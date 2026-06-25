# ClickCatalyst Outreach Pipeline — Codebase Reference

> Optimized for AI agents. Skip to any section by header. Do not re-scan files covered here.

---

## Project Identity

**Product**: ClickCatalyst — cold outreach system targeting Indian companies running Google Ads  
**Goal**: Find leads from MCA company registry → find their website → confirm Google Ads pixel → generate personalized competitive intel → send cold email  
**Stack**: Python 3.10 · SQLite · FastAPI · Next.js 14 · Streamlit  
**Brand URL**: `clickcatalyst.digital`  
**Sender**: `Pujan from ClickCatalyst` / `pujan@clickcatalyst.digital`

> **Strategic pivot (2026-06):** active outreach is now **US digital agencies sourced via Apollo** (`us_lead_engine/`). The original India MCA pipeline (documented below) is **frozen / local-only** — its ~814 MB MCA tables (`company_data`, `nic_master`, `vw_qualified_leads`) live only on the Mac and are intentionally NOT in Turso.

---

## Current Architecture & Operations (updated 2026-06-25)

**Mac executes · Turso is shared state · Render shows it:**
```
Render (Next.js dashboard, US-only) ──read/write──► Turso ◄──read/write── Mac (workers + launchd + local FastAPI)
                                                      │
                                          Apollo · Gmail · Firestore tracking
```
- **Turso** (`libsql://cat-mail-db-pujan.aws-ap-south-1.turso.io`) is the single shared DB. `db_factory.connect()` → Turso when `TURSO_URL`+`TURSO_AUTH_TOKEN` are set, else local SQLite. Driver: **`libsql`** (NOT libsql-client / pyturso). Workers route their MAIN-DB access through `db_factory` (`us_lead_engine/orchestrator.py`, `sender.py`, `sync_outreach_tracking.py`, `reply_tracker.py`, `bayesian_engine.py`). The `us_leads.db` Apollo corpus + India scripts stay raw-`sqlite3` / local.
- **Mac** runs all execution: US engine + tracking sync + reply tracker, plus a **local-only FastAPI** (`api/` — the "power tool": full India/Places/execution; never deployed). Two launchd jobs (`scripts/*.plist`, installed in `~/Library/LaunchAgents`):
  - `com.clickcatalyst.heartbeat` (60s) → `heartbeat.py` upserts `mac_heartbeat` in Turso (liveness).
  - `com.clickcatalyst.us` (20 min) → `scripts/tick.sh` runs orchestrator + sync + replies + `command_worker.py` once each (resilient; `RunAtLoad`).
- **Render** hosts ONLY the Next.js dashboard (`dashboard/`), **US-only** (`NEXT_PUBLIC_HOSTED=true`), behind **Basic Auth** (`dashboard/middleware.js`). It reaches Turso through **server-side Next.js route handlers** in `dashboard/app/api/**` (`@libsql/client`, token in server env) — NOT FastAPI. Client API base resolves at runtime (`NEXT_PUBLIC_API_URL` → else localhost⇒FastAPI / deployed⇒`/api`).
- **Command queue:** the hosted dashboard can't execute on the Mac, so "Run cycle now" / "Discover" insert a `command_queue` (or pending `discover_jobs`) row in Turso; `command_worker.py` (run by `tick.sh`) drains and executes them.
- **Observability:** `/api/system-health` aggregates heartbeats + funnel; `/system` page = green/red board; `npm run verify` (endpoint availability) + `npm run doctor` (business-pipeline board). Funnel: Generated→Qualified→Ready→Sent→Opened→Clicked→Replied.

**New Turso tables (beyond the originals):** `mac_heartbeat`, `command_queue`, `bayesian_state` (deliverability mirror), `us_scheduler_config` (US engine config incl. `last_cycle_at`, `corpus_remaining`, `reveals_this_month` snapshot), `us_alerts`, `us_test_emails`, `tracking_sync_heartbeat`.

**Test vs prod isolation:** US test sends use `Batch_ID` prefix `ustest` and write ONLY `outreach_analytics` rows — they never set `company_enrichment.Email_Sent_Date` / `Pipeline_Status`. Every analytics query + the funnel exclude `Batch_ID LIKE 'ustest%'`, so test sends never pollute analytics.

**Env vars (current):** `TURSO_URL`, `TURSO_AUTH_TOKEN` (Mac `.env` + Render); dashboard build: `NEXT_PUBLIC_API_URL=/api`, `NEXT_PUBLIC_HOSTED=true`, `BASIC_AUTH_USER`, `BASIC_AUTH_PASS`; workers: `DB_PATH`, `SENDER_EMAIL`/`SENDER_APP_PASS`, `OPENROUTER_API_KEY`, `FIREBASE_CREDENTIALS_PATH`, Gmail `credentials.json`/`token.json`.

---

## Database

**Single SQLite file — external to this repo:**
```
/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db
```
Overridable via `DB_PATH` env var. All scripts hardcode or read this path.

### Key Tables

