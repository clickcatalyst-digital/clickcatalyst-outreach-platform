import { q, json } from '../../lib/turso.server'

export const dynamic = 'force-dynamic'

export async function GET(req) {
  const c = (new URL(req.url).searchParams.get('country') || '').toLowerCase()
  // US arms use the 'us_' Variant_Key prefix; India arms don't.
  let where = ''
  if (c === 'us') where = "WHERE Variant_Key LIKE 'us\\_%' ESCAPE '\\'"
  else if (c === 'india') where = "WHERE Variant_Key NOT LIKE 'us\\_%' ESCAPE '\\'"
  const rows = await q(`
    SELECT Template_ID, Variant_Key, Segment, Subject_Line,
           Body_HTML, Body_Plain, CTA_URL, Is_Active, Created_At
    FROM campaign_templates
    ${where}
    ORDER BY Segment, Variant_Key`)
  return json(rows)
}
