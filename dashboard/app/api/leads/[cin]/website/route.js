import { run, json } from '../../../../lib/turso.server'

export async function PATCH(req, { params }) {
  const body = await req.json().catch(() => ({}))
  const url = (body.website_url || '').trim()
  if (!url) return json({ error: 'website_url is required' }, { status: 400 })
  await run(
    `UPDATE company_enrichment SET Website_URL = ?, Domain_Source = 'Manual Override' WHERE CIN = ?`,
    [url, params.cin])
  return json({ ok: true, website_url: url })
}