| Table | Purpose |
|---|---|
| `vw_qualified_leads` | View: pre-filtered ICP leads from raw MCA data. Has `CIN`, `CompanyName`, `State`, `PaidupCapital`, `RegistrationDate`, `nic_code`, `ICP_Segment` |
| `company_enrichment` | One row per CIN. Tracks pipeline progress, website URL, pixel status, email sent date, unsubscribe state |
| `company_contacts` | Manually-entered contacts (name, email, job title, LinkedIn). `Is_Primary_Contact=1` → who gets the email |
| `competitor_analysis_data` | Scatter plot data per target CIN: target + all competitor rows with capital, age, pixel status |
| `outreach_analytics` | One row per email sent. Tracks opens, clicks, replies, bounces, variant, batch |
| `campaign_templates` | Email HTML/plain/subject per `Variant_Key`. A/B pairs end in `_a` / `_b` |
| `pipeline_runs` | Log of API-triggered pipeline runs (stage, status, timestamps) |
| `send_queue` | Queue for async email dispatch via `queue_worker.py` |
| `scheduler_config` | KV store: `start_hour`, `end_hour`, `send_days`, `default_strategy`, `force_test_mode`, etc. |
| `bulk_run_queries` | Logs every Places search (query, city, leads returned) for quota tracking |
| `discover_jobs` | Async job records for UI-triggered Places searches |
| `places_leads` | Leads from Google Places API. CIN is synthetic: `PLACES_<place_id>` |
| `lead_interactions` | Free-text call/contact log for places leads |
| `nic_master` | NIC code descriptions (join on `nic_code_5d`) |

### `company_enrichment` Pipeline Status Values (ordered)
`Enriched_Ready` → `Intelligence_Ready` → `Outreach_Sent`  
Also: `No_Contact_Found`, `Hard_Bounce`, `Unsubscribed`, `Places_Discovered`, `Replied_Ads_Extracted`

### ICP Segments (from `vw_qualified_leads.ICP_Segment`)
- `Tier 1: Brand - High Intent (Direct Buyers)` — main target
- Golden Lead = Tier 1 + `Has_Google_Ads_Pixel = 1`

---

## Core 4-Stage Pipeline

Entry point: `main.py` — interactive CLI that orchestrates stages sequentially.  
Each stage can be run standalone via its `run_*_batch()` function.

### Stage 1 — Domain Finder (`domain_extractor_01.py`)

**Input**: `vw_qualified_leads` WHERE `ICP_Segment = Tier 1` AND no website yet AND `Enrichment_Attempts < 5`  
**Output**: Writes `Website_URL`, `Domain_Source`, `Has_GMB`, `Pipeline_Status = 'Enriched_Ready'` to `company_enrichment`

**3-layer search:**
1. **Google Places API** (new API) — best source, returns GMB profile + website
2. **DuckDuckGo HTML scraper** — fallback, scrapes `html.duckduckgo.com`
3. **Serper.dev** — paid Google search API, last resort

**Filtering logic** (applied to all layers):
- `B2B_BLACKLIST`: 30+ aggregator/directory domains blocked (LinkedIn, JustDial, Zaubacorp, etc.)
- `NON_COMMERCIAL_SUFFIXES`: `.gov.in`, `.edu.in` blocked
- `passes_bouncer_check()`: domain name must resemble company name (prevents Google autocorrect hallucinations)
- `is_domain_related_to_company()`: word overlap or acronym match

**Domain swap map** (`PARENT_TO_CHILD_DOMAIN`): Intercepts corporate holding domains and swaps to ad-spending consumer brand (e.g., `bundl.com` → `swiggy.com`, `one97.com` → `paytm.com`). 24 entries hardcoded.

**Key functions**: `clean_company_name()`, `master_domain_finder()`, `run_enrichment_batch(batch_size=50)`

---

### Stage 2 — Pixel Checker (`pixel_checker_02.py`)

**Input**: `company_enrichment` WHERE `Website_URL IS NOT NULL` AND `Has_Google_Ads_Pixel IS NULL`  
**Output**: Updates `Has_Google_Ads_Pixel` (1 / 0 / NULL = unreachable, will retry)

**Detection strategy (3 steps per URL):**
1. Fetch HTML (follows redirects, https→http fallback)
2. Scan `<head>` first (fast path), then full HTML: look for `googletagmanager.com/gtag/js` or `AW-[0-9]{7,}` regex
3. If GTM container found: fetch `https://www.googletagmanager.com/gtm.js?id=GTM-XXX` and scan for `awct`, `googtag`, `google_ads`, `aw-conversion`, `adwords`

**Concurrency**: `ThreadPoolExecutor(max_workers=10)` by default — all URLs fetched in parallel  
**Key function**: `run_pixel_batch(max_workers=10, batch_size=50)`

---

### Stage 3 — Intelligence Engine (`competition_intel_03.py`)

**Input**: Golden Leads (`vw_qualified_leads` WHERE `ICP_Segment=Tier1` AND `Has_Google_Ads_Pixel=1` AND `Pipeline_Status IN (Enriched_Ready, NULL)`)  
**Output**: Populates `competitor_analysis_data` table, sets `Competitor_Count`, `Personalized_Sentence`, `Pipeline_Status='Intelligence_Ready'`

**What it does per lead:**
1. `get_competitor_intelligence(cin)`: SQL query finds competitors in same State + NIC code + ±50% capital + registered within ±365 days. Generates a personalized email sentence naming the competitor count.
2. `save_competitor_scatter_data()`: Writes target + all competitors to `competitor_analysis_data` with capital, age, pixel status, benchmark average. Used by visualizer.
3. `log_outreach_intelligence()`: Updates `company_enrichment` with count + sentence.

**Fallback**: If no competitors found, uses generic industry benchmark sentence.

---

### Stage 4 — Email Dispatch (`email_engine_04.py`)

