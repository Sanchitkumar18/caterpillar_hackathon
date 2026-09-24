# Synthetic Machine-Manual Knowledge Base

SYNTHETIC hackathon content — not an official Caterpillar manual. Does not represent real Caterpillar procedures, specifications, or safety thresholds. Always follow the official machine manual and your supervisor. Operation/how-to guidance only; for faults, leaks, or repairs, stop and contact a qualified technician.

## Contents
- `<MODEL>.md` — one how-to operator guide per fleet model (CAT 320, CAT 336, CAT 966, CAT 950, CAT D6, CAT D5).
- `manuals_kb.json` — 82 retrieval chunks: each has `machine_model`, `machine_type`,
  `category`, `title`, `question_examples`, and `content`. Ideal for RAG ingestion.

## How to use (for the Airia RAG pipeline)
1. Ingest either the `.md` files (as documents) or `manuals_kb.json` (as pre-chunked
   passages). The `question_examples` fields help retrieval match how operators
   actually phrase questions ("how do I use the hydraulic thumb").
2. Keep the disclaimer visible — this is synthetic how-to content, not real CAT
   procedures, and covers operation only (no repair/diagnostic/override steps).

## Regenerate
`python scripts/generate_manuals.py`
