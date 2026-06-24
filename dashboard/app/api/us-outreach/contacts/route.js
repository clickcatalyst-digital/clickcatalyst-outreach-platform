import { q, scalar, json } from '../../../lib/turso.server'

export const dynamic = 'force-dynamic'

export async function GET(req) {
  const sp = new URL(req.url).searchParams
  const search = sp.get('search')
  const page = parseInt(sp.get('page') || '1', 10)
  const limit = parseInt(sp.get('limit') || '100', 10)
  const offset = (page - 1) * limit

  const where = ["e.Lead_Source = 'US_Apollo'"]
  const params = []
  if (search) {
    where.push('(e.Company_Name LIKE ? OR cc.Full_Name LIKE ? OR cc.Email_Address LIKE ?)')
    params.push(`%${search}%`, `%${search}%`, `%${search}%`)
  }
  const wc = where.join(' AND ')

  const contacts = await q(`
    SELECT cc.Contact_ID, cc.CIN, cc.Full_Name, cc.Job_Title, cc.Email_Address,
           cc.Email_Label, cc.LinkedIn_URL, cc.Is_Primary_Contact,
           cc.Notes, cc.Conversation_Summary, cc.Summary_Updated_At,
           e.Company_Name, e.Website_URL, e.Has_Google_Ads_Pixel,
           e.Pipeline_Status, e.Phone, e.Email_Sent_Date,
           (SELECT COUNT(*) FROM outreach_analytics oa WHERE oa.CIN = cc.CIN
              AND oa.Email_Opened = 1 AND oa.Batch_ID NOT LIKE 'ustest%') AS Opens,
           (SELECT COUNT(*) FROM outreach_analytics oa WHERE oa.CIN = cc.CIN
              AND oa.Audit_Link_Clicked = 1 AND oa.Batch_ID NOT LIKE 'ustest%') AS Clicks,
           (SELECT COUNT(*) FROM outreach_analytics oa WHERE oa.CIN = cc.CIN
              AND oa.Reply_Received = 1 AND oa.Batch_ID NOT LIKE 'ustest%') AS Replies
    FROM company_contacts cc
    JOIN company_enrichment e ON cc.CIN = e.CIN
    WHERE ${wc}
    ORDER BY e.Company_Name, cc.Is_Primary_Contact DESC
    LIMIT ? OFFSET ?`, [...params, limit, offset])

  const total = Number(await scalar(`
    SELECT COUNT(*) FROM company_contacts cc
    JOIN company_enrichment e ON cc.CIN = e.CIN WHERE ${wc}`, params, 0))
  return json({ contacts, total })
}
