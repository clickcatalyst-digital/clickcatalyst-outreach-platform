import { q1, run, json } from '../../../lib/turso.server'

export async function POST(req) {
  const body = await req.json().catch(() => ({}))
  const contacts = body.contacts || []
  if (!contacts.length) return json({ error: 'No contacts provided', imported: 0, skipped: 0 })

  let imported = 0, skipped = 0
  const errors = []
  for (let i = 0; i < contacts.length; i++) {
    const c = contacts[i]
    const cin = (c.cin || '').trim()
    const full_name = (c.full_name || '').trim()
    const email = (c.email_address || '').trim()
    if (!cin || !full_name || !email || !email.includes('@')) {
      skipped++; errors.push(`Row ${i + 1}: missing CIN, name, or valid email`); continue
    }
    // Hosted is US-only: verify CIN against company_enrichment (US_Apollo), not vw_qualified_leads.
    const exists = await q1(
      `SELECT CIN FROM company_enrichment WHERE CIN = ? AND Lead_Source = 'US_Apollo'`, [cin])
    if (!exists) { skipped++; errors.push(`Row ${i + 1}: CIN ${cin} not found`); continue }

    const is_primary = c.is_primary ? 1 : 0
    if (is_primary) await run('UPDATE company_contacts SET Is_Primary_Contact = 0 WHERE CIN = ?', [cin])
    await run(`
      INSERT INTO company_contacts
        (CIN, Full_Name, Job_Title, Email_Address, Email_Label, LinkedIn_URL, Is_Primary_Contact)
      VALUES (?, ?, ?, ?, ?, ?, ?)`, [
      cin, full_name, (c.job_title || '').trim() || null, email,
      (c.email_label || 'Work').trim(), (c.linkedin_url || '').trim() || null, is_primary,
    ])
    imported++
  }
  return json({ ok: true, imported, skipped, errors: errors.slice(0, 20) })
}