**Input**: `company_enrichment WHERE Pipeline_Status = 'Intelligence_Ready'`  
**Output**: Sends emails via Gmail SMTP SSL (port 465), updates `outreach_analytics`, sets `Pipeline_Status = 'Outreach_Sent'`

**Per-email flow:**
1. Build UTM audit URL (`clickcatalyst.digital/free-audit?utm_...`)
2. Build tracking pixel URL + click redirect URL (via `/api/track/`)
3. Call `visualizer.generate_scatter_plot(cin)` → returns `BytesIO` PNG
4. Pick campaign variant via `get_campaign_variant(lead_info)` → NIC-code routing
5. Thompson Sampling override: `select_variant_thompson(variant_base, cin)` from `bayesian_engine.py` (falls back to deterministic A/B if no data)
6. Fetch template from `campaign_templates` DB; do string replace `{variable}` substitution
7. Recipient: `company_contacts WHERE Is_Primary_Contact = 1`; falls back to `recipient_email_override` (test mode)
8. Send `MIMEMultipart('related')` with inline scatter plot PNG (Content-ID: `scatter_{cin}`)
9. Log to `outreach_analytics`, mark `Outreach_Sent`
10. Random delay 30–90s between sends (human-like)

**Bounce handling**: Hard bounce signals (550/user unknown/etc.) → sets `Pipeline_Status = 'Hard_Bounce'`, labels contact as `'Bounced'`. Soft bounce → logs `Last_Error`, retries next run.

**Test mode**: `recipient_email_override='you@gmail.com'` sends all to your inbox. Prompted interactively by `main.py`.

**Env vars**: `SENDER_EMAIL`, `SENDER_APP_PASS`

---

## Visualizer (`visualizer.py`)

Generates the scatter plot attached inline in every email.

- **X-axis**: Company age in days  
- **Y-axis**: Paid-up capital (₹)  
- **Target lead**: Bold navy star (★)  
- **Competitors with ads**: Red dots  
- **Competitors no ads**: Light grey dots  
- **Competitors unknown**: Mid grey dots  
- **Benchmark line**: Dashed grey = cohort average capital

Data source: `competitor_analysis_data WHERE Target_CIN = ?`  
Saves PNG to `output/plots/{cin}_{date}.png` AND returns `BytesIO` for email attachment.  
Uses matplotlib with `Agg` backend (non-interactive, safe for server).

---

## Campaign Variant System (`api/campaign_engine.py`)

**NIC code → variant routing:**
| NIC | Variant base |
|---|---|
| 47910 (e-commerce) | `ecomm_pmax_v1` or `ecomm_pmax_gmb_v1` or `ecomm_pmax_competitive_v1` |
| 62000 (software/SaaS) | `saas_funnel_v1` or `saas_funnel_competitive_v1` |
| 73100/73200/73101/73210 (agency) | `agency_whitelabel_v1` |
| 70200 (consulting) | `consulting_generic_v1` |
| anything else | `generic_audit_v1` |

`get_ab_variant(cin, base)` → deterministic A/B by CIN character sum % 2 → `base_a` or `base_b`  
`seed_default_templates(conn)` → inserts 10 default templates if table empty (called on startup)

**Template variables**: `{company_name}`, `{personalized_sentence}`, `{audit_url}`, `{competitor_count}`, `{tracking_pixel_url}`, `{unsubscribe_url}`

---

## Bayesian Engine (`bayesian_engine.py`)

Two independent models. Used by `email_engine_04.py` and `queue_worker.py`.

### 1. Thompson Sampling (`ThompsonSampler`)
- Maintains Beta(alpha, beta) posteriors per variant key loaded from `outreach_analytics`
- Success metric: `click` (default), `reply`, or `conversion`
- `select_variant_thompson(variant_base, cin, metric='click')` → replaces `get_ab_variant()`
- Falls back to deterministic split if no data for either variant yet
- State: re-computed from DB on each call (no persistence needed)

### 2. Deliverability Estimator (`DeliverabilityEstimator`)
- Tracks domain reputation [0,1] via exponential moving average: `rep = 0.8 * rep + 0.2 * signal`
- Signal = weighted combo: open rate (0.10), reply rate (0.35), click rate (0.15), (1 - bounce rate) (0.15), (1 - unsub rate) (0.10), conversion rate (0.15) - volume penalty
- Persisted to `bayesian_model_state.json` (project root)
- `should_send_today()` → returns (bool, reason, score); blocks sends if reputation < 0.2
- `get_volume_adjustment()` → 1.0 at rep ≥ 0.7, scales down to 0.0 at rep < 0.3

**CLI**: `python bayesian_engine.py [--update] [--recommend N] [--deliverability] [--metric click|reply|conversion]`

---

## Queue System (`queue_worker.py`)

Separates "schedule" from "send" — UI schedules into `send_queue`, worker drains it.

**`process_queue()`** checks in order:
1. `auto_send_enabled` config flag
2. Send window (weekday, business hours from `scheduler_config`)
3. Warmup daily limit (ramp: 5→10→20→35→50→75→100 over 60+ days)
4. Bayesian deliverability gate
5. Peak-hour vs off-peak cycle sizing

**Warmup ramp** (days since first email sent):
```
0-3: 5/day | 4-7: 10 | 8-14: 20 | 15-21: 35 | 22-30: 50 | 31-60: 75 | 61+: 100
```

