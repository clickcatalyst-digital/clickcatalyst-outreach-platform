import { run, json } from '../../../../lib/turso.server'

export async function DELETE(_req, { params }) {
  await run('DELETE FROM company_contacts WHERE Contact_ID = ? AND CIN = ?',
    [Number(params.contact_id), params.cin])
  return json({ ok: true })
}
