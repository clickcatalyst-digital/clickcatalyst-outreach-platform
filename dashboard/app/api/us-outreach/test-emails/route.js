// GET  /api/us-outreach/test-emails  -> [{ID, Email, Added_At}]
// POST same with { email } -> insert
import { q, run, json } from '../../../lib/turso.server'

export async function GET() {
  const rows = await q('SELECT ID, Email, Added_At FROM us_test_emails ORDER BY ID')
  return json(rows)
}

export async function POST(req) {
  const body = await req.json().catch(() => ({}))
  const email = (body.email || '').trim()
  if (!email.includes('@') || !email.split('@').pop().includes('.')) {
    return json({ detail: 'valid email required' }, { status: 400 })
  }
  await run('INSERT OR IGNORE INTO us_test_emails (Email) VALUES (?)', [email])
  return json({ ok: true, email })
}
