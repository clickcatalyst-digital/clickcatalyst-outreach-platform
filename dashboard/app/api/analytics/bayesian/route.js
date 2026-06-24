// Thompson posteriors (live from outreach_analytics) + deliverability (Turso
// bayesian_state) + reply stats. Mirrors GET /api/analytics/bayesian.
import { q, q1, scalar, json, countryFilter } from '../../../lib/turso.server'

export async function GET(req) {
  const flt = countryFilter(new URL(req.url).searchParams.get('country'))

  // Thompson Sampling posteriors
  const vrows = await q(`
    SELECT Campaign_Variant, COUNT(*) AS total,
           SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) AS clicked,
           SUM(CASE WHEN Reply_Received = 1 THEN 1 ELSE 0 END) AS replied,
           SUM(CASE WHEN Converted = 1 THEN 1 ELSE 0 END) AS converted
    FROM outreach_analytics
    WHERE Campaign_Variant IS NOT NULL ${flt}
    GROUP BY Campaign_Variant`)
  const variants = vrows.map((r) => {
    const total = Number(r.total), clicked = Number(r.clicked)
    const alpha = 1 + clicked, beta = 1 + (total - clicked)
    const mean = alpha / (alpha + beta)
    const sd = Math.sqrt((mean * (1 - mean)) / Math.max(total, 1))
    return {
      Campaign_Variant: r.Campaign_Variant, total, clicked,
      replied: Number(r.replied), converted: Number(r.converted),
      alpha, beta, mean: Math.round(mean * 1e4) / 1e4,
      ci_low: Math.round(Math.max(0, mean - 1.96 * sd) * 1e4) / 1e4,
      ci_high: Math.round(Math.min(1, mean + 1.96 * sd) * 1e4) / 1e4,
    }
  })

  // Deliverability from Turso bayesian_state
  let deliverability = { reputation: 0.7, trend: 'no_data', history: [] }
  const brow = await q1('SELECT Reputation, History_Json FROM bayesian_state WHERE ID = 1')
  if (brow && brow.Reputation != null) {
    const history = (JSON.parse(brow.History_Json || '[]')).slice(-14)
    deliverability = { reputation: Number(brow.Reputation), trend: 'stable', history }
    if (history.length >= 3) {
      const recent = history.slice(-5).map((h) => h.reputation)
      const older = history.slice(-10, -5).map((h) => h.reputation)
      if (older.length) {
        const avg = (a) => a.reduce((s, x) => s + x, 0) / a.length
        const diff = avg(recent) - avg(older)
        deliverability.trend = diff > 0.05 ? 'improving' : diff < -0.05 ? 'declining' : 'stable'
      }
    }
  }

  // Reply stats
  const total_replies = Number(await scalar(
    `SELECT COUNT(*) FROM outreach_analytics WHERE Reply_Received = 1 ${flt}`, [], 0))
  const unique_companies = Number(await scalar(
    `SELECT COUNT(DISTINCT CIN) FROM outreach_analytics WHERE Reply_Received = 1 ${flt}`, [], 0))
  const total_sent = Number(await scalar(
    `SELECT COUNT(*) FROM outreach_analytics WHERE 1=1 ${flt}`, [], 0))
  const reply_stats = {
    total_replies, unique_companies,
    reply_rate: total_sent > 0 ? Math.round((total_replies / total_sent) * 1000) / 10 : 0,
  }

  return json({ variants, deliverability, reply_stats })
}
