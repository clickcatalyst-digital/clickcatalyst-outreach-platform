# US Lead Engine

Independent module: sources US marketing/advertising agency leads from Apollo,
qualifies + reveals them credit-efficiently, and runs a self-scheduling outreach
sender. Its own SQLite DB (`us_leads.db`); exports into the main pipeline's
`company_contacts` / `company_enrichment`.

> **Full reference lives in `../CODEBASE.md` → "US Lead Engine" section** (schema,
> flow, Apollo facts, orchestrator, alerts, control-tower UI, Gemma summarizer,
> country dropdown, env vars, and future work). This README is just a launchpad.

## Quick commands
```bash
# Discovery → qualify → reveal → pixel → export
python -m us_lead_engine.run_discovery --dry-run        # search + qualify (0 credits)
python -m us_lead_engine.run_discovery --enrich 5       # reveal 5 (5 credits)
python -m us_lead_engine.run_discovery --export         # push to main pipeline
python -m us_lead_engine.run_discovery --cost           # spend report

# Campaign arms + manual send
python -m us_lead_engine.run_discovery --seed-campaigns
python -m us_lead_engine.run_discovery --send 5 --test you@example.com   # test to self

# Self-running orchestrator (the control tower's engine)
python -m us_lead_engine.orchestrator --init            # tables + defaults (start = next Mon)
python -m us_lead_engine.orchestrator --daemon          # run continuously
python -m us_lead_engine.orchestrator --status          # JSON status

# AI thread summaries (after a contact replies)
python -m us_lead_engine.summarizer --all-replied
```

## Companion daemons (project root, not this module)
- `sync_outreach_tracking.py --daemon` — Firestore opens/clicks → SQLite (needs `FIREBASE_CREDENTIALS_PATH`)
- `reply_tracker.py --daemon` — Gmail reply detection + auto-summarize (needs `credentials.json` / `token.json`)

## Key env
`APOLLO_API_KEY` (master), `SENDER_EMAIL`, `SENDER_APP_PASS`, `US_POSTAL_ADDRESS`,
`OPENROUTER_API_KEY` (Gemma), `FIREBASE_CREDENTIALS_PATH`. See CODEBASE.md for the full table.
