#!/usr/bin/env node
// Business-pipeline health ("make doctor" — run before sleep). Hits /api/system-health
// and prints a green/red board with freshness + the lead funnel.
// Usage: node scripts/doctor.mjs [baseUrl] [user:pass]
const BASE = (process.argv[2] || process.env.DASHBOARD_URL || 'http://localhost:3000').replace(/\/$/, '')
const AUTH = process.argv[3] || process.env.BASIC_AUTH || ''
const headers = AUTH ? { Authorization: 'Basic ' + Buffer.from(AUTH).toString('base64') } : {}

const fmtAge = (m) => m == null ? 'never' : m < 60 ? `${Math.round(m)}m ago`
  : m < 1440 ? `${(m / 60).toFixed(1)}h ago` : `${(m / 1440).toFixed(1)}d ago`

let warn = 0, fail = 0
function line(state, label, detail = '') {
  if (state === 'warn') warn++
  if (state === 'fail') fail++
  const icon = state === 'ok' ? '🟢' : state === 'warn' ? '🟡' : '🔴'
  console.log(`${icon} ${label.padEnd(20)} ${detail}`)
}

;(async () => {
  console.log(`\n🩺 doctor — ${BASE}\n`)
  let h
  try {
    const r = await fetch(BASE + '/api/system-health', { headers })
    h = await r.json()
  } catch (e) { line('fail', 'Reach dashboard', String(e.message)); process.exit(1) }

  const s = h.signals || {}
  line(s.database?.ok ? 'ok' : 'fail', 'Turso', s.database?.value || '')
  line(s.mac?.ok ? 'ok' : 'fail', 'Mac heartbeat', fmtAge(s.mac?.age_min))
  line(s.orchestrator?.ok ? 'ok' : 'fail', 'Orchestrator', fmtAge(s.orchestrator?.age_min))
  line(s.tracking_sync?.ok ? 'ok' : 'fail', 'Tracking sync', fmtAge(s.tracking_sync?.age_min))
  line(s.command_queue?.ok ? 'ok' : 'warn', 'Command queue', `${s.command_queue?.pending} pending`)
  line(s.scheduler?.ok ? 'ok' : 'warn', 'Scheduler', `${s.scheduler?.value} · ${String(s.scheduler?.mode).toUpperCase()}`)
  line(s.test_recipients?.ok ? 'ok' : 'warn', 'Test recipients', `${s.test_recipients?.count}`)
  line(s.campaign_templates?.ok ? 'ok' : 'fail', 'Campaign templates', `${s.campaign_templates?.active} active`)
  line(s.bayesian?.ok ? 'ok' : 'warn', 'Bayesian state', fmtAge(s.bayesian?.age_min))
  line(s.alerts?.ok ? 'ok' : 'warn', 'Alerts', s.alerts?.count ? `${s.alerts.count} (${s.alerts.red} red)` : 'none')
  line('ok', 'Last send', `${s.last_send?.value || 'never'} · ${s.last_send?.today} today`)

  const f = h.funnel || {}
  console.log(`\n  Funnel:  ${f.generated} gen → ${f.qualified} qual → ${f.ready} ready → ${f.sent} sent → ${f.opened} open → ${f.clicked} click → ${f.replied} reply`)
  console.log(`           never-emailed: ${f.never_emailed}`)
  console.log(`\n${fail ? '🔴 ' + fail + ' critical' : warn ? '🟡 ' + warn + ' warning(s)' : '🟢 all systems healthy'}\n`)
  process.exit(fail ? 1 : 0)
})()
