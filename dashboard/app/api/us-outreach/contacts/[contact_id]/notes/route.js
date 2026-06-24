import { run, json } from '../../../../../lib/turso.server'

export async function PATCH(req, { params }) {
  const body = await req.json().catch(() => ({}))
  await run('UPDATE company_contacts SET Notes = ? WHERE Contact_ID = ?',
    [body.notes || '', Number(params.contact_id)])
  return json({ ok: true })
}
