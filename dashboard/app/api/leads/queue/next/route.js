import { json } from '../../../../lib/turso.server'

// India MCA queue (vw_qualified_leads) — not in Turso. Empty on the hosted US dashboard.
export async function GET() {
  return json({ lead: null, total: 0, offset: 0 })
}
