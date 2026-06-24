import { q, json, countryFilter } from '../../../lib/turso.server'

export async function GET(req) {
  const flt = countryFilter(new URL(req.url).searchParams.get('country'))
  const rows = await q(`
    SELECT Email_Sent_Date AS date,
           COUNT(*) AS sent,
           SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) AS clicked
    FROM outreach_analytics
    WHERE Email_Sent_Date >= date('now', '-30 days') ${flt}
    GROUP BY Email_Sent_Date
    ORDER BY Email_Sent_Date ASC`)
  return json(rows)
}