**CLI**: `python queue_worker.py [--daemon] [--status] [--once]`  
Daemon mode: reads `send_interval_minutes` from config (default 15) and polls.

---

## Send Scheduler (`send_scheduler.py`)

Decides when to send, wraps `email_engine_04.py`.  
Uses same warmup ramp as queue worker.  
Send window: IST 9:00–17:00 Mon–Fri. Peak hours: 10, 11, 14, 15.  
`get_time_performance()` analyzes historical `Send_Hour` / `Send_DayOfWeek` columns in `outreach_analytics`.

**CLI**: `python send_scheduler.py [--execute] [--plan-week] [--time-stats]`

---

## Reply Tracker (`reply_tracker.py`)

Polls Gmail API for replies to sent outreach emails.  
Auth: OAuth2 via `credentials.json` + `token.json` (Gmail read-only scope).  
Searches Gmail for messages from each lead's email address with matching subject line, sent after the outreach date.  
On reply found: sets `Reply_Received=1`, `Reply_Date=now` in `outreach_analytics`.

**CLI**: `python reply_tracker.py [--daemon]` — daemon polls every 600s

---

## Firestore Sync (`sync_outreach_tracking.py`)

Pulls tracking events (open/click/unsubscribe/conversion) from Firestore collection `outreach_tracking` into SQLite.  
Events have `synced=false` flag; script marks them `synced=true` after processing.  
Firebase credentials: `GOOGLE_APPLICATION_CREDENTIALS` or `FIREBASE_CREDENTIALS_PATH` env var.

**Event handlers**: `open` → `Email_Opened=1`, `click` → `Audit_Link_Clicked=1`, `unsubscribe` → `Unsubscribed=1 + Pipeline_Status='Unsubscribed'`, `conversion` → `Converted=1`

**CLI**: `python sync_outreach_tracking.py [--dry-run] [--daemon]`

---

## Contact Entry App (`collector_app.py`)

Streamlit app (`streamlit run collector_app.py`) for human-in-the-loop contact discovery.

**Modes:**
- **Queue mode**: Auto-loads next `Intelligence_Ready` company with no contacts; researcher fills in name/email/title/LinkedIn
- **Search mode**: Search by CIN or company name, add contacts to any company

**Actions per lead**: Save & Next, Add Another (stay on lead), Skip (sets `No_Contact_Found`), Update Website URL (manual override)

**Contact form fields**: First name, Last name, Job title (dropdown), Email type (dropdown), Email address, LinkedIn URL, Is Primary (checkbox)

---

## On-Demand Warm Lead Script (`on-demand-warm-lead-show-ads-script.py`)

One-off utility for generating follow-up replies to warm leads (when someone replies to cold email).  
Uses SerpAPI `google_ads_transparency_center` engine to fetch live ads for the company.  
Requires: `SERPAPI_KEY` (100 credits/month free tier).  
Outputs a ready-to-send follow-up email template to stdout.  
`generate_warm_followup(cin)` — pass CIN of the warm lead.

---

## FastAPI Backend (`api/`)

**Start**: `uvicorn api.main:app --reload --port 8000`  
**CORS**: `localhost:3000` only  
**DB**: `api/database.py` → `get_conn()` — returns `sqlite3.Connection` with `row_factory = sqlite3.Row`

### Route Map

| Prefix | File | Key endpoints |
|---|---|---|
| `/api/pipeline` | `routes/pipeline.py` | `POST /run` (trigger stage, returns run_id), `GET /stream/{run_id}` (SSE log stream), `GET /status` (counts per stage), `GET /history`, `GET /scheduler/status`, `POST /scheduler/send`, `GET /scheduler/week-plan`, `PATCH /scheduler/config`, `GET /preview-next-email` |
| `/api/leads` | `routes/leads.py` | `GET /` (paginated, filters: segment/status/search), `GET /segments`, `GET /statuses`, `GET /{cin}` (detail + contacts + outreach history), `PATCH /{cin}/website`, `GET /queue/next` |
| `/api/contacts` | `routes/contacts.py` | `GET /{cin}`, `POST /{cin}` (add), `PATCH /{cin}/primary/{contact_id}`, `DELETE /{cin}/{contact_id}`, `PATCH /{cin}/skip`, `POST /bulk` (CSV import) |
| `/api/campaigns` | `routes/campaigns.py` | `GET /` (all templates), `GET /{id}`, `PATCH /{id}` (edit subject/body), `POST /preview` (render with sample vars), `POST /ab-promote` (deactivate losing variant) |
| `/api/analytics` | `routes/analytics.py` | `GET /overview` (totals + rates), `GET /by-variant`, `GET /by-batch`, `GET /timeline` (30d daily), `GET /ab-tests` (z-test with p-value + winner), `GET /track/open?aid=` (pixel, returns 1x1 GIF), `GET /track/click?aid=&url=` (redirect), `GET /unsubscribe?cin=`, `GET /bayesian` (Thompson posteriors + deliverability + reply stats) |
| `/api/places` | `routes/places.py` | `POST /search` (run Places search + persist), `GET /` (list with filters), `GET /{place_id}`, `GET /with-interactions/list` (to_call / contacted tabs), `POST /recheck-pixel/{cin}`, `POST /recheck-pixel/bulk/unchecked` |
| `/api/interactions` | `routes/interactions.py` | `GET /{cin}`, `POST /{cin}` (log interaction), `DELETE /{interaction_id}` |
| `/api/discover` | `routes/discover.py` | `GET /summary` (quota + history + active jobs + cities), `POST /run` (async job, returns job_id immediately), `GET /jobs/{job_id}` (poll status), `GET /check-keyword?query=` |
| `/api/queue` | `routes/queue.py` | `GET /status`, `POST /schedule` (add N leads to queue), `POST /force-send`, `POST /pause`, `POST /resume`, `PATCH /config`, `DELETE /clear-failed`, `DELETE /cancel-queued`, `GET /calendar?days=14` |
| `/api/health` | `main.py` | `{"status": "ok"}` |

