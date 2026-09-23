"""VoiceService — provider-agnostic abstraction so the app is not coupled to
Google Cloud. Credentials stay on the backend only.

    VoiceService  ->  GoogleCloudVoiceProvider (when creds present)
                  ->  BrowserFallbackProvider  (frontend Web Speech API)

The Google SDK is imported lazily and only if credentials exist, so the app
runs (and the demo works) with zero cloud setup.
"""
from __future__ import annotations
import base64
import datetime
import os
import re
from typing import Optional, Dict, Any


_BASE = os.path.join(os.path.dirname(__file__), "..", "..")
VOSK_MODEL_PATH = os.environ.get("VOSK_MODEL_PATH", os.path.join(_BASE, "models", "vosk-model-small-en-us-0.15"))


def vosk_available() -> bool:
    try:
        import vosk  # noqa: F401
        return os.path.isdir(VOSK_MODEL_PATH)
    except Exception:
        return False


def _provider_mode() -> str:
    """Priority — an EXPLICIT VOICE_PROVIDER wins; otherwise prefer the offline,
    on-device engine so the copilot keeps working with no internet, then cloud,
    then the browser Web Speech API."""
    forced = os.environ.get("VOICE_PROVIDER", "auto")
    if forced in ("google", "browser", "offline"):
        if forced == "offline" and not vosk_available():
            return "browser"
        return forced
    if vosk_available():
        return "offline"
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and os.environ.get("GOOGLE_CLOUD_PROJECT_ID"):
        return "google"
    return "browser"


class BrowserFallbackProvider:
    name = "browser"
    available = True

    def transcribe_audio(self, audio_b64: str, language: str = "en-IN"):
        # Client already transcribed via Web Speech API and posts text.
        return {"transcript": "", "language": "en-IN"}

    def synthesize_speech(self, text: str, language: str):
        return None  # client uses speechSynthesis


class GoogleCloudVoiceProvider:
    name = "google"
    available = True

    def transcribe_audio(self, audio_b64: str, language: str = "en-IN"):
        from google.cloud import speech  # imported lazily; optional dependency
        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=base64.b64decode(audio_b64))
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            sample_rate_hertz=48000,
            language_code=language,
            alternative_language_codes=["en-IN", "hi-IN"],
            enable_automatic_punctuation=True,
        )
        resp = client.recognize(config=config, audio=audio)
        transcript = " ".join(r.alternatives[0].transcript for r in resp.results).strip()
        detected = resp.results[0].language_code if resp.results else language
        return {"transcript": transcript, "language": detected or language}

    def synthesize_speech(self, text: str, language: str):
        from google.cloud import texttospeech  # imported lazily; optional dependency
        client = texttospeech.TextToSpeechClient()
        resp = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(language_code=language, ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3),
        )
        return {"audioBase64": base64.b64encode(resp.audio_content).decode("ascii"), "mimeType": "audio/mpeg"}


class OfflineVoiceProvider:
    """On-device speech-to-text via Vosk. Runs fully offline — no internet, no
    cloud, no API keys. This is the copilot's connectivity-independent voice path."""
    name = "offline"
    available = True
    _model = None  # loaded once, reused

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            from vosk import Model
            cls._model = Model(VOSK_MODEL_PATH)
        return cls._model

    def transcribe_audio(self, audio_b64: str, language: str = "en-IN"):
        import io
        import json as _json
        import wave
        from vosk import KaldiRecognizer
        raw = base64.b64decode(audio_b64)
        wf = wave.open(io.BytesIO(raw), "rb")
        rec = KaldiRecognizer(self._get_model(), wf.getframerate())
        rec.SetWords(False)
        text_parts = []
        while True:
            frames = wf.readframes(4000)
            if not frames:
                break
            if rec.AcceptWaveform(frames):
                text_parts.append(_json.loads(rec.Result()).get("text", ""))
        text_parts.append(_json.loads(rec.FinalResult()).get("text", ""))
        transcript = " ".join(p for p in text_parts if p).strip()
        return {"transcript": transcript, "language": language}

    def synthesize_speech(self, text: str, language: str):
        # TTS stays on the client (browser speechSynthesis uses local, offline voices).
        return None


def get_voice_service():
    mode = _provider_mode()
    if mode == "offline":
        try:
            return OfflineVoiceProvider()
        except Exception:
            return BrowserFallbackProvider()
    if mode == "google":
        try:
            return GoogleCloudVoiceProvider()
        except Exception:
            return BrowserFallbackProvider()
    return BrowserFallbackProvider()


def voice_status():
    """Which STT engines are available, for the UI mode indicator."""
    return {
        "active": _provider_mode(),
        "offlineAvailable": vosk_available(),
        "cloudAvailable": bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and os.environ.get("GOOGLE_CLOUD_PROJECT_ID")),
    }


# ---------- Structured note extraction ----------
TASK_WORDS = ["Trenching", "Earth Excavation", "Excavation", "Material Loading", "Grading",
              "Demolition", "Site Preparation", "Material Movement"]
REASON_WORDS = {"rain": "Rain", "wet": "Wet ground", "mud": "Muddy ground", "wind": "Wind",
                "fuel": "Refuelling", "break down": "Machine issue", "slow": "Machine performance"}


def extract_note(transcript: str, language: str) -> Dict[str, Any]:
    t = transcript.lower()
    task = next((w for w in TASK_WORDS if w.lower() in t), None)
    dur_match = re.search(r"(\d{1,3})\s*(min|minute|minutes|मिनट)", t)
    duration = int(dur_match.group(1)) if dur_match else None
    reason = next((v for k, v in REASON_WORDS.items() if k in t), None)

    category = "general"
    if "delay" in t or "slow" in t or "longer" in t or (duration and task):
        category = "task_delay"
    elif "safety" in t or "seatbelt" in t or "alert" in t:
        category = "safety"
    elif "machine" in t or "engine" in t or "hydraulic" in t:
        category = "machine"

    return {
        "note": transcript,  # original always preserved
        "language": language,
        "category": category,
        "task": task,
        "reason": reason,
        "duration_minutes": duration,
        "source": "voice",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
