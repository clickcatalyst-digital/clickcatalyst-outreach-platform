'use client'

import { useState, useEffect } from 'react'
import { apiFetch } from '../lib/api'
import Funnel from '../components/Funnel'

const LEVEL = { red: '#e5484d', yellow: '#d6a100', green: '#30a46c' }
const fmtAge = (m) => m == null ? 'never' : m < 60 ? `${Math.round(m)}m ago`
  : m < 1440 ? `${(m / 60).toFixed(1)}h ago` : `${(m / 1440).toFixed(1)}d ago`

function Tile({ state, label, value, sub }) {
  const color = state === 'ok' ? LEVEL.green : state === 'bad' ? LEVEL.red
    : state === 'warn' ? LEVEL.yellow : 'var(--muted)'
  return (
    <div style={{ border: '1px solid var(--border)', background: 'var(--surface)', borderRadius: 12, padding: '15px 17px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 9, height: 9, borderRadius: 999, background: color, flexShrink: 0 }} />
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>{label}</span>
      </div>
      <div style={{ fontSize: 19, fontWeight: 600, marginTop: 8, color: 'var(--text)' }}>{value}</div>
      {sub ? <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2 }}>{sub}</div> : null}
    </div>
  )
}

export default function SystemPage() {
  const [h, setH] = useState(null)

  async function load() { const d = await apiFetch('/system-health'); if (d) setH(d) }
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t) }, [])

  if (!h) return <div style={{ padding: 48, color: 'var(--muted)' }}>Loading…</div>
  const s = h.signals || {}
  const st = (sig) => sig?.ok === true ? 'ok' : sig?.ok === false ? 'bad' : 'neutral'

  return (
    <div className="cc-page page-enter" style={{ padding: '40px 44px', maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6, flexWrap: 'wrap' }}>
        <h1 style={{ fontSize: 21, fontWeight: 600, margin: 0, letterSpacing: '-0.02em' }}>System Health</h1>
        <span style={{
          fontSize: 12, padding: '4px 10px', borderRadius: 999, background: 'var(--surface)',
          border: '1px solid var(--border)', color: h.ok ? LEVEL.green : LEVEL.red,
        }}>{h.ok ? '🟢 All systems healthy' : '🔴 Needs attention'}</span>
      </div>
      <p style={{ color: 'var(--muted)', fontSize: 13, margin: '0 0 24px' }}>
        If everything is green, the Mac is running the pipeline — no need to check it.
      </p>

      <div className="cc-grid-auto" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
        <Tile state={st(s.mac)} label="MacBook" value={s.mac?.value || '—'} sub={`heartbeat ${fmtAge(s.mac?.age_min)}`} />
        <Tile state={st(s.scheduler)} label="Scheduler" value={s.scheduler?.value || '—'} sub={`mode ${String(s.scheduler?.mode || '').toUpperCase()}`} />
        <Tile state={st(s.orchestrator)} label="Orchestrator" value={fmtAge(s.orchestrator?.age_min)} sub="last cycle" />
        <Tile state={st(s.tracking_sync)} label="Tracking sync" value={fmtAge(s.tracking_sync?.age_min)} sub="opens / clicks" />
        <Tile state={st(s.command_queue)} label="Command queue" value={`${s.command_queue?.pending ?? '—'} pending`} sub="dashboard → Mac" />
        <Tile state={st(s.database)} label="Database" value={s.database?.value || '—'} sub="Turso" />
        <Tile state="neutral" label="Last send" value={s.last_send?.value || 'never'} sub={`${s.last_send?.today || 0} today`} />
        <Tile state={st(s.bayesian)} label="Bayesian" value={fmtAge(s.bayesian?.age_min)} sub="reputation model" />
        <Tile state={st(s.campaign_templates)} label="Templates" value={`${s.campaign_templates?.active ?? '—'} active`} sub="" />
        <Tile state={st(s.test_recipients)} label="Test recipients" value={s.test_recipients?.count ?? '—'} sub="" />
        <Tile state={s.alerts?.ok ? 'ok' : 'warn'} label="Alerts" value={s.alerts?.count ? String(s.alerts.count) : 'none'} sub={s.alerts?.red ? `${s.alerts.red} red` : ''} />
      </div>

      {s.alerts?.items?.length > 0 && (
        <div style={{ marginTop: 24 }}>
          {s.alerts.items.map((a, i) => (
            <div key={i} style={{
              padding: '9px 13px', borderRadius: 8, marginBottom: 6, fontSize: 12.5,
              borderLeft: `3px solid ${LEVEL[a.Level] || 'var(--muted)'}`, background: 'var(--surface)',
            }}>
              <strong style={{ color: LEVEL[a.Level] }}>{a.Level?.toUpperCase()}</strong>
              <span style={{ color: 'var(--text)' }}> · {a.Message}</span>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 30 }}>
        <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Lead funnel</div>
        <Funnel f={h.funnel} />
      </div>
    </div>
  )
}
