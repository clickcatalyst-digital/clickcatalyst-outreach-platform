// GET  /api/us-outreach/config  -> { key: value, ... }
// PATCH same with a JSON body of allowed keys -> upserts us_scheduler_config
import { q, run, json } from '../../../lib/turso.server'

const ALLOWED = new Set([
  'mode', 'enabled', 'test_count', 'start_hour', 'end_hour', 'send_days',
  'replenish_threshold', 'replenish_enrich_batch', 'monthly_enrich_cap',
  'apollo_cycle_start', 'cycle_minutes', 'start_date', 'learning_threshold',
])

export async function GET() {
  const rows = await q('SELECT Config_Key, Config_Value FROM us_scheduler_config')
  const cfg = {}
  for (const r of rows) cfg[r.Config_Key] = r.Config_Value
  return json(cfg)
}

export async function PATCH(req) {
  const body = await req.json().catch(() => ({}))
  const updated = []
  for (const [k, v] of Object.entries(body)) {
    if (!ALLOWED.has(k)) continue
    await run(
      `INSERT INTO us_scheduler_config (Config_Key, Config_Value)
       VALUES (?, ?)
       ON CONFLICT(Config_Key) DO UPDATE SET
         Config_Value = excluded.Config_Value,
         Updated_At = CURRENT_TIMESTAMP`,
      [k, String(v)],
    )
    updated.push(k)
  }
  return json({ ok: true, updated })
}
