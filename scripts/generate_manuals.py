"""
Synthetic MACHINE-MANUAL knowledge base generator for CAT Operator Copilot.

Produces feature-level, how-to operator content for the fleet's machine models,
structured for RAG ingestion (e.g. an Airia pipeline) and for an optional local
offline knowledge base.

Output:
  data/manuals/<MODEL>.md          one readable manual per model
  data/manuals/manuals_kb.json     flat list of retrievable chunks (RAG-ready)
  data/manuals/README.md           what this is + how to ingest

IMPORTANT: All content is SYNTHETIC hackathon data written for this prototype.
It is NOT an official Caterpillar operator manual and does NOT represent real
Caterpillar procedures, specifications, or safety thresholds. For real operation
always follow the official machine manual and a qualified supervisor. The content
intentionally covers OPERATION / how-to only — it never gives repair, diagnostic,
or safety-override procedures.

Usage: python scripts/generate_manuals.py
"""
from __future__ import annotations
import json
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "manuals")
os.makedirs(OUT, exist_ok=True)

DISCLAIMER = (
    "SYNTHETIC hackathon content — not an official Caterpillar manual. Does not "
    "represent real Caterpillar procedures, specifications, or safety thresholds. "
    "Always follow the official machine manual and your supervisor. Operation/how-to "
    "guidance only; for faults, leaks, or repairs, stop and contact a qualified technician."
)

# ---- Fleet models (synthetic spec values) ----
MODELS = [
    {"model": "CAT 320", "type": "Excavator", "machines": ["EXC001", "EXC003"],
     "op_weight_t": 22.9, "engine_hp": 162, "bucket_m3": 1.19, "max_dig_depth_m": 6.7, "work_tool": "bucket / hydraulic thumb / breaker"},
    {"model": "CAT 336", "type": "Excavator", "machines": ["EXC002"],
     "op_weight_t": 38.5, "engine_hp": 311, "bucket_m3": 2.2, "max_dig_depth_m": 7.9, "work_tool": "bucket / hydraulic thumb / breaker"},
    {"model": "CAT 966", "type": "Wheel Loader", "machines": ["LOD001"],
     "op_weight_t": 23.5, "engine_hp": 296, "bucket_m3": 4.2, "max_dig_depth_m": None, "work_tool": "general-purpose bucket / forks"},
    {"model": "CAT 950", "type": "Wheel Loader", "machines": ["LOD002"],
     "op_weight_t": 20.2, "engine_hp": 256, "bucket_m3": 3.5, "max_dig_depth_m": None, "work_tool": "general-purpose bucket / forks"},
    {"model": "CAT D6", "type": "Dozer", "machines": ["DOZ001"],
     "op_weight_t": 23.0, "engine_hp": 215, "bucket_m3": None, "blade_m3": 5.6, "work_tool": "VPAT blade / ripper"},
    {"model": "CAT D5", "type": "Dozer", "machines": ["DOZ002"],
     "op_weight_t": 20.9, "engine_hp": 150, "bucket_m3": None, "blade_m3": 4.28, "work_tool": "VPAT blade / ripper"},
]

# ---- Article templates ----
# Each: (category, title, [question phrasings], body-with-{placeholders})
# {model} {type} {engine_hp} {op_weight_t} {bucket_m3} {blade_m3} {max_dig_depth_m} {work_tool}

