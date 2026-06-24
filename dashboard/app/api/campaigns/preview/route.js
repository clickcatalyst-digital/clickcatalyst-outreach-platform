import { q1, json } from '../../../lib/turso.server'

export async function POST(req) {
  const body = await req.json().catch(() => ({}))
  const t = await q1('SELECT * FROM campaign_templates WHERE Template_ID = ?', [body.template_id])
  if (!t) return json({ error: 'Template not found' }, { status: 404 })

  const sample = {
    company_name: 'Acme Retail Pvt Ltd',
    personalized_sentence: 'My analysis shows 8 other retail companies in Maharashtra with your exact capital bracket are currently capturing impression share.',
    audit_url: (t.CTA_URL || '') + '?utm_source=preview&cin=SAMPLE',
    competitor_count: '8',
  }
  const sub = (s) => {
    let out = s || ''
    for (const [k, v] of Object.entries(sample)) out = out.split('{' + k + '}').join(v)
    return out
  }
  return json({ subject: sub(t.Subject_Line), body_html: sub(t.Body_HTML), body_plain: sub(t.Body_Plain) })
}
