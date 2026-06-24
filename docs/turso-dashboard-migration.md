# Turso Dashboard Migration Plan (Model B)

**Goal:** Host the Next.js dashboard on Render. It must operate **entirely through Turso**, never contacting the Mac. The Mac stays private and runs FastAPI + workers locally. Turso is the shared state.

---

## 1. How data access changes

Today every page calls the local FastAPI via `fetch(\`${API}/...\`)` / `apiFetch()` (see `dashboard/app/lib/api.js`). That only works at the Mac. For Model B:

- **Add a server-side Turso layer in Next.js.** Use Route Handlers (`app/api/*/route.js`) or Server Actions that hold the Turso URL + token as **server-only env vars** (`TURSO_URL`, `TURSO_AUTH_TOKEN` — *not* `NEXT_PUBLIC_*`). The browser calls these Next.js server endpoints; the server queries Turso with `@libsql/client`. **The token never reaches the browser.**
- **Add auth (login).** The dashboard exposes CRM data + config writes, so it must be gated before public exposure (NextAuth, Clerk, or even Basic Auth / a shared password to start).
- **Replace the data layer.** `lib/api.js` stops pointing at FastAPI and instead calls the new server actions. Pages keep their UI; only the fetch layer changes.

This requires a **Next.js Node service on Render** (not a static site), because of the server-side Turso layer.

## 2. Three categories of endpoint

| Category | Hosted replacement |
|---|---|
| **READ** | Server-side Turso `SELECT`. Direct. |
| **CONFIG-WRITE** | Server-side Turso `INSERT/UPDATE/DELETE`. Direct. The Mac re-reads config each cycle. |
| **EXECUTION** | **Cannot run on Render.** Either (a) **DROP** from the hosted UI, or (b) **COMMAND-QUEUE**: write an intent row to Turso that the Mac polls and executes when awake. |

## 3. Data that is NOT in Turso → hide/disable on hosted

- **India MCA leads** — `vw_qualified_leads` + `company_data`/`nic_master` are local-only (814 MB). Any India read returns empty on Turso (already guarded by `_india_unavailable()`). The hosted dashboard is **US-only**.
- **`bayesian_model_state.json`** — ✅ **RESOLVED.** `bayesian_engine.py:save_state()` now mirrors `reputation` + `history` into a Turso `bayesian_state` table, and `/api/analytics/bayesian` reads deliverability from Turso (falls back to the file only for local dev). The Bayesian panel is **kept** and is now Mac-independent. (`variants` and `reply_stats` were already pure `outreach_analytics` reads.)
- **`us_leads.db` corpus count** — used by `orchestrator.status()`. Have the orchestrator write `corpus_count` into `us_scheduler_config` each cycle so the hosted status card can show it.
- **`preview-next-email`, `campaign_engine`, pixel checks, SMTP, Google Places API, Gmail/AI summarize** — Mac-only execution (see §5).

## 4. Per-page audit + Turso replacement

Legend: ✅ Turso-ready · ⚙️ config-write to Turso · 🟥 execution (drop or command-queue) · 🇮🇳 India-only (empty on Turso)

### Home — `app/page.jsx`
| Call | Class | Turso replacement |
|---|---|---|
| `GET /pipeline/status` | READ | `SELECT` counts from `company_enrichment` (US via `Lead_Source='US_Apollo'`); skip the `vw_qualified_leads` (India) part ✅ |
| `GET /analytics/overview` | READ | aggregate `outreach_analytics` ✅ |
| `GET /pipeline/scheduler/status` | READ | `scheduler_config` + `outreach_analytics` ✅ |

### Layout — `app/layout.jsx`
| `GET /health` | READ | Replace with heartbeat read: `mac_heartbeat` age < 3 min → online ✅ (this is the "MacBook Online/Offline" signal) |

### Leads — `app/leads/page.jsx` (US only on hosted)
| `GET /leads?params` | READ | `company_enrichment WHERE Lead_Source='US_Apollo'` + `company_contacts` count ✅ |
| `GET /leads/{cin}` | READ | `company_enrichment` + `company_contacts` + `outreach_analytics` for US CIN ✅ |
| `GET /leads/statuses` | READ | `GROUP BY Pipeline_Status` on `company_enrichment` ✅ |
| `GET /leads/segments` | READ | 🇮🇳 empty — hide the India segment filter |
| `PATCH /leads/{cin}/website` | CONFIG | `UPDATE company_enrichment SET Website_URL` ⚙️ |