COMMON = [
    ("Startup", "Daily pre-start walkaround", [
        "how do I do the pre-start check", "what should I do before starting the {model}",
        "walkaround checklist", "what to check before operating"],
     "Before starting the {model}, do a walkaround: check for leaks, loose bolts, tyre/track condition, "
     "damaged guards, and that lights and mirrors are clean. Check engine oil, coolant and hydraulic "
     "levels are in the safe range on the dipsticks/sight glasses. Clear the area of people and obstacles, "
     "then enter the cab using three points of contact. Adjust the seat and mirrors, fasten the seatbelt, "
     "and confirm all controls are in neutral before cranking. If anything looks abnormal, do not operate — "
     "report it to your supervisor."),
    ("Startup", "Starting and warming up", [
        "how do I start the {model}", "engine start procedure", "how to warm up the machine",
        "cold start steps"],
     "With the parking brake applied and controls in neutral, turn the key to ON and wait for the monitor "
     "self-check and any wait-to-start lamp to clear. Start the engine and let it idle to build hydraulic "
     "and system pressure; allow a warm-up idle before heavy work, longer in cold conditions. Watch the "
     "monitor for normal oil pressure and temperature. Do not rev a cold engine. If a warning lamp stays "
     "on after start, stop and report it rather than operating."),
    ("Controls", "Reading the in-cab monitor / display", [
        "what does the display show", "how do I read the monitor", "what do the icons mean",
        "how to change display settings"],
     "The {model} touchscreen/keypad monitor shows engine RPM, fuel level, coolant/hydraulic temperature, "
     "DEF level, work mode, and camera views. Menu buttons let you change units, brightness, language, and "
     "select work modes. Green icons are normal status; amber icons are cautions to check at a safe stopping "
     "point; red icons mean stop safely and investigate. Use the rear/side camera view when reversing. If you "
     "are unsure what an icon means, stop in a safe spot and check before continuing."),
    ("Safety", "Seatbelt, cab and visibility", [
        "why does it record my seatbelt", "how do I set up the cab safely", "seatbelt and mirrors",
        "how to improve visibility"],
     "Always fasten the seatbelt before moving; the {model} logs seatbelt status each shift and it is reviewed. "
     "Adjust the seat so you can reach all controls comfortably and see the mirrors and camera clearly. Keep "
     "windows, mirrors and cameras clean. Use the horn before starting and before reversing. Keep people out of "
     "the working radius. Seatbelt, alarms and guards are safety systems — never disable or bypass them."),
    ("Operation", "Working in rain, mud and poor visibility", [
        "how do I work in the rain", "operating in wet ground", "tips for muddy conditions",
        "what changes in bad weather"],
     "In wet or muddy conditions expect reduced traction and slower cycle times, so plan extra time. Reduce "
     "speed, avoid steep or unstable ground, and keep loads lower for stability. Watch for the machine sliding "
     "on slopes. In poor visibility use lights, slow down, and use the cameras and a spotter where available. "
     "If conditions become unsafe, stop and consult your supervisor — the Copilot can also flag weather-sensitive "
     "tasks in your schedule."),
    ("Shutdown", "Parking and shutdown", [
        "how do I park the {model}", "shutdown procedure", "how to stop for a break",
        "end of shift steps"],
     "Park on firm, level ground clear of traffic. Lower the work tool (bucket/blade) fully to the ground, set "
     "the controls to neutral and apply the parking brake. Idle the engine briefly to let turbo/temperatures "
     "settle, then turn it off and remove the key. Lower any hydraulic lockouts, close windows, and dismount "
     "using three points of contact. For a longer stop, chock as required by site rules."),
    ("Efficiency", "Reducing idle time and fuel use", [
        "how do I save fuel", "how to reduce idling", "tips to be more efficient",
        "why is my idle time high"],
     "Idling wastes fuel and adds engine hours. Use the auto-idle/auto-shutdown features if fitted, and switch "
     "off during long waits instead of idling. Match the work mode to the task — a lighter/economy mode for "
     "finishing work uses less fuel than full power. Plan loads to minimise empty travel and re-handling. The "
     "Copilot dashboard shows your idle time so you can see the effect of these habits over the shift."),
]

