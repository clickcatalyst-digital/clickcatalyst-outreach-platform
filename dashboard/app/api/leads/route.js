import { q, scalar, json } from '../../lib/turso.server'

export const dynamic = 'force-dynamic'

export async function GET(req) {
  const sp = new URL(req.url).searchParams
  const status = sp.get('status')
  const search = sp.get('search')
  const page = parseInt(sp.get('page') || '1', 10)
  const limit = parseInt(sp.get('limit') || '50', 10)
  const offset = (page - 1) * limit

  // Hosted dashboard is US-only: company_enrichment / Lead_Source = 'US_Apollo'.
  const where = ["e.Lead_Source = 'US_Apollo'"]
  const params = []
  if (status) { where.push('e.Pipeline_Status = ?'); params.push(status) }
  if (search) { where.push('(e.Company_Name LIKE ? OR e.CIN LIKE ?)'); params.push(`%${search}%`, `%${search}%`) }
  const wc = where.join(' AND ')

  const leads = await q(`
    SELECT e.CIN, e.Company_Name AS CompanyName, 'US Agency' AS ICP_Segment,
           NULL AS State, NULL AS PaidupCapital, NULL AS RegistrationDate, NULL AS nic_code,
           e.Website_URL, e.Domain_Source, e.Has_GMB, e.Has_Google_Ads_Pixel,
           e.Pipeline_Status, NULL AS Competitor_Count, e.Email_Sent_Date,
           (SELECT COUNT(*) FROM company_contacts cc WHERE cc.CIN = e.CIN) AS Contact_Count
    FROM company_enrichment e
    WHERE ${wc}
    ORDER BY e.CIN
    LIMIT ? OFFSET ?`, [...params, limit, offset])

  const total = Number(await scalar(`SELECT COUNT(*) FROM company_enrichment e WHERE ${wc}`, params, 0))
  return json({ leads, total, page, limit })
}
