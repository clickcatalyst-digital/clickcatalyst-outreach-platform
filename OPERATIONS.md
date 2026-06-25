# Operations Runbook — ClickCatalyst US Engine

One-page guide to run, monitor, and troubleshoot the autonomous outreach engine.
Architecture detail lives in [CODEBASE.md](CODEBASE.md) ("Current Architecture & Operations").

```
Render (Next.js dashboard, US-only)  ⇄  Turso (cat-mail-db)  ⇄  Mac (workers + 2 launchd daemons)
```
The Mac executes; Turso is shared state; the dashboard reads/writes Turso. Nothing runs in the cloud except the dashboard UI.

---

## ✅ Check overall status (fastest → richest)

| How | What it tells you |
|---|---|
| `cd dashboard && npm run doctor` | Green/red board: Mac heartbeat, orchestrator, tracking-sync, command queue, scheduler+mode, bayesian, alerts, last send, **lead funnel**. Run before sleep. |
| `npm run verify` (in `dashboard/`) | Every dashboard API endpoint returns 200. |
| Dashboard → **System** page | Same board in the browser (polls every 15s). |
| Dashboard → **US Outreach** | Funnel + live status + mode/schedule controls. |

`doctor`/`verify` default to the hosted URL via env, or pass args:
`node scripts/doctor.mjs https://<app>.onrender.com <user>:<pass>`

---

## Is the engine actually running? (the autonomy check)

```bash
launchctl list | grep clickcatalyst          # both jobs should be listed
launchctl print gui/$(id -u)/com.clickcatalyst.us | grep 'runs ='   # run count should climb every 20 min
tail -f logs/orchestrator_$(date +%F).log     # watch live cycles
```
- `com.clickcatalyst.heartbeat` → 60s liveness beat.
- `com.clickcatalyst.us` → 20-min engine tick (`tick.sh` = orchestrator + sync + replies + command_worker).
- Both auto-load on login/reboot (installed in `~/Library/LaunchAgents`). **They do not fire while the Mac is asleep.**

---

## Common actions

| Task | How |
|---|---|
| **Go live (prod)** | Dashboard → US Outreach → flip **Mode → Production**. Picked up within ≤20 min. (Or `mode` row in `us_scheduler_config`.) |
| **Pause / resume** | Dashboard → US Outreach → Pause all / Resume. |
| **Run a cycle now** | Dashboard → "Run cycle now" (enqueues `command_queue`; Mac runs it next tick). |
| **Start/stop the engine** | `launchctl load   ~/Library/LaunchAgents/com.clickcatalyst.us.plist` / `unload` to stop. |
| **Re-auth Gmail (replies)** | `python reply_tracker.py` in a terminal (one-time browser consent → new `token.json`). |
| **View logs** | `logs/{orchestrator,sync,replies}_YYYY-MM-DD.log` (dated, 7-day retention). |

---

## Troubleshooting

- **Dashboard shows "Last ran 20h ago" / stale heartbeat** → the engine daemon isn't running. Check `launchctl list | grep clickcatalyst`; if `com.clickcatalyst.us` is missing, install + load it (cp the plist to `~/Library/LaunchAgents`, `launchctl load`). Confirm the Mac is awake + online. (This was the original root cause — the daemon was never loaded.)
- **"Database not reachable" banner** → Turso creds. Hit `/api/health` on the dashboard; it reports `hasUrl`/`hasToken`/error. Ensure Render's `TURSO_URL`/`TURSO_AUTH_TOKEN` match the Mac's `.env`.
- **Dashboard data looks frozen but daemon is running** → confirm the deployed build is current (Render → Manual Deploy → **Clear build cache & deploy**). Route handlers are `force-dynamic` (live); a stale build or browser cache is the usual culprit — hard-refresh.
- **Replies not tracking** → Gmail token expired; re-auth (above). Sends/tracking/analytics are unaffected.
- **Test sends "missing" from analytics** → by design: `Batch_ID ustest%` is excluded everywhere; see the Analytics "Testing" line for the count.

---

## Definition of healthy
`npm run doctor` all-green (except replies until Gmail re-auth), engine `runs` climbing every 20 min, dashboard heartbeat < 3 min, funnel advancing. If all true, the engine is self-running — no need to touch the Mac.
