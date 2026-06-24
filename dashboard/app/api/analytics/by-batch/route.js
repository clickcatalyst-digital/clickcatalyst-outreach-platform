import { q, json, countryFilter } from '../../../lib/turso.server'

export async function GET(req) {
  const flt = countryFilter(new URL(req.url).searchParams.get('country'))
  const rows = await q(`
    SELECT Batch_ID,
           COUNT(*) AS sent,
           SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) AS clicked,
           MIN(Email_Sent_Date) AS sent_date
    FROM outreach_analytics
    WHERE 1=1 ${flt}
    GROUP BY Batch_ID
    ORDER BY sent_date DESC
    LIMIT 20`)
  return json(rows)
}