EXCAVATOR = [
    ("Controls", "Joystick controls and pattern", [
        "how do the joysticks work", "what does each joystick do", "how to change control pattern (ISO/SAE)",
        "excavator control layout"],
     "The {model} uses two joysticks. In the common ISO pattern: left joystick controls stick (in/out) and "
     "swing (left/right); right joystick controls boom (up/down) and bucket (curl/dump). Foot pedals/levers "
     "control travel, and an auxiliary control (thumb roller/button) runs attachments. Some machines let you "
     "switch between ISO and SAE patterns via a selector or the monitor menu — confirm which pattern is set "
     "before operating, and never change it while the machine is moving."),
    ("Attachments", "Using the quick coupler", [
        "how do I engage the quick coupler", "how to change attachments", "quick coupler steps",
        "how to lock the bucket on"],
     "A quick coupler lets you change work tools without leaving the cab on some machines. Typical sequence: "
     "park on level ground, select the coupler function (often via a monitor menu or switch, sometimes with a "
     "confirmation because it is a safety step), unlock the coupler, line up and engage the attachment pins, "
     "then lock the coupler and confirm the lock indicator. Always visually confirm the attachment is fully "
     "locked by curling and gently testing it near the ground before working. If the lock indicator does not "
     "confirm, stop and check — do not lift or swing an unconfirmed attachment."),
    ("Attachments", "Operating the hydraulic thumb", [
        "how do I use the hydraulic thumb", "how to grab material with the thumb", "hydraulic thumb operation",
        "how to pick up debris"],
     "The hydraulic thumb works with the bucket to grip material like rock, pipe or debris. Engage the auxiliary "
     "hydraulics (usually a joystick roller/button), then open the thumb, position the bucket under the object, "
     "and close the thumb to clamp it against the bucket. Move slowly and keep the load close and low for "
     "stability; avoid side-loading the thumb or over-gripping. Release by opening the thumb over the drop "
     "location. Stow the thumb against the stick when travelling. This is a how-to overview — follow the tool's "
     "own guidance for its rating and limits."),
    ("Attachments", "Fitting and running a hydraulic breaker", [
        "how do I use the breaker", "hammer attachment operation", "how to run the hydraulic breaker",
        "breaker tips"],
     "A hydraulic breaker (hammer) is used to break rock or concrete. Fit it via the coupler/auxiliary lines and "
     "confirm the lock and hose connections. Position the tool vertically against the material, apply firm down "
     "pressure with the boom, and operate in short bursts — moving the point to a fresh spot rather than "
     "hammering one place too long. Do not pry with the breaker or use it under water unless it is rated for it. "
     "Keep people well clear of flying debris. Refer to the breaker's own operating limits."),
    ("Operation", "Work modes (power / smart / fine)", [
        "how do I switch work modes", "what is fine grading mode", "how to change to economy mode",
        "power mode vs economy"],
     "The {model} offers selectable work modes via the monitor: a high-power mode for heavy digging, a "
     "smart/standard mode that balances power and fuel, and a fine/precision mode for careful grading and "
     "trenching. Select the mode from the monitor before starting the task. Use fine mode for smooth, "
     "controlled movements when finishing a grade or working near services; use power mode for tough digging. "
     "Matching the mode to the task improves control and reduces fuel use."),
    ("Operation", "Digging and trenching technique", [
        "how do I dig efficiently", "trenching tips", "how to dig a straight trench",
        "excavation technique"],
     "Position the machine square to the trench line on stable ground with the tracks aligned to the direction "
     "of dig. Take even passes, filling the bucket by curling as you draw the stick in, and lift smoothly. Keep "
     "spoil piled far enough back that it does not fall in or destabilise the edge. For trenches, check for "
     "underground services first and follow shoring/edge-protection rules. In wet ground expect the sides to "
     "slump and allow more time. Swing and dump with the upper structure over the tracks where possible for "
     "stability."),
    ("Operation", "Grade / depth assist", [
        "how do I use grade assist", "what is 2D grade control", "how to hit target depth",
        "depth guidance"],
     "If your {model} is fitted with grade/2D assist, the monitor shows bucket tip elevation relative to a "
     "target depth and slope, helping you reach grade with fewer checks. Set the reference/benchmark as your "
     "site requires, then watch the on-screen indicators (cut/fill) as you work. Grade assist is an aid, not a "
     "replacement for survey checks — verify critical depths by conventional means and follow site quality "
     "control."),
    ("Safety", "Swing radius and working near people", [
        "how do I work safely near people", "swing safety", "working near other machines",
        "how to avoid hitting things when swinging"],
     "The counterweight swings within the machine's tail radius, which can be close to obstacles and people. "
     "Before swinging, check mirrors and cameras and sound the horn. Keep everyone outside the swing radius and "
     "never swing a load over people. Use a spotter in tight areas. Lock the swing when required (e.g. during "
     "transport or coupler changes). Move deliberately and keep loads low."),
]

