import { q, json, countryFilter } from '../../../lib/turso.server'

export async function GET(req) {
  const flt = countryFilter(new URL(req.url).searchParams.get('country'))
  const rows = await q(`
    SELECT Campaign_Variant,
           COUNT(*) AS sent,
           SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) AS clicked,
           SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) AS opened,
           ROUND(100.0 * SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS click_rate,
           ROUND(100.0 * SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS open_rate
    FROM outreach_analytics
    WHERE Campaign_Variant IS NOT NULL ${flt}
    GROUP BY Campaign_Variant
    ORDER BY click_rate DESC`)
  return json(rows)
}
