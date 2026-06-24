import { run, json } from '../../../../../lib/turso.server'

export async function PATCH(_req, { params }) {
  await run('UPDATE company_contacts SET Is_Primary_Contact = 0 WHERE CIN = ?', [params.cin])
  await run('UPDATE company_contacts SET Is_Primary_Contact = 1 WHERE Contact_ID = ?', [Number(params.contact_id)])
  return json({ ok: true })
}
