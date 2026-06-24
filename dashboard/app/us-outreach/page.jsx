'use client'

import { useState, useEffect } from 'react'
import { apiFetch } from '../lib/api'

const LEVEL = { red: '#e5484d', yellow: '#d6a100', green: '#30a46c' }
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export default function USOutreachPage() {
  const [s, setS] = useState(null)
  const [emails, setEmails] = useState([])
  const [newEmail, setNewEmail] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    const [st, te] = await Promise.all([
      apiFetch('/us-outreach/status'),
      apiFetch('/us-outreach/test-emails'),
    ])
    if (st) setS(st)
    if (te) setEmails(te)
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [])

  async function patch(key, value) {
    setBusy(true)
    await apiFetch('/us-outreach/config', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [key]: value }),
    })
    await load()
    setBusy(false)
  }

  async function toggleMode() {
    const next = s.mode === 'test' ? 'prod' : 'test'
    if (next === 'prod' &&
        !confirm('Switch to PRODUCTION? Real prospects will receive emails on the next cycle.')) return
    await patch('mode', next)
  }

  async function toggleDay(i) {
    const set = new Set((s.send_days || '').split(',').filter(x => x !== '').map(Number))
    set.has(i) ? set.delete(i) : set.add(i)
    await patch('send_days', [...set].sort((a, b) => a - b).join(','))
  }

  async function addEmail() {
    if (!newEmail.includes('@')) return
    setBusy(true)
    await apiFetch('/us-outreach/test-emails', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: newEmail.trim() }),
    })
    setNewEmail(''); await load(); setBusy(false)
  }

  async function delEmail(id) {
    await apiFetch(`/us-outreach/test-emails/${id}`, { method: 'DELETE' }); await load()
  }

  async function runOnce() {
    setBusy(true)
    await apiFetch('/us-outreach/run-once', { method: 'POST' })
    setTimeout(load, 2500); setBusy(false)
  }

  if (!s) return <div style={{ padding: 48, color: 'var(--muted)' }}>Loading…</div>

  const isProd = s.mode === 'prod'
  const days = new Set((s.send_days || '').split(',').filter(x => x !== '').map(Number))
  const hb = heartbeat(s.last_cycle_at, s.cycle_minutes)

  return (
    <div style={{ padding: '40px 44px', maxWidth: 880, margin: '0 auto' }}>

      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 600, letterSpacing: '-0.02em', margin: 0 }}>
            US Outreach
          </h1>
          <p style={{ color: 'var(--muted)', fontSize: 13, margin: '6px 0 0' }}>
            Self-running Apollo pipeline. Monitor here — it sends on its own.
          </p>
        </div>
        <div title={s.last_cycle_at || 'never'} style={{
          display: 'flex', alignItems: 'center', gap: 7, fontSize: 12,
          padding: '6px 12px', borderRadius: 999, border: '1px solid var(--border)',
          background: 'var(--surface)', color: hb.color, whiteSpace: 'nowrap'
        }}>
          <span style={{ width: 7, height: 7, borderRadius: 999, background: hb.color }} />
          {hb.label}
        </div>
      </div>

      {/* ── Mode + master controls ── */}
      <div style={{
        display: 'flex', gap: 10, marginBottom: 22, alignItems: 'stretch', flexWrap: 'wrap'
      }}>
        <button onClick={toggleMode} disabled={busy} style={{
          flex: '1 1 320px', textAlign: 'left', padding: '14px 18px', borderRadius: 12, cursor: 'pointer',
          border: `1px solid ${isProd ? LEVEL.red : LEVEL.green}`,
          background: isProd ? '#e5484d0d' : '#30a46c0d',
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: isProd ? LEVEL.red : LEVEL.green }}>
            {isProd ? 'Production' : 'Test mode'}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 3 }}>
            {isProd ? 'Sending to real prospects · tap to switch to test' : 'Sending to test inboxes only · tap to go live'}
          </div>
        </button>

        <Btn onClick={() => patch('enabled', s.enabled ? 'false' : 'true')} disabled={busy}>
          {s.enabled ? 'Pause all' : 'Resume'}
          <Sub>{s.mode === 'test' ? 'test already pauses prod' : 'kill switch'}</Sub>
        </Btn>
        <Btn onClick={runOnce} disabled={busy}>
          Run cycle now <Sub>test the flow</Sub>
        </Btn>
      </div>

      {/* ── Alerts ── */}
      {s.alerts?.length > 0 && (
        <div style={{ marginBottom: 22 }}>
          {s.alerts.map((a, i) => (
            <div key={i} style={{
              padding: '9px 13px', borderRadius: 8, marginBottom: 6, fontSize: 12.5,
              borderLeft: `3px solid ${LEVEL[a.Level] || 'var(--muted)'}`,
              background: 'var(--surface)',
            }}>
              <strong style={{ color: LEVEL[a.Level] }}>{a.Level.toUpperCase()}</strong>
              <span style={{ color: 'var(--text)' }}> · {a.Message}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Status ── */}
      <Section label="Live status">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
          <Stat label="State" value={s.before_start ? `Starts ${s.start_date}` : s.in_window ? 'In window' : 'Idle'}
            sub={s.before_start ? '' : s.window_reason} />
          <Stat label="Warmup day" value={s.warmup_day} sub={`limit ${s.daily_limit}/day`} />
          <Stat label="Sent today" value={s.sent_today} sub="prod only" />
          <Stat label="Corpus" value={s.corpus_remaining} sub="leads ready" />
          <Stat label="Reputation" value={s.reputation ?? '—'}
            color={rep(s.reputation)} sub={`vol ×${s.deliverability_multiplier}`} />
          <Stat label="Reveals (cap)" value={`${s.reveals_this_month}/${s.monthly_enrich_cap}`} sub="logged · self-imposed" />
        </div>
      </Section>

      {/* ── Schedule (overridable) ── */}
      <Section label="Schedule — when the system sends (CST)">
        <Card>
          <Row label="Send days">
            <div style={{ display: 'flex', gap: 6 }}>
              {DAYS.map((d, i) => (
                <button key={d} onClick={() => toggleDay(i)} disabled={busy} style={{
                  width: 42, padding: '7px 0', borderRadius: 8, cursor: 'pointer', fontSize: 12,
                  border: `1px solid ${days.has(i) ? 'var(--text)' : 'var(--border)'}`,
                  background: days.has(i) ? 'var(--text)' : 'transparent',
                  color: days.has(i) ? 'var(--bg)' : 'var(--muted)', fontWeight: days.has(i) ? 600 : 400,
                }}>{d}</button>
              ))}
            </div>
          </Row>

          <Row label="Send window">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <HourSelect value={s.start_hour} onChange={v => patch('start_hour', v)} />
              <span style={{ color: 'var(--muted)', fontSize: 13 }}>to</span>
              <HourSelect value={s.end_hour} onChange={v => patch('end_hour', v)} />
              <span style={{ color: 'var(--muted)', fontSize: 12 }}>CST (covers ET → PT)</span>
            </div>
          </Row>

          <Row label="Send every">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="number" min="5" defaultValue={s.cycle_minutes} key={s.cycle_minutes}
                onBlur={e => patch('cycle_minutes', e.target.value)} style={numInput} />
              <span style={{ color: 'var(--muted)', fontSize: 12 }}>min — sends are spread across the window</span>
            </div>
          </Row>

          <Row label="Start date" last>
            <input type="date" defaultValue={s.start_date} key={s.start_date}
              onChange={e => patch('start_date', e.target.value)} style={numInput} />
          </Row>
        </Card>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, margin: '12px 2px 0',
          fontSize: 12, color: 'var(--muted)'
        }}>
          <span style={{
            width: 7, height: 7, borderRadius: 999,
            background: s.learning?.active && s.learning.peak_hours.length ? LEVEL.green : 'var(--border)'
          }} />
          {s.learning?.active && s.learning.peak_hours.length
            ? <span>Auto-learning <b style={{ color: 'var(--text)' }}>active</b> — favoring {s.learning.peak_hours.map(h => String(h).padStart(2, '0') + ':00').join(', ')} (best open rates)</span>
            : <span>Send-time auto-learning: building ({s.learning?.sends ?? 0}/{s.learning?.threshold ?? 150} prod sends, then it picks the best hours itself)</span>}
        </div>
      </Section>

      {/* ── Test config ── */}
      <Section label="Test configuration">
        <Card style={{ opacity: isProd ? 0.5 : 1 }}>
          <Row label="Emails / day (test)">
            <input type="number" min="1" defaultValue={s.test_count} key={s.test_count}
              onBlur={e => patch('test_count', e.target.value)} style={numInput} />
          </Row>
          <Row label="Test recipients" last>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', gap: 8, marginBottom: emails.length ? 10 : 0 }}>
                <input value={newEmail} onChange={e => setNewEmail(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addEmail()} placeholder="you@example.com"
                  style={{ ...numInput, width: 220 }} />
                <Btn small onClick={addEmail} disabled={busy}>Add</Btn>
              </div>
              {emails.length === 0
                ? <div style={{ fontSize: 12, color: LEVEL.yellow }}>No test emails — test mode can’t send until you add one.</div>
                : emails.map(e => (
                  <div key={e.ID} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', fontSize: 13 }}>
                    <span>{e.Email}</span>
                    <button onClick={() => delEmail(e.ID)} style={{ background: 'none', border: 'none', color: LEVEL.red, cursor: 'pointer', fontSize: 12 }}>remove</button>
                  </div>
                ))}
            </div>
          </Row>
        </Card>
      </Section>
    </div>
  )
}

/* ── helpers ── */
function heartbeat(iso, cycleMin) {
  if (!iso) return { color: LEVEL.yellow, label: 'Daemon not started' }
  const mins = (Date.now() - new Date(iso).getTime()) / 60000
  if (mins > 3 * (cycleMin || 20)) return { color: LEVEL.red, label: `Last ran ${fmtAgo(mins)} ago — check daemon` }
  return { color: LEVEL.green, label: `Running · last ${fmtAgo(mins)} ago` }
}
function fmtAgo(m) { return m < 1 ? 'just now' : m < 60 ? `${Math.round(m)}m` : `${Math.round(m / 60)}h` }
function rep(r) { return r == null ? 'var(--text)' : r < 0.4 ? LEVEL.red : r < 0.6 ? LEVEL.yellow : LEVEL.green }

function Section({ label, children }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 12 }}>{label}</div>
      {children}
    </div>
  )
}
function Card({ children, style }) {
  return <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: '6px 18px', ...style }}>{children}</div>
}
function Row({ label, children, last }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 0', borderBottom: last ? 'none' : '1px solid var(--border)' }}>
      <div style={{ fontSize: 12.5, color: 'var(--muted)', width: 150, flexShrink: 0 }}>{label}</div>
      {children}
    </div>
  )
}
function Stat({ label, value, sub, color }) {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: 15 }}>
      <div style={{ fontSize: 10.5, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 19, fontWeight: 500, marginTop: 5, color: color || 'var(--text)' }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}
function Btn({ children, onClick, disabled, small }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: small ? '8px 14px' : '14px 18px', borderRadius: small ? 8 : 12, cursor: 'pointer',
      border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)',
      fontSize: 13, textAlign: 'left',
    }}>{children}</button>
  )
}
function Sub({ children }) {
  return <span style={{ display: 'block', fontSize: 11, fontWeight: 400, marginTop: 3, color: 'var(--muted)' }}>{children}</span>
}
function HourSelect({ value, onChange }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={numInput}>
      {Array.from({ length: 24 }, (_, h) => (
        <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>
      ))}
    </select>
  )
}
const numInput = {
  padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border)',
  background: 'var(--bg)', color: 'var(--text)', fontSize: 13, outline: 'none',
}