LOADER = [
    ("Controls", "Loader controls and joystick", [
        "how do the loader controls work", "what does the loader joystick do", "lift and tilt controls",
        "wheel loader control layout"],
     "The {model} uses a single joystick (or lever set) for the lift arms (raise/lower) and bucket (tilt back / "
     "dump), plus a steering wheel or steering joystick, and a forward/neutral/reverse selector. Detents can "
     "hold raise or return-to-dig positions. The throttle and service brakes are foot-operated. Confirm the "
     "transmission is in neutral with the parking brake set before starting, and know where the ride-control "
     "and differential-lock switches are before you begin."),
    ("Operation", "Load-and-carry technique", [
        "how do I load efficiently", "loading a truck", "how to fill the bucket",
        "load and carry tips"],
     "Approach the pile square and low, drive in with the bucket flat, and crowd (tilt back) while lifting to "
     "fill the bucket in one smooth motion — avoid spinning the wheels. Carry the load low for stability and "
     "visibility while travelling. When loading a truck, approach at a slight angle, lift only as high as needed, "
     "and dump smoothly into the centre of the bed. Keep the work area tidy to reduce re-handling and cycle time."),
    ("Operation", "Ride control and load stability", [
        "what is ride control", "how do I turn on ride control", "how to reduce bouncing",
        "carrying loads smoothly"],
     "Ride control cushions the lift-arm hydraulics so the machine bounces less when travelling with a load over "
     "rough ground, protecting the load and improving comfort and control. Switch it on (via its cab switch) for "
     "load-and-carry over distance; it is usually best left off for precise truck loading. Even with ride control, "
     "keep the bucket low and speed sensible for the ground conditions."),
    ("Operation", "Using the differential lock", [
        "how do I use the diff lock", "differential lock in mud", "how to get traction",
        "when to engage diff lock"],
     "The differential lock improves traction on slippery or soft ground by driving the wheels together. Engage "
     "it briefly (usually a pedal or switch) when driving straight into a pile or through mud, and release it "
     "before turning to avoid driveline strain and tyre scrub. Do not leave it engaged for normal travel or "
     "cornering. Combine with sensible throttle to avoid wheel spin."),
    ("Operation", "Payload weighing", [
        "how do I check the load weight", "payload scale", "how to weigh the bucket",
        "on-board weighing"],
     "If fitted, the on-board payload system shows the weight in the bucket and a running total for the truck on "
     "the monitor, helping you load to target without over/under-loading. Lift smoothly through the weigh range "
     "as prompted for an accurate reading. Use it to avoid overloading trucks and to track productivity. Calibrate "
     "as your site requires for accurate figures."),
    ("Attachments", "Switching bucket to forks", [
        "how do I fit the forks", "change from bucket to forks", "using pallet forks",
        "attachment change on the loader"],
     "With a quick coupler, park on level ground, tilt to the coupler position, disengage the bucket, and drive "
     "clear; then line up and engage the forks and confirm the coupler lock indicator. With forks, keep loads "
     "low and centred, travel with the load tilted slightly back, and lift only as high as needed. Confirm the "
     "attachment is fully locked before lifting any load."),
]

DOZER = [
    ("Controls", "Blade and steering controls", [
        "how do the dozer controls work", "what does the blade joystick do", "how to steer the dozer",
        "dozer control layout"],
     "The {model} typically uses a steering/direction control (differential steering lever or joystick) in one "
     "hand and a blade control joystick in the other. The blade joystick raises/lowers and, on a VPAT blade, "
     "angles and tilts the blade. A decelerator and brake pedal control speed. Confirm neutral and parking brake "
     "before start, and know your blade and ripper control positions before moving."),
    ("Operation", "Grading and finishing technique", [
        "how do I grade with the dozer", "how to make a smooth grade", "finishing technique",
        "dozing tips"],
     "For a smooth grade, carry a consistent blade load and make overlapping passes, letting the tracks run on "
     "already-cut ground for a level reference. Make small blade adjustments rather than large corrections. Work "
     "up and down slopes rather than across where possible for stability. Slot dozing (using previous cuts to "
     "hold material) moves more material efficiently on longer pushes. Keep speed steady for an even finish."),
    ("Operation", "Using blade tilt, angle and pitch (VPAT)", [
        "how do I tilt the blade", "what is blade angle and pitch", "how to use the VPAT blade",
        "blade positioning"],
     "A VPAT (variable-angle power-tilt) blade can tilt (one corner lower to cut or crown), angle (turn to cast "
     "material to one side, useful for backfilling or windrowing), and pitch (change the cutting aggressiveness). "
     "Use tilt to correct level or start a cut, angle to move material sideways along the blade, and a steeper "
     "pitch for hard material. Make one adjustment at a time and observe the result before combining them."),
    ("Operation", "Slope / grade control assist", [
        "how do I use grade control", "slope assist on the dozer", "how to hit target slope",
        "automatic blade control"],
     "If your {model} has grade/slope assist, the system helps hold blade elevation and cross-slope to a target, "
     "reducing manual corrections and rework. Set the target grade/slope as your site requires and let the system "
     "assist while you manage speed and blade load. It is an aid — verify final grade against survey checks and "
     "follow site quality control."),
    ("Attachments", "Operating the ripper", [
        "how do I use the ripper", "ripping technique", "how to break up hard ground",
        "rear ripper operation"],
     "The rear ripper breaks up hard or compacted ground so it can be dozed. Lower the ripper shank(s) to a "
     "moderate depth first, drive forward at a steady speed, and increase depth gradually — forcing full depth "
     "immediately can stall or strain the machine. Rip in one direction, then cross-rip if needed. Raise the "
     "ripper fully before reversing over ripped ground or turning."),
    ("Operation", "Track condition and soft ground", [
        "how do I drive on soft ground", "track care", "operating on slopes safely",
        "avoiding the dozer sliding"],
     "On soft or wet ground, spread passes to avoid digging in and keep moving smoothly rather than spinning the "
     "tracks. On slopes, keep the blade low, work up/down rather than across where possible, and avoid sudden "
     "steering that can cause sliding. Watch for the machine walking downhill on side slopes. If the ground is "
     "too unstable, stop and reassess with your supervisor."),
]

