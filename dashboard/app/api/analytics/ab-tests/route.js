import { q, json, countryFilter } from '../../../lib/turso.server'

// erf approximation (Abramowitz & Stegun 7.1.26) — JS has no Math.erf.
function erf(x) {
  const sign = x < 0 ? -1 : 1
  x = Math.abs(x)
  const t = 1 / (1 + 0.3275911 * x)
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x)
  return sign * y
}

export async function GET(req) {
  const flt = countryFilter(new URL(req.url).searchParams.get('country'))
  const rows = await q(`
    SELECT Campaign_Variant,
           COUNT(*) AS sent,
           SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) AS clicked,
           SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) AS opened
    FROM outreach_analytics
    WHERE Campaign_Variant IS NOT NULL ${flt}
    GROUP BY Campaign_Variant`)

  const pairs = {}
  for (const r of rows) {
    const key = r.Campaign_Variant
    let base = key, side = 'a'
    if (key.endsWith('_a') || key.endsWith('_b')) { base = key.slice(0, -2); side = key.slice(-1) }
    if (!pairs[base]) pairs[base] = { base, a: null, b: null }
    const sent = Number(r.sent), clicked = Number(r.clicked), opened = Number(r.opened)
    pairs[base][side] = {
      variant: key, sent, clicked, opened,
      click_rate: sent > 0 ? Math.round((1000 * clicked) / sent) / 10 : 0,
      open_rate: sent > 0 ? Math.round((1000 * opened) / sent) / 10 : 0,
    }
  }

  const results = []
  for (const base of Object.keys(pairs)) {
    const { a, b } = pairs[base]
    const test = { base, a, b, winner: null, significant: false, p_value: null, min_sample: null }
    if (a && b && a.sent >= 5 && b.sent >= 5) {
      const nA = a.sent, nB = b.sent
      const pA = a.clicked / nA, pB = b.clicked / nB
      const pPool = (a.clicked + b.clicked) / (nA + nB)
      if (pPool > 0 && pPool < 1) {
        const se = Math.sqrt(pPool * (1 - pPool) * (1 / nA + 1 / nB))
        if (se > 0) {
          const z = (pA - pB) / se
          const pVal = 2 * (1 - 0.5 * (1 + erf(Math.abs(z) / Math.sqrt(2))))
          test.p_value = Math.round(pVal * 10000) / 10000
          test.significant = pVal < 0.05
          test.winner = pA > pB ? 'a' : pB > pA ? 'b' : null
        }
        const effect = 0.05, zAlpha = 1.96, zBeta = 0.84
        const minN = ((zAlpha + zBeta) ** 2 * 2 * pPool * (1 - pPool)) / (effect ** 2)
        test.min_sample = Math.ceil(minN)
      }
    }
    results.push(test)
  }
  return json(results)
}
