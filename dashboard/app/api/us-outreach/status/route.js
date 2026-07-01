// GET /api/us-outreach/status
// Reconstructs orchestrator.status() from Turso (no Mac contact). Mac-only numbers
// (reveals_this_month) come from the us_scheduler_config snapshot written each cycle.
import { q, q1, scalar, json } from '../../../lib/turso.server'

export const dynamic = 'force-dynamic'  // always live; never static-cache at build

const TEST_BATCH = 'ustest'
// (day_lo, day_hi, daily_limit) — mirrors sender.WARMUP
const WARMUP = [[0, 3, 5], [4, 7, 10], [8, 14, 20], [15, 21, 35], [22, 30, 50], [31, 60, 75], [61, 999, 100]]
const DOW = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 }

// Current time in America/Chicago (CST/CDT), matching the orchestrator's _now_cst.
function chicagoNow() {
  const now = new Date()
  const hour = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'America/Chicago', hour: '2-digit', hourCycle: 'h23' }).format(now))
  const wd = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Chicago', weekday: 'short' }).format(now)
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Chicago' }).format(now) // YYYY-MM-DD
  return { hour, weekday: DOW[wd], wdShort: wd, date }
}

function volMultiplier(rep) {
  if (rep == null) return 1.0
  if (rep >= 0.7) return 1.0
  if (rep >= 0.5) return 0.75
  if (rep >= 0.3) return 0.5
  return 0.0
}

export async function GET() {
  const rows = await q('SELECT Config_Key, Config_Value FROM us_scheduler_config')
  const cfg = {}
  for (const r of rows) cfg[r.Config_Key] = r.Config_Value

  const now = chicagoNow()

  // send window
  const days = (cfg.send_days || '0,1,2,3,4').split(',').filter((x) => x.trim() !== '').map(Number)
  const sh = parseInt(cfg.start_hour ?? '9', 10)
  const eh = parseInt(cfg.end_hour ?? '17', 10)
  let inWindow = true, windowReason = 'in window'
  if (!days.includes(now.weekday)) { inWindow = false; windowReason = `not a send day (${now.wdShort})` }
  else if (now.hour < sh || now.hour >= eh) { inWindow = false; windowReason = `outside window (${now.hour}:00 CST, ${sh}-${eh})` }

  const beforeStart = cfg.start_date ? now.date < cfg.start_date : false

  // warmup day + daily limit (days since first US prod send)
  const first = await scalar(
    `SELECT MIN(oa.Email_Sent_Date) FROM outreach_analytics oa
     JOIN company_enrichment e ON oa.CIN = e.CIN
     WHERE e.Lead_Source = 'US_Apollo' AND oa.Batch_ID NOT LIKE ?`, [TEST_BATCH + '%'])
  let warmupDay = 0
  if (first) warmupDay = Math.max(0, Math.floor((Date.parse(now.date) - Date.parse(first)) / 86400000))
  let dailyLimit = 5
  for (const [lo, hi, lim] of WARMUP) { if (warmupDay >= lo && warmupDay <= hi) { dailyLimit = lim; break } }

  const sentToday = Number(await scalar(
    `SELECT COUNT(*) FROM outreach_analytics oa
     JOIN company_enrichment e ON oa.CIN = e.CIN
     WHERE e.Lead_Source = 'US_Apollo' AND oa.Email_Sent_Date = date('now')
       AND oa.Batch_ID NOT LIKE ?`, [TEST_BATCH + '%'], 0))

  // corpus_remaining: Turso-derivable (prefer fresh SQL over the snapshot)
  const corpusRemaining = Number(await scalar(
    `SELECT COUNT(*) FROM company_enrichment e
     JOIN company_contacts cc ON e.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
     WHERE e.Lead_Source = 'US_Apollo' AND e.Pipeline_Status = 'Intelligence_Ready'
       AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
       AND (cc.Email_Label IS NULL OR cc.Email_Label != 'Bounced')`, [], 0))

  // reputation from bayesian_state (Turso-mirrored)
  const brow = await q1('SELECT Reputation FROM bayesian_state WHERE ID = 1')
  const reputation = brow && brow.Reputation != null ? Number(brow.Reputation) : null

  const alerts = await q(
    `SELECT Level, Code, Message FROM us_alerts WHERE Active = 1
     ORDER BY CASE Level WHEN 'red' THEN 0 WHEN 'yellow' THEN 1 ELSE 2 END`)
  const testEmails = (await q('SELECT Email FROM us_test_emails ORDER BY ID')).map((r) => r.Email)

  return json({
    mode: cfg.mode,
    enabled: cfg.enabled === 'true',
    start_date: cfg.start_date,
    before_start: beforeStart,
    in_window: inWindow,
    window_reason: windowReason,
    warmup_day: warmupDay,
    daily_limit: dailyLimit,
    deliverability_multiplier: volMultiplier(reputation),
    reputation,
    sent_today: sentToday,
    corpus_remaining: corpusRemaining,
    reveals_this_month: cfg.reveals_this_month != null ? Number(cfg.reveals_this_month) : 0,
    monthly_enrich_cap: parseInt(cfg.monthly_enrich_cap ?? '90', 10),
    apollo_cycle_start: cfg.apollo_cycle_start || null,
    test_count: parseInt(cfg.test_count ?? '5', 10),
    test_emails: testEmails,
    send_days: cfg.send_days || '0,1,2,3,4',
    start_hour: sh,
    end_hour: eh,
    cycle_minutes: parseInt(cfg.cycle_minutes ?? '20', 10),
    last_cycle_at: cfg.last_cycle_at,
    learning: { active: false },
    alerts,
  })
}