BY_TYPE = {"Excavator": EXCAVATOR, "Wheel Loader": LOADER, "Dozer": DOZER}


def fill(text: str, m: dict) -> str:
    return text.format(
        model=m["model"], type=m["type"], engine_hp=m["engine_hp"], op_weight_t=m["op_weight_t"],
        bucket_m3=m.get("bucket_m3"), blade_m3=m.get("blade_m3"),
        max_dig_depth_m=m.get("max_dig_depth_m"), work_tool=m["work_tool"],
    )


def spec_block(m: dict) -> str:
    lines = [
        "| Spec (synthetic) | Value |",
        "|---|---|",
        "| Model | %s |" % m["model"],
        "| Type | %s |" % m["type"],
        "| In fleet as | %s |" % ", ".join(m["machines"]),
        "| Operating weight | ~%s t |" % m["op_weight_t"],
        "| Engine power | ~%s hp |" % m["engine_hp"],
    ]
    if m.get("bucket_m3"):
        lines.append("| Bucket capacity | ~%s m³ |" % m["bucket_m3"])
    if m.get("blade_m3"):
        lines.append("| Blade capacity | ~%s m³ |" % m["blade_m3"])
    if m.get("max_dig_depth_m"):
        lines.append("| Max dig depth | ~%s m |" % m["max_dig_depth_m"])
    lines.append("| Work tools | %s |" % m["work_tool"])
    return "\n".join(lines)


kb = []
kb_id = 1
manifest = []

for m in MODELS:
    articles = COMMON + BY_TYPE[m["type"]]
    md = []
    md.append("# %s — Operator How-To Guide (Synthetic)\n" % m["model"])
    md.append("> %s\n" % DISCLAIMER)
    md.append("## Specifications\n\n%s\n" % spec_block(m))
    for (category, title, questions, body) in articles:
        t = fill(title, m)
        b = fill(body, m)
        qs = [fill(q, m) for q in questions]
        md.append("## %s — %s\n\n%s\n" % (category, t, b))
        kb.append({
            "id": "KB%04d" % kb_id,
            "machine_model": m["model"],
            "machine_type": m["type"],
            "machines": m["machines"],
            "category": category,
            "title": t,
            "question_examples": qs,
            "content": b,
            "disclaimer": "Synthetic operation/how-to content — not an official Caterpillar manual.",
        })
        kb_id += 1
    fname = m["model"].replace(" ", "_") + ".md"
    with open(os.path.join(OUT, fname), "w") as f:
        f.write("\n".join(md))
    manifest.append(fname)
    print("  %s: %d sections" % (fname, len(articles)))

with open(os.path.join(OUT, "manuals_kb.json"), "w") as f:
    json.dump({"disclaimer": DISCLAIMER, "count": len(kb), "chunks": kb}, f, indent=2, ensure_ascii=False)

readme = """# Synthetic Machine-Manual Knowledge Base

%s

## Contents
- `<MODEL>.md` — one how-to operator guide per fleet model (%s).
- `manuals_kb.json` — %d retrieval chunks: each has `machine_model`, `machine_type`,
  `category`, `title`, `question_examples`, and `content`. Ideal for RAG ingestion.

## How to use (for the Airia RAG pipeline)
1. Ingest either the `.md` files (as documents) or `manuals_kb.json` (as pre-chunked
   passages). The `question_examples` fields help retrieval match how operators
   actually phrase questions ("how do I use the hydraulic thumb").
2. Keep the disclaimer visible — this is synthetic how-to content, not real CAT
   procedures, and covers operation only (no repair/diagnostic/override steps).

## Regenerate
`python scripts/generate_manuals.py`
""" % (DISCLAIMER, ", ".join(m["model"] for m in MODELS), len(kb))

with open(os.path.join(OUT, "README.md"), "w") as f:
    f.write(readme)

print("Done. %d models, %d KB chunks -> %s" % (len(MODELS), len(kb), OUT))
