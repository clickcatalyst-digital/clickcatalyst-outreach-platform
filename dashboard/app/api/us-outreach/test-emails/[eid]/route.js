// DELETE /api/us-outreach/test-emails/:eid
import { run, json } from '../../../../lib/turso.server'

export async function DELETE(_req, { params }) {
  const eid = Number(params.eid)
  await run('DELETE FROM us_test_emails WHERE ID = ?', [eid])
  return json({ ok: true })
}
