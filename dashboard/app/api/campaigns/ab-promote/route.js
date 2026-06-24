import { run, json } from '../../../lib/turso.server'

export async function POST(req) {
  const body = await req.json().catch(() => ({}))
  const winner = body.winner_variant
  if (!winner) return json({ error: 'winner_variant required' }, { status: 400 })

  let loser
  if (winner.endsWith('_a')) loser = winner.slice(0, -2) + '_b'
  else if (winner.endsWith('_b')) loser = winner.slice(0, -2) + '_a'
  else return json({ error: "Variant doesn't end with _a or _b" }, { status: 400 })

  const r = await run('UPDATE campaign_templates SET Is_Active = 0 WHERE Variant_Key = ?', [loser])
  return json({ ok: true, deactivated: loser, rows_affected: Number(r.rowsAffected || 0) })
}
