#!/usr/bin/env bash
# scripts/tick.sh
# One tick of the US outreach engine, run by launchd on an interval.
# Runs orchestrator + tracking sync + reply detection ONCE each, logs to dated
# files in logs/, and keeps only the last 7 days of logs.
#
# Why --once (not --daemon): each tick is independent, so a crash self-heals on
# the next tick (no perpetual process to die), and it mirrors the cloud cron model.

set -uo pipefail

PROJECT_DIR="/Users/pujan/Developer/research_leads"
cd "$PROJECT_DIR" || exit 1

# launchd gives a minimal PATH — make pyenv / homebrew pythons resolvable.
export PATH="$HOME/.pyenv/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Secrets in .env are loaded by python-dotenv inside each script (config.py,
# sync_outreach_tracking.py, reply_tracker.py) — NOT sourced in bash (the .env
# uses python-dotenv format that breaks `source`). We only point at the Firebase
# key here, which the tracking sync reads from the environment.
export FIREBASE_CREDENTIALS_PATH="${FIREBASE_CREDENTIALS_PATH:-$PROJECT_DIR/keys/tier1-web-firebase-adminsdk-fbsvc-3a34532ca1.json}"

PY="${PYTHON:-python}"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
DAY="$(date +%F)"
TS="$(date +'%F %T')"

run() {  # run <name> <command...>
  local name="$1"; shift
  local log="$LOG_DIR/${name}_${DAY}.log"
  echo "[$TS] >>> $name" >> "$log"
  "$@" >> "$log" 2>&1
  echo "[$TS] <<< $name (exit $?)" >> "$log"
}

# ── Wait for internet before running ──────────────────────────────────────────
# A tick can fire right after the Mac wakes, before DNS/network is ready — which
# made the tracking sync burn 300s failing on a DNS lookup. Wait up to ~60s for
# connectivity; if still offline, skip this tick (launchd retries next interval).
online=0
for _ in $(seq 1 12); do
  if curl -s -m 5 -o /dev/null https://www.googleapis.com 2>/dev/null; then online=1; break; fi
  sleep 5
done
if [ "$online" -ne 1 ]; then
  echo "[$(date +'%F %T')] tick skipped — no internet after 60s" >> "$LOG_DIR/launchd.out.log"
  exit 0
fi

run orchestrator "$PY" -m us_lead_engine.orchestrator --once
run sync         "$PY" sync_outreach_tracking.py
run replies      "$PY" reply_tracker.py
run commands     "$PY" command_worker.py

# Retention: keep only the last 7 days of logs.
find "$LOG_DIR" -name '*.log' -mtime +7 -delete 2>/dev/null

exit 0
