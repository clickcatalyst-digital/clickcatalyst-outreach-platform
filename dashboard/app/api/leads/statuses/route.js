import { q, json } from '../../../lib/turso.server'

export const dynamic = 'force-dynamic'

export async function GET() {
  const rows = await q(`
    SELECT Pipeline_Status, COUNT(*) as count
    FROM company_enrichment
    WHERE Lead_Source = 'US_Apollo'
    GROUP BY Pipeline_Status
    ORDER BY count DESC`)
  return json(rows)
}