### Pipeline SSE Streaming (`routes/pipeline.py`)
`POST /run` → inserts `pipeline_runs` row, spawns thread that calls `run_*_batch()` with stdout redirected to a `queue.Queue`. Returns `run_id`.  
`GET /stream/{run_id}` → SSE endpoint that drains the queue. Sends `{"line": "..."}` events. Sends `{"line": "__DONE__"}` on completion.

---

## Services (`api/services/`)

### `places_service.py`
Wraps Google Places API (new) `searchText` endpoint.  
`GOOGLE_PLACES_API_KEY` env var required.  
Field mask set to minimize billing: id, displayName, formattedAddress, phones, websiteUri, rating, ratingCount, businessStatus, primaryType, types, location, googleMapsUri.  
`normalize_place(raw)` → flat dict with synthetic CIN (`PLACES_<place_id>`), quality score, formatted phone.

### `lead_quality.py`
`score_lead(name, primary_type, types_json, user_rating_count)` → score 0–100.  
+30 for `marketing_consultant` primary type, +20 for PPC keywords in name, −40 for OOH keywords, −25 for non-PPC keywords. +10 for 50+ reviews.  
`format_phone(raw)` → normalizes Indian phone to `XXX-XXX-XXXX`. Strips country code (+91), trunk prefix (0).

### `pixel_service.py` (referenced but not read)
`check_and_persist(cin, url)` → single-lead pixel check + DB write.  
`check_places_leads_batch(cins=None, min_quality=None, only_unchecked=False, max_workers=10)` → batch pixel check for Places leads.

---

## Google Places / Discover System

**Two entry points for Places search:**
1. `POST /api/places/search` — ad-hoc, immediate, returns results
2. `POST /api/discover/run` — async job, returns `job_id` immediately, background task runs search then auto-runs pixel check on new leads

Both persist to `places_leads` + `company_enrichment` (with `Pipeline_Status = 'Places_Discovered'`).  
`configs/cities.json` — city presets with lat/lng/radius for `location_bias`.  
Quota tracking: every successful search logged to `bulk_run_queries`. `GET /api/discover/summary` shows `used_this_month` vs 5000 free tier limit.

---

## Database Migrations (`migrations/`)

Run manually via SQLite CLI in order:

| File | What it adds |
|---|---|
| `001_add_places.sql` | `Phone` column on `company_enrichment`, creates `places_leads` table with all Places columns |
| `002_quality_phone_interactions.sql` | (not read — likely adds `Quality_Score`, `Phone_Formatted`, `lead_interactions` table) |
| `003_bulk_run_history.sql` | (not read — likely adds `bulk_run_queries` table) |
| `004_discover_jobs.sql` | Creates `discover_jobs` table (async search jobs) |
| `005_fix_bulk_run_queries_nullable.sql` | (likely fixes nullable columns in bulk_run_queries) |

---

## Dashboard (`dashboard/`)

**Next.js 14 App Router** at `localhost:3000`.  
**Start**: `cd dashboard && npm run dev`  
API base: `http://localhost:8000`

### Country scope (India / US)
A **global country dropdown** in the sidebar (`layout.jsx`, options India/US) sets `localStorage['cc_country']` and dispatches a `cc-country-change` window event. Pages read `getCountry()` (from `app/lib/api.js`), pass `?country=` to fetches, and re-fetch on the event. Backend: `api/database.py:country_filter(country, cin_col, batch_col)` → SQL fragment (`us` = `CIN LIKE 'APOLLO_%'`, `india` = `NOT LIKE`, plus excludes `ustest` batches). Applied to `/api/leads` (US branch reads company_enrichment, not vw_qualified_leads), `/api/leads/{cin}` (APOLLO_ branch), all `/api/analytics/*`, `/api/pipeline/status`, `/api/campaigns` (US arms = `us_` Variant_Key prefix). Nav hides India-only tabs (Pipeline/Discover/Phone) in US and the US Outreach tab in India. Home gates the India pipeline workflow / scheduler to India and shows a US Outreach pointer. Contacts shows a banner in US (contacts auto-sourced from Apollo; manual queue is India-only).

### Pages
- `/us-outreach` — premium control tower: test/prod toggle, pause/resume, run-once, status cards, alerts, **Schedule controls** (send days, CST window, cycle interval, start date — all override the system defaults via PATCH `/api/us-outreach/config`), test-email mgmt, and a **heartbeat** (`last_cycle_at` from orchestrator status; green=alive, red=daemon stopped).
- `/info` — concise how-to-use reference (country switch, US autonomous loop, control tower, India pipeline, per-tab guide, going-live steps). Shown in both countries.

### Pages

