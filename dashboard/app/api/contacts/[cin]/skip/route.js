import { run, json } from '../../../../lib/turso.server'

export async function PATCH(_req, { params }) {
  await run(`UPDATE company_enrichment SET Pipeline_Status = 'No_Contact_Found' WHERE CIN = ?`,
    [params.cin])
  return json({ ok: true })
}