### Contacts — `app/contacts/page.jsx`
| `GET /us-outreach/contacts` | READ | join `company_contacts`+`company_enrichment`+`outreach_analytics` (US) ✅ (skip `ensure_contact_columns` — columns already exist in Turso) |
| `PATCH /us-outreach/contacts/{id}/notes` | CONFIG | `UPDATE company_contacts` ⚙️ |
| `GET/POST/PATCH/DELETE /contacts/{cin}*` | READ/CONFIG | `company_contacts` CRUD ✅⚙️ |
| `PATCH /contacts/{cin}/skip` | CONFIG | `UPDATE company_enrichment SET Pipeline_Status='No_Contact_Found'` ⚙️ |
| `POST /contacts/bulk` | CONFIG | validate CINs against `company_enrichment` (not `vw_qualified_leads`) + insert `company_contacts` ⚙️ |
| `GET /leads/queue/next` | READ | 🇮🇳 empty — India queue; hide on hosted |
| `POST /us-outreach/contacts/{cin}/summarize` | EXEC | 🟥 Gmail+AI on Mac → command-queue or drop |

### Campaigns — `app/campaigns/page.jsx` (fully Turso)
| `GET /campaigns?country` | READ | `campaign_templates` (filter `us_` prefix) ✅ |
| `GET /campaigns/{id}` | READ | `campaign_templates` ✅ |
| `PATCH /campaigns/{id}` | CONFIG | `UPDATE campaign_templates` ⚙️ |
| `POST /campaigns/preview` | READ | reimplement `{var}` substitution in the server layer ✅ |
| `POST /campaigns/ab-promote` | CONFIG | `UPDATE campaign_templates SET Is_Active=0` on loser ⚙️ |

### Analytics — `app/analytics/page.jsx`
| `GET /analytics/overview,by-variant,by-batch,timeline,ab-tests` | READ | SQL aggregations on `outreach_analytics` ✅. `ab-tests` z-test math → reimplement in server JS |
| `GET /analytics/bayesian` | READ | ✅ done — reads `bayesian_state` (Turso) for deliverability; `variants`/`reply_stats` from `outreach_analytics`. Panel kept. |
| `GET /pipeline/scheduler/status` | READ | as Home ✅ |
| `POST /campaigns/ab-promote` | CONFIG | as Campaigns ⚙️ |

### US Outreach — `app/us-outreach/page.jsx` ← most important hosted page
| `GET /us-outreach/status` | (was EXEC) | **Reconstruct from Turso:** `us_scheduler_config` (mode, enabled, last_cycle_at, window), `us_alerts` (alerts), `outreach_analytics` (sent/warmup). Corpus count: add `corpus_count` to `us_scheduler_config` (orchestrator writes it). ✅ |
| `GET /us-outreach/config` | (was EXEC) | `SELECT * FROM us_scheduler_config` ✅ |
| `PATCH /us-outreach/config` | (was EXEC) | `UPDATE us_scheduler_config` ⚙️ — Mac re-reads next cycle (verified) |
| `GET /us-outreach/test-emails` | READ | `us_test_emails` ✅ |
| `POST/DELETE /us-outreach/test-emails` | CONFIG | `us_test_emails` insert/delete ⚙️ |
| `POST /us-outreach/run-once` | EXEC | 🟥 trigger a cycle → **command-queue** (insert intent; Mac runs it) |

### Phone — `app/phone/*`
| `GET /places/with-interactions/list` | READ | `places_leads`+`company_enrichment`+`lead_interactions` ✅ |
| `GET/POST/DELETE /interactions/{cin}` | READ/CONFIG | `lead_interactions` CRUD ✅⚙️ |
| `POST /places/recheck-pixel/{cin}` | EXEC | 🟥 pixel check on Mac → command-queue or drop |

### Discover — `app/discover/*`
| `GET /discover/summary` | READ | `bulk_run_queries`+`discover_jobs` ✅ |
| `GET /discover/check-keyword` | READ | `bulk_run_queries` ✅ |
| `GET /discover/jobs/{id}` | READ | `discover_jobs` ✅ (poll) |
| `POST /discover/run` | EXEC | 🟥 Google Places API on Mac → **command-queue** (`discover_jobs` already is a job table — insert a `pending` job; Mac executes) |

