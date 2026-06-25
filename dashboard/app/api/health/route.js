// GET /api/health — pings Turso so the dashboard's connectivity indicator reflects
// the actual backend (Turso), not a FastAPI server.
import { scalar, json } from '../../lib/turso.server'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    await scalar('SELECT 1', [], 1)
    return json({ status: 'ok' })
  } catch (e) {
    return json({ status: 'error', detail: String(e?.message || e) }, { status: 503 })
  }
}
