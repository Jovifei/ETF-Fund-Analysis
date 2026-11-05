# Phase A email/slim wiring (box runtime mirror)

Production runtime path: `/workspace/etf_slot/email_render/`.

- `extract_slim.py` → `slim_version=etf-email-slim-v1.1`; optional per-row `structure_v1` (flat) or `--structure-sidecar`.
- `attach_structure_v1.py` → join shadow `{header,rows[]}` flat structure_v1 onto existing slim by `ts_code`.
- `render_strategy_email.py` → columns 威科夫 / 道氏 / ATR风险桶; missing → —; proxy disclaimer once.

Does **not** change `assign_grade` / five-档 weights.