### Pipeline (India MCA) — `app/pipeline/page.jsx` + `components/QueuePanel.jsx`
This page drives the **India** MCA pipeline + send queue. Given the US pivot and that India data isn't in Turso, **recommend hiding this page on the hosted dashboard.**
| `GET /pipeline/status,history` , `GET /queue/calendar,status` | READ | partly 🇮🇳; pipeline_runs/send_queue/outreach_analytics parts ✅ |
| `GET /pipeline/preview-next-email` | READ | 🟥 imports `campaign_engine`/`bayesian` + `vw_qualified_leads` → drop |
| `POST /pipeline/run`, `POST /pipeline/scheduler/send`, `POST /queue/force-send` | EXEC | 🟥 India sends on Mac → drop on hosted |
| `POST /queue/pause,resume`, `PATCH /queue/config`, `DELETE clear-failed/cancel-queued` | CONFIG | `scheduler_config`/`send_queue` ⚙️ (if you keep India queue control) |
| `POST /queue/schedule` | CONFIG | reads `vw_qualified_leads` 🇮🇳 → drop/adapt |

## 5. Execution actions — decision table (drop vs command-queue)

These cannot run on Render. Recommended disposition for a **US-focused hosted v1**:

| Action | Recommendation |
|---|---|
| `us-outreach/run-once` (trigger a US cycle) | **Command-queue** — worth remote-triggering |
| `discover/run` (Places search) | **Command-queue** (uses existing `discover_jobs`) |
| `places/recheck-pixel*` | Drop from hosted v1 (keep on local dashboard) |
| `contacts/{cin}/summarize` (Gmail+AI) | Drop from hosted v1 |
| `pipeline/run`, `pipeline/scheduler/send`, `queue/force-send`, `places/search` | Drop (India / heavy; run from the Mac) |

**Command-queue pattern (only if you want remote-triggered actions):** add one Turso table

```sql
CREATE TABLE command_queue (
  ID INTEGER PRIMARY KEY AUTOINCREMENT,
  Action TEXT,              -- 'run_once' | 'discover' | ...
  Payload TEXT,             -- JSON args
  Status TEXT DEFAULT 'pending',   -- pending | running | done | failed
  Requested_At TEXT, Started_At TEXT, Finished_At TEXT, Result TEXT
);
```
Dashboard inserts a `pending` row. A small poller on the Mac (fold into `tick.sh` / launchd) claims `pending` rows, executes the real function (`orchestrator.run_cycle`, discovery, …), and updates `Status`. The dashboard shows status by reading the row. Async by nature — the Mac acts when awake.

## 6. Tables: already in Turso vs new

- **Already in Turso (no work):** `company_enrichment`, `company_contacts`, `outreach_analytics`, `campaign_templates`, `places_leads`, `lead_interactions`, `discover_jobs`, `bulk_run_queries`, `scheduler_config`, `us_scheduler_config`, `us_alerts`, `us_test_emails`, `pipeline_runs`, `mac_heartbeat`, `tracking_sync_heartbeat`, `send_queue`.
- **New / additions:** `command_queue` (if doing remote actions); `us_scheduler_config.corpus_count` (orchestrator writes it); optional `bayesian_state` table (if you want the bayesian panel hosted).
- **Out of scope:** open/click/unsubscribe tracking endpoints (`/api/analytics/track/*`) are hit by *email recipients*, not the dashboard. They're served via `clickcatalyst.digital` + Firestore and synced into Turso by `sync_outreach_tracking.py` — unrelated to this migration.

## 7. Phased rollout

1. **Infra:** Next.js Node service on Render + server-side Turso client (`@libsql/client`, server env vars) + auth gate. Decommission the Render FastAPI service.
2. **Read pages (US):** Home, Layout heartbeat, US Leads, Contacts, Campaigns, Analytics (minus bayesian), Phone/Places, Discover summary, Status. Swap `lib/api.js` calls to server actions.
3. **Config writes:** website edit, contact CRUD, campaign edits, `us_scheduler_config` (mode/test/prod toggles), test-emails, interactions, scheduler config.
4. **Command-queue (optional):** `us-outreach/run-once` + `discover/run`; add the Mac poller.
5. **Hide on hosted:** India Pipeline page, India leads/segments/queue, bayesian panel (until its state is in Turso), all dropped execution buttons.

