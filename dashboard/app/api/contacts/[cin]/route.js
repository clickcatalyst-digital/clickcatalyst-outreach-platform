import { q, run, json } from '../../../lib/turso.server'

export const dynamic = 'force-dynamic'

export async function GET(_req, { params }) {
  const rows = await q(`
    SELECT Contact_ID, CIN, Full_Name, Job_Title, Email_Address, Email_Label,
           LinkedIn_URL, Is_Primary_Contact, Added_Date
    FROM company_contacts WHERE CIN = ?
    ORDER BY Is_Primary_Contact DESC, Contact_ID ASC`, [params.cin])
  return json(rows)
}

export async function POST(req, { params }) {
  const cin = params.cin
  const body = await req.json().catch(() => ({}))
  for (const f of ['full_name', 'email_address']) {
    if (!body[f]) return json({ error: `${f} is required` }, { status: 400 })
  }
  if (body.is_primary) {
    await run('UPDATE company_contacts SET Is_Primary_Contact = 0 WHERE CIN = ?', [cin])
  }
  const r = await run(`
    INSERT INTO company_contacts
      (CIN, Full_Name, Job_Title, Email_Address, Email_Label, LinkedIn_URL, Is_Primary_Contact)
    VALUES (?, ?, ?, ?, ?, ?, ?)`, [
    cin, body.full_name.trim(), body.job_title ?? null, body.email_address.trim(),
    body.email_label ?? 'Work', body.linkedin_url || null, body.is_primary ? 1 : 0,
  ])
  return json({ ok: true, contact_id: Number(r.lastInsertRowid) })
}
