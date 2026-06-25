// GET /api/health — pings Turso so the dashboard's connectivity indicator reflects
// the actual backend (Turso). On failure it returns a non-secret diagnostic so you
// can tell WHY (missing url, missing token, or a connection error) without leaking creds.
import { scalar, json, tursoUrl, tursoToken } from '../../lib/turso.server'

export const dynamic = 'force-dynamic'

export async function GET() {
  const url = tursoUrl()
  try {
    await scalar('SELECT 1', [], 1)
    return json({ status: 'ok' })
  } catch (e) {
    return json({
      status: 'error',
      hasUrl: !!url,
      urlScheme: url ? (url.split('://')[0] || null) : null, // e.g. 'libsql' — never the full url
      hasToken: !!tursoToken(),
      detail: String(e?.message || e),
    }, { status: 503 })
  }
}
