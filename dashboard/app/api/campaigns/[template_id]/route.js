import { q1, run, json } from '../../../lib/turso.server'

export const dynamic = 'force-dynamic'

const ALLOWED = ['Subject_Line', 'Body_HTML', 'Body_Plain', 'CTA_URL', 'Is_Active']

export async function GET(_req, { params }) {
  const row = await q1('SELECT * FROM campaign_templates WHERE Template_ID = ?', [Number(params.template_id)])
  return json(row || { error: 'Not found' })
}

export async function PATCH(req, { params }) {
  const body = await req.json().catch(() => ({}))
  const keys = Object.keys(body).filter((k) => ALLOWED.includes(k))
  if (!keys.length) return json({ error: 'No valid fields to update' }, { status: 400 })
  const setClause = keys.map((k) => `${k} = ?`).join(', ')
  const values = keys.map((k) => body[k])
  await run(`UPDATE campaign_templates SET ${setClause} WHERE Template_ID = ?`,
    [...values, Number(params.template_id)])
  return json({ ok: true })
}