| Route | File | Description |
|---|---|---|
| `/` | `app/page.jsx` | Home / overview |
| `/leads` | `app/leads/page.jsx` | Lead list with segment/status filters |
| `/contacts` | `app/contacts/page.jsx` | Contact management |
| `/pipeline` | `app/pipeline/page.jsx` | Stage runner with live SSE log streaming |
| `/campaigns` | `app/campaigns/page.jsx` | Template editor + A/B test results |
| `/analytics` | `app/analytics/page.jsx` | Send stats, variant performance, Bayesian status |
| `/phone` | `app/phone/page.jsx` | Phone outreach for Places leads (to_call / contacted tabs) |
| `/discover` | `app/discover/page.jsx` | Places search UI with async job polling |

### Components
- `app/components/QueuePanel.jsx` — email queue status panel (queue counts, upcoming sends, schedule controls)
- `app/phone/components/PhoneLeadTable.jsx` — Places leads table for phone tab
- `app/phone/components/InteractionPanel.jsx` — log/view interactions on a lead
- `app/discover/components/SearchForm.jsx` — search input + city picker
- `app/discover/components/QuotaCard.jsx` — quota usage display
- `app/discover/components/SearchHistory.jsx` — past search history

### API Clients
- `app/lib/api.js` — generic API utilities
- `app/phone/lib/api.js` — phone-tab specific API calls
- `app/discover/lib/api.js` — discover-tab specific API calls

---

## Environment Variables

| Var | Used in | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | `domain_extractor_01.py` | Google Places API for domain finding |
| `GOOGLE_PLACES_API_KEY` | `api/services/places_service.py` | Google Places API for lead discovery |
| `SERPER_API` | `domain_extractor_01.py` | Serper.dev Google search (Layer 3 fallback) |
| `SENDER_EMAIL` | `email_engine_04.py`, `queue_worker.py` | Gmail sender address |
| `SENDER_APP_PASS` | `email_engine_04.py`, `queue_worker.py` | Gmail App Password |
| `TEST_EMAIL` | `main.py` | Default test mode recipient |
| `DB_PATH` | All Python files | Override SQLite path |
| `GOOGLE_APPLICATION_CREDENTIALS` | `sync_outreach_tracking.py` | Firebase service account key path |
| `FIREBASE_CREDENTIALS_PATH` | `sync_outreach_tracking.py` | Alternative Firebase key path |
| `GMAIL_CREDENTIALS` | `reply_tracker.py` | Path to OAuth credentials.json |
| `GMAIL_TOKEN` | `reply_tracker.py` | Path to token.json |
| `MODEL_STATE` | `bayesian_engine.py` | Path for bayesian_model_state.json |
| `APOLLO_API_KEY` | `us_lead_engine/apollo_client.py` | Apollo master API key (search needs master) |
| `US_POSTAL_ADDRESS` | `us_lead_engine/sender.py` | CAN-SPAM physical address (required before US live sends) |
| `US_FROM_NAME` | `us_lead_engine/sender.py` | US sender display name (optional) |

Firebase service account key: `keys/tier1-web-firebase-adminsdk-fbsvc-3a34532ca1.json`

---

## Scripts (`scripts/`)

- `scripts/backfill_pixel_check.py` — retroactively runs pixel check on enriched leads
- `scripts/backfill_quality_phone.py` — retroactively scores quality and formats phones for places leads
- `scripts/bulk_runner.py` — batch Places searches from a list of queries

---

## Configs (`configs/`)

- `configs/cities.json` — city presets: `{ "mumbai": { "lat": 19.08, "lng": 72.88, "radius_m": 40000 }, ... }`
- `configs/ppc_india_v1.json` — (likely search query presets for PPC agencies in India)

---

## Data Flow Summary

```
MCA company registry (external DB)
    ↓
vw_qualified_leads (SQL view filters to ICP)
    ↓
Stage 1: domain_extractor_01.py — finds website URL
    ↓
Stage 2: pixel_checker_02.py — confirms Google Ads pixel
    ↓
[Manual: collector_app.py — researcher adds contact email]
    ↓
Stage 3: competition_intel_03.py — finds competitors, generates personalized sentence
    ↓
Stage 4: email_engine_04.py — renders email + scatter plot, sends via Gmail
    ↓
clickcatalyst.digital/api/track/* — pixel/click events → Firestore
    ↓
sync_outreach_tracking.py — syncs Firestore events back to SQLite
    ↓
reply_tracker.py — monitors Gmail inbox for replies
    ↓
outreach_analytics — full funnel data for dashboard
```

**Parallel lead source (Places — phone):**
```
Google Places API → places_leads table → phone outreach tab (manual calls)
```