## 8b. Page-by-page hosted status (final)

Infrastructure now in place: `bayesian_state` (Turso), `command_queue` + `command_worker.py` (run_once + discover via `discover_jobs`), `us_scheduler_config.corpus_remaining` / `reveals_this_month` snapshot. With those, every page resolves to one of: **✅ works immediately from Turso**, **✅ works (with a triggered action via command-queue)**, or **🚫 hidden** (local dashboard / Mac only).

### ✅ Works immediately from Turso (the US control panel)

| Page | Source tables (Turso) | Notes |
|---|---|---|
| **Layout / heartbeat** | `mac_heartbeat` | MacBook Online/Offline (< 3 min) |
| **Home `/`** | `company_enrichment`, `outreach_analytics`, `scheduler_config` | US summary counts; India part returns empty |
| **Leads `/leads`** | `company_enrichment`, `company_contacts`, `outreach_analytics` | **US-only**; hide India segment filter; website edit = config-write |
| **Contacts `/contacts`** | `company_contacts`, `company_enrichment`, `outreach_analytics` | US contact CRUD + notes; **hide** the summarize button + India `queue/next` |
| **Campaigns `/campaigns`** | `campaign_templates` | full; `preview` = reimplement `{var}` substitution server-side; ab-promote = config-write |
| **Analytics `/analytics`** | `outreach_analytics`, `bayesian_state` | full incl. **Bayesian panel** (now Turso-backed); ab-tests z-test math reimplemented server-side |
| **US Outreach `/us-outreach`** | `us_scheduler_config`, `us_alerts`, `us_test_emails`, `outreach_analytics` | **the key page** — status reconstructed from these + `corpus_remaining`/`reveals_this_month` snapshot; config + test-emails = config-write |
| **Info `/info`** | none | static |

### ✅ Works via command-queue (dashboard writes intent, Mac executes)

| Page / action | Mechanism |
|---|---|
| **US Outreach → Run Once** | insert `command_queue(Action='run_once')`; `command_worker` runs `orchestrator.run_cycle(force=True)` next tick |
| **Discover `/discover`** | reads (`bulk_run_queries`, `discover_jobs`) work from Turso; **Run** inserts a `pending discover_jobs` row; `command_worker` executes it on the Mac. ⚠️ Discover produces *Places* leads, whose browsing pages are hidden (below) — confirm you still want Discover on hosted, since results are only viewable on the local dashboard. |

### 🚫 Hidden on hosted (local dashboard / Mac only)

| Page / control | Why |
|---|---|
| **Pipeline `/pipeline`** + `QueuePanel` | India MCA pipeline + SMTP sends (`pipeline/run`, `scheduler/send`, `queue/force-send`) — India data not in Turso, execution is Mac-only |
| **Phone `/phone`** | Places calling workflow + `recheck-pixel` (Places + pixel checker — hidden) |
| **Places browsing** | `places/search` + Places reads — hidden per decision |
| Contacts → **Summarize** button | Gmail + AI execution (Mac-only) |
| Leads → **India segment filter**, Contacts → **India queue** | India MCA (`vw_qualified_leads`) not in Turso |
| Any **force-send / pixel / SMTP** trigger | Mac-only execution |

## 8. Locked decisions

1. **Auth:** Basic Auth for now.
2. **Command-queue:** ONLY `us-outreach/run-once` and `discover/run`. Everything else execution-related is dropped/hidden on hosted.
3. **Keep the local FastAPI dashboard** as the at-the-Mac power tool (full execution). Hosted = Turso-only control panel.
4. **Bayesian panel:** ✅ kept and migrated to Turso (`bayesian_state`) — see §3/§4. Done.

**Explicitly NOT migrated / HIDDEN on the hosted dashboard** (run only from the local dashboard / Mac):
- India MCA pipeline page + all India MCA functionality (`vw_qualified_leads`, `pipeline/run`, `pipeline/scheduler/send`, India `queue/*`, `pipeline/preview-next-email`).
- Places search + Places pages (`places/search`, `places/*` reads that drive Places workflow).
- Pixel checker (`places/recheck-pixel*`).
- Gmail/AI execution (`us-outreach/contacts/{cin}/summarize`).
- SMTP execution (`queue/force-send`, any direct send).
