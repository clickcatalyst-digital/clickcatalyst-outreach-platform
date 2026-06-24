import { scalar, json, countryFilter } from '../../../lib/turso.server'

export async function GET(req) {
  const country = new URL(req.url).searchParams.get('country')
  const flt = countryFilter(country)
  const cnt = async (extra = '') =>
    Number(await scalar(`SELECT COUNT(*) FROM outreach_analytics WHERE 1=1 ${flt} ${extra}`, [], 0))

  const total_sent = await cnt()
  const total_clicked = await cnt('AND Audit_Link_Clicked = 1')
  const total_opened = await cnt('AND Email_Opened = 1')
  const total_replied = await cnt('AND Reply_Received = 1')
  const unique_companies = Number(
    await scalar(`SELECT COUNT(DISTINCT CIN) FROM outreach_analytics WHERE 1=1 ${flt}`, [], 0))

  const rate = (n) => (total_sent > 0 ? Math.round((n / total_sent) * 1000) / 10 : 0)
  return json({
    total_sent, total_clicked, total_opened,
    click_rate: rate(total_clicked), open_rate: rate(total_opened),
    unique_companies, total_replied, reply_rate: rate(total_replied),
  })
}