**Parallel lead source (US — email):** see [US Lead Engine](#us-lead-engine-us_lead_engine)
```
Apollo search → qualify (role) → enrich (email+domain) → pixel check
   → export (APOLLO_<id> into main DB) → sender.py (agency pitch) → outreach_analytics
```

---

## US Lead Engine (`us_lead_engine/`)

**Independent module** that sources US marketing/advertising agency leads from Apollo and exports them into the main pipeline. Strategic pivot from India (MCA data has no emails) → US (Apollo provides verified emails). Built 2026-06; first sends validated (inbox placement confirmed).

**Own SQLite DB:** `us_lead_engine/us_leads.db` (separate from the main MCA DB). Nothing touches the main pipeline until `--export` runs.

### Full loop
```
discover (search, 0 credits) → qualify (role score, free) → reveal (enrich, 1 credit ea)
   → pixel check (post-reveal) → export (to main DB) → send (dedicated US sender)
```

### CLI — `python -m us_lead_engine.run_discovery [flag]`
| Flag | Action | Credits |
|---|---|---|
| `--dry-run` | Apollo search + qualify, persist to us_leads.db | 0 |
| `--enrich N` | reveal emails for top-N qualified (by role score), run pixel check | N |
| `--cost` | spend report from `api_usage_log` | 0 |
| `--export` | push pixel-confirmed, non-catch-all leads to main DB | 0 |
| `--send N [--test EMAIL] [--send-dry]` | send up to N US emails (warmup-capped); `--test` routes all to one address | 0 |

### Files
- `config.py` — `ICP_QUERY` (validated: US agency founders/owners, 11–200 emp, verified email), `MIN_ROLE_SCORE`, Apollo cost table, `MAIN_DB_PATH`. Tech-stack filter is commented out (paid feature).
- `apollo_client.py` — REST wrapper. `search()` = `POST {base}/mixed_people/api_search` (0 credits, masked emails); `enrich()` = `POST {base}/people/match` (1 credit). **Base = `https://api.apollo.io/api/v1`** (NOT `/v1`).
- `role_classifier.py` — rules + Apollo structured `seniority`/`departments`. `classify(title) → (score, label, is_decision_maker)`. No SLM (rules handle "Fractional CMO" etc.).
- `cost_tracker.py` — logs every API call to `api_usage_log` with credits + $; `spend_report()`.
- `db.py` — `get_conn()` for us_leads.db (busy_timeout set). `--init` builds from `schema.sql`.
- `run_discovery.py` — entry point: `run_search`, `qualify`, `run_enrich`, `run_export`.
- `sender.py` — **dedicated US sender** (see below).
- `inspect_raw.py` — throwaway: dumps raw search JSON for field mapping.

### Apollo facts (validated live)
- Search returns only identity + `has_*` boolean flags; **domain/email/location/last-name come only from enrich**.
- Enrich payload is rich: revealed email + `email_status`, `email_domain_catchall` (deliverability flag), org `primary_domain`, `estimated_num_employees`, tech stack (`technology_names` incl. Google Tag Manager), `keywords`, `seniority`/`departments`.
- Free tier ≈ 100 lead credits/month; `api_search` needs a **master** API key. Already-revealed contacts are **not recharged** (`revealed_for_current_team`).
- Tech-stack filters (`currently_using_any_of_technology_uids`) are a **paid** feature (422 on free) — so qualify on role pre-reveal, pixel-check post-reveal.

### Local DB tables (`us_leads.db`)
- `us_leads` — one row per Apollo person. Identity from search; email/domain/location/pixel/catch-all filled at enrich. Lifecycle: `Discovered_At` → `Enriched_At` → `Exported_At`. `Role_Score`/`Role_Label`, `Pixel_Status` (yes/no/unreachable/unchecked), `Email_Catchall`, `Qualified`.
- `api_usage_log` — one row per API call (endpoint, call_type, credits, USD, results).

### Export → main DB
`run_export()` writes pixel-confirmed (`Pixel_Status='yes'`), non-catch-all, enriched leads into the **main** DB:
- `company_enrichment`: synthetic CIN `APOLLO_<person_id>`, `Domain_Source='Apollo'`, `Has_Google_Ads_Pixel=1`, `Pipeline_Status='Intelligence_Ready'`, plus **two additive columns** `Company_Name` and `Lead_Source='US_Apollo'`.
- `company_contacts`: primary contact (name, email, title, LinkedIn).
- Reversible: `DELETE FROM company_contacts/company_enrichment WHERE CIN LIKE 'APOLLO_%';`

### `sender.py` — dedicated US sender
Separate from the MCA scatter-plot engine (which is hardwired to `vw_qualified_leads`). Reads exported leads (`Lead_Source='US_Apollo'`, `Pipeline_Status='Intelligence_Ready'`) from the main DB, sends the **agency white-label pitch** (no scatter plot), logs to `outreach_analytics` (variant `us_agency_whitelabel_v1`) so existing tracking/reply/dashboard work. Own warmup ramp (days since first US send), CAN-SPAM footer, `List-Unsubscribe`. India pipeline untouched.

**US-specific env:** `US_POSTAL_ADDRESS` (CAN-SPAM, required before live sends), `US_FROM_NAME` (optional). Reuses `SENDER_EMAIL`, `SENDER_APP_PASS`, `APOLLO_API_KEY`.

### Copy system (built)
- `product_profile.json` — source of truth for copy (product = Google Ads observability platform / ClickHub; narrative = "Google can't audit its own waste"; funnel: cold email → free PDF audit → ClickHub subscription). Edit this when the product changes.
- `personalization.py` — `build_personalized_line()`: rules-based, scale/size angle (avoids the "you run Google Ads" tautology). Reads signals from us_leads.
- `seed_campaigns.py` — seeds 2 cold-email arms (`us_agency_waste_v1_a/_b`) into `campaign_templates`. Strategy (locked): problem-first, ONE personalized line, free **Efficiency & Waste** audit on a client account, CTA = **reply for a promo code (no link in body)**, pre-launch (no proof claims), Founding Agency offer saved for the reply. Run: `python -m us_lead_engine.run_discovery --seed-campaigns`.
- `sender.py` now: Thompson-selects an arm from `campaign_templates`, injects `{first_name}/{company_name}/{personalized_line}`, appends CAN-SPAM footer + open pixel. 2 arms (not 6) — correct for 5–20/day warmup volume; expand when volume supports it.

### Status (as of 2026-06-20)
**Working & verified:** discover→qualify→reveal→pixel→export→A/B send→orchestrator (scheduled Mon 06-22, deliverability-gated volume, auto-replenish w/ pagination, send-time auto-learning past 150 sends) → control-tower UI (test/prod toggle, schedule controls, heartbeat) → alerts (deliverability, bounce, corpus, credit-cap, apollo, tracking_sync, smtp, replies). **Open-tracking pipeline CONFIRMED LIVE** (prod endpoint + Firestore + `sync_outreach_tracking.py` — processed 7 opens). Country dropdown scopes whole dashboard. Gemma summarization + contact Notes/analytics built. Gmail is the sender, sending stays on the Mac.

### Status (2026-06-25) — autonomous cloud loop live
The 2026-06-20 "cloud migration" (future work #1 below) is **DONE**: Turso is the shared DB, the Next.js dashboard runs on Render (US-only, Basic Auth, server-side Turso route handlers), workers write Turso, FastAPI stays local. The US engine is **autonomous** — `com.clickcatalyst.us` is loaded and ticking every 20 min; verified end-to-end (dashboard config write → orchestrator reads it next cycle → sends → writes Turso → dashboard reflects). Currently in **TEST mode** (5 test inboxes); flip Mode→Prod on the US Outreach page to go live. **Open-tracking live.** **Reply tracking paused** — Gmail refresh token revoked; re-auth via `python reply_tracker.py` (the code now self-heals instead of crashing).

### Immediate manual steps (user)
- **Gmail OAuth for replies:** Google Cloud → enable Gmail API → create OAuth Desktop client → save `credentials.json` at project root → `python reply_tracker.py` once (writes `token.json`). Unblocks reply detection + auto-summaries + green alert.
- Set `OPENROUTER_API_KEY` to activate Gemma summaries.
- Keep `sync_outreach_tracking.py --daemon` running (needs `FIREBASE_CREDENTIALS_PATH`).

### Future work (planned 2026-06-20, to do ~next)
1. ✅ **DONE (2026-06-25) — Cloud migration: dashboard to Render + DB to Turso, cron stays on Mac.** Turso (hosted libSQL) holds the DB; FastAPI + Next.js dashboard deploy to Render (read Turso); the orchestrator/sender/sync/reply daemons keep running on the Mac (Gmail works from residential IP) writing to Turso. **Prereqs:** (a) DB connection factory routing all ~15 `sqlite3.connect` calls through one Turso-capable helper (env-gated, falls back to local) — foundational; (b) Turso provision + data migrate; (c) secret scrub before repo public + API auth; (d) Render deploy. Do NOT move sending off the Mac (Gmail/cloud-SMTP issues; GCP blocks SMTP).
2. **Background cron + log rotation on Mac — BUILT.** `scripts/tick.sh` runs orchestrator + sync + reply ONCE each (resilient: one failing step doesn't stop the others), logs to dated `logs/<name>_YYYY-MM-DD.log`, prunes logs > 7 days. `scripts/com.clickcatalyst.us.plist` = launchd job running it every 20 min (`RunAtLoad` + 20-min interval → also self-heals crashes). Install: `cp scripts/com.clickcatalyst.us.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.clickcatalyst.us.plist`. Secrets load via python-dotenv inside the scripts (config.py / sync / reply call `load_dotenv()`); tick.sh only exports `FIREBASE_CREDENTIALS_PATH`. NOTE: reply_tracker Gmail token expires in OAuth "Testing" mode (~7 days) → publish the OAuth consent screen to Production, or re-auth (`rm token.json && python reply_tracker.py`).
3. **Verify the waste-audit PDF (first impression).** It IS substantially built in `clickcatalyst/frontend`: `/free-google-ads-waste-audit` page, `api/free-audit/waste-summary/route.js` (BigQuery-backed, auth-gated, has a sample-data path), and react-pdf render components (`WasteSynthesisPDF`, `WasteHeatmapPDF`, etc.). **Not yet end-to-end verified** — generate one on the sample dataset or a real connected Google Ads account before sending outreach, since the free waste audit is the offer's first impression.
4. Smaller: promo-code fulfillment process, separate warmed sending domain, pixel `unreachable` retry, richer (org-keyword) personalization, heart-icon for the heartbeat dot, reply-tracker health heartbeat.

---

## Key Invariants for Agents

1. **CIN is the primary key** everywhere. Places leads use synthetic `PLACES_<place_id>` CIN; US Apollo leads use `APOLLO_<person_id>`.
2. **Email only goes to `Is_Primary_Contact = 1`** in `company_contacts`. No contact = no email.
3. **Pipeline status is a state machine** — advancing requires the previous stage to have completed for that CIN.
4. **All batch functions are idempotent** — they skip already-processed CINs.
5. **Template variable substitution** uses `{variable_name}` (curly braces, no dollar sign).
6. **A/B variants are always `{base}_a` and `{base}_b`** — this convention is used everywhere.
7. **`Unsubscribed = 1`** always excludes a lead from further processing (checked in every SQL query).
8. **Warmup day = days since first email in `outreach_analytics`** — used by queue_worker + send_scheduler.
9. **SSE streams** emit `__DONE__` sentinel when complete and `__TIMEOUT__` on 60s idle.
10. **`vw_qualified_leads`** is a view — do not `INSERT` into it. Source data is in a separate MCA table.
