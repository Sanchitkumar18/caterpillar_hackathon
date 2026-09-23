#!/usr/bin/env bash
# Download the small offline Vosk STT model (~40MB) used for on-device voice.
# Run once after cloning: bash scripts/get_models.sh
set -e
cd "$(dirname "$0")/.."
mkdir -p models && cd models
if [ -d "vosk-model-small-en-us-0.15" ]; then echo "English model already present."; exit 0; fi
echo "Downloading vosk-model-small-en-us-0.15 (~40MB)..."
curl -L -o m.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip -q m.zip && rm m.zip
echo "Done. Offline voice is ready."
# Optional Hindi model (uncomment):
# curl -L -o hi.zip https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip && unzip -q hi.zip && rm hi.zip
