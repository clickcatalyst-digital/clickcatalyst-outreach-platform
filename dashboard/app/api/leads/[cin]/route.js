import { q, q1, json } from '../../../lib/turso.server'

export const dynamic = 'force-dynamic'

export async function GET(_req, { params }) {
  const cin = params.cin
  // Hosted = US only. India CINs (non-APOLLO) live in vw_qualified_leads (not in Turso).
  if (!cin.startsWith('APOLLO_')) return json({ error: 'Lead not found' })

  const lead = await q1(`
    SELECT e.CIN, e.Company_Name AS CompanyName, 'US Agency' AS ICP_Segment,
           NULL AS State, NULL AS PaidupCapital, NULL AS RegistrationDate,
           NULL AS nic_code, NULL AS Industry,
           e.Website_URL, e.Domain_Source, e.Has_GMB, e.Has_Google_Ads_Pixel,
           e.Pipeline_Status, NULL AS Competitor_Count, e.Personalized_Sentence,
           e.Email_Sent_Date, e.Audit_Link_Clicked
    FROM company_enrichment e WHERE e.CIN = ?`, [cin])
  if (!lead) return json({ error: 'Lead not found' })

  const contacts = await q(`
    SELECT Contact_ID, Full_Name, Job_Title, Email_Address, Email_Label,
           LinkedIn_URL, Is_Primary_Contact, Added_Date
    FROM company_contacts WHERE CIN = ? ORDER BY Is_Primary_Contact DESC`, [cin])

  const outreach = await q(`
    SELECT Analytics_ID, Email_Sent_Date, Batch_ID, Campaign_Variant, Subject_Line,
           Audit_Link_Clicked, Clicked_At, Email_Opened
    FROM outreach_analytics WHERE CIN = ? ORDER BY Analytics_ID DESC`, [cin])

  return json({ lead, contacts, outreach })
}
