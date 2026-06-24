// dashboard/app/components/QueuePanel.jsx
// Drop this into your pipeline page as <QueuePanel api={API} />
// Replace the existing SchedulerPanel

'use client'

import { useState, useEffect, useCallback } from 'react'

export default function QueuePanel({ api }) {
  const [queue, setQueue]           = useState(null)
  const [sched, setSched]           = useState(null)
  const [showConfig, setShowConfig] = useState(false)
  const [showWeek, setShowWeek]     = useState(false)
  const [weekPlan, setWeekPlan]     = useState(null)

  // Schedule form
  const [schedCount, setSchedCount]     = useState(5)
  const [schedStrategy, setSchedStrategy] = useState('')
  const [schedVariant, setSchedVariant] = useState('')
  const [schedTestEmail, setSchedTestEmail] = useState('')
  const [schedSendAfter, setSchedSendAfter] = useState('')
  const [scheduling, setScheduling] = useState(false)

  // Config form
  const [configDraft, setConfigDraft] = useState(null)
  const [configSaving, setConfigSaving] = useState(false)

  const refresh = useCallback(() => {
    fetch(`${api}/queue/status`).then(r => r.json()).then(setQueue).catch(() => {})
    fetch(`${api}/pipeline/scheduler/status`).then(r => r.json()).then(setSched).catch(() => {})
  }, [api])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 30000) // refresh every 30s
    return () => clearInterval(interval)
  }, [refresh])

  useEffect(() => {
    if (sched?.config && !configDraft) {
      setConfigDraft({
        start_hour: sched.config.start_hour,
        end_hour: sched.config.end_hour,
        peak_hours: sched.config.peak_hours.join(','),
        send_days: sched.config.send_days,
      })
    }
  }, [sched])

  async function scheduleBatch() {
    setScheduling(true)
    await fetch(`${api}/queue/schedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        count: schedCount,
        strategy: schedStrategy || undefined,
        variant_key: schedStrategy === 'manual' ? schedVariant : undefined,
        test_email: schedTestEmail || undefined,
        send_after: schedSendAfter || undefined,
      })
    })
    setScheduling(false)
    refresh()
  }

  async function forceSend() {
    if (!confirm('Force send all queued emails now, bypassing time window?')) return
    await fetch(`${api}/queue/force-send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    })
    refresh()
  }

  async function togglePause() {
    const endpoint = queue?.auto_send_enabled ? 'pause' : 'resume'
    await fetch(`${api}/queue/${endpoint}`, { method: 'POST' })
    refresh()
  }

  async function cancelQueued() {
    if (!confirm('Cancel all queued emails?')) return
    await fetch(`${api}/queue/cancel-queued`, { method: 'DELETE' })
    refresh()
  }

  async function clearFailed() {
    await fetch(`${api}/queue/clear-failed`, { method: 'DELETE' })
    refresh()
  }

  async function saveConfig() {
    setConfigSaving(true)
    // Save schedule config
    await fetch(`${api}/pipeline/scheduler/config`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_hour: String(configDraft.start_hour),
        end_hour: String(configDraft.end_hour),
        peak_hours: configDraft.peak_hours,
        send_days: configDraft.send_days.join(','),
      })
    })
    // Save queue config
    await fetch(`${api}/queue/config`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        default_strategy: schedStrategy || queue?.strategy || 'thompson',
        force_test_mode: String(!!schedTestEmail),
        test_email_fallback: schedTestEmail || '',
      })
    })
    setConfigSaving(false)
    setShowConfig(false)
    refresh()
  }

  async function loadWeekPlan() {
    const r = await fetch(`${api}/pipeline/scheduler/week-plan`)
    setWeekPlan(await r.json())
    setShowWeek(!showWeek)
  }

  if (!queue || !sched) return null

  const dayNames = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: 22, marginBottom: 24,
      boxShadow: 'var(--shadow-sm)'
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={secTitle}>Email Queue</div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={togglePause} style={{
            fontSize: 11, padding: '4px 10px', borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)', cursor: 'pointer',
            background: queue.auto_send_enabled ? 'var(--green-soft)' : 'var(--accent-soft)',
            color: queue.auto_send_enabled ? 'var(--green)' : 'var(--accent)',
            fontWeight: 500
          }}>
            {queue.auto_send_enabled ? '● Auto-send ON' : '■ PAUSED'}
          </button>
          <button onClick={loadWeekPlan} style={linkBtn}>
            {showWeek ? 'Hide' : 'Week'} plan
          </button>
          <button onClick={() => setShowConfig(!showConfig)} style={linkBtn}>
            {showConfig ? 'Hide' : 'Settings'}
          </button>
        </div>
      </div>

      {/* Status row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8, marginBottom: 16 }}>
        {[
          { label: 'Queued', value: queue.queued, color: 'var(--blue)' },
          { label: 'Sending', value: queue.sending, color: 'var(--yellow)' },
          { label: 'Sent today', value: queue.sent_today, color: 'var(--green)' },
          { label: 'Failed', value: queue.failed, color: queue.failed > 0 ? 'var(--accent)' : 'var(--muted)' },
          { label: 'Daily limit', value: sched.daily_limit, color: 'var(--text)' },
          { label: 'Remaining', value: sched.remaining, color: 'var(--green)' },
        ].map(m => (
          <div key={m.label} style={{
            padding: '8px 10px', background: 'var(--bg)',
            borderRadius: 'var(--radius-sm)', textAlign: 'center'
          }}>
            <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 16, fontWeight: 500, color: m.color }}>
              {m.value}
            </div>
            <div style={{ fontSize: 9, color: 'var(--muted)', marginTop: 2 }}>{m.label}</div>
          </div>
        ))}
      </div>

      {/* Send window indicator */}
      <div style={{
        padding: '8px 14px', borderRadius: 'var(--radius-sm)', marginBottom: 14,
        fontSize: 12, fontWeight: 500,
        background: sched.can_send ? 'var(--green-soft)' : 'var(--bg)',
        color: sched.can_send ? 'var(--green)' : 'var(--muted)',
        border: `1px solid ${sched.can_send ? 'var(--green)' : 'var(--border)'}`
      }}>
        {sched.can_send
          ? `${sched.is_peak ? '⚡ Peak' : '✅ Active'} · ${dayNames[sched.current_day]} ${sched.current_hour}:00 IST · Worker sends automatically`
          : `⏸ Next window: ${dayNames[sched.config?.send_days?.[0] ?? 0]} ${sched.config?.start_hour ?? 9}:00 IST · Queue emails now, they'll send on schedule`
        }
      </div>

      {/* Schedule form */}
      <div style={{
        display: 'flex', alignItems: 'flex-end', gap: 8, flexWrap: 'wrap', marginBottom: 14,
        padding: '14px 16px', background: 'var(--bg)', borderRadius: 'var(--radius-sm)',
        border: '1px solid var(--border)'
      }}>
        <label style={fieldLabel}>
          Count
          <input type="number" min={1} max={100} value={schedCount}
            onChange={e => setSchedCount(parseInt(e.target.value) || 1)}
            style={{ ...fieldInput, width: 60 }} />
        </label>
        <label style={fieldLabel}>
          Strategy
          <select value={schedStrategy} onChange={e => setSchedStrategy(e.target.value)}
            style={{ ...fieldInput, width: 130 }}>
            <option value="">Auto ({queue.strategy})</option>
            <option value="thompson">Thompson Sampling</option>
            <option value="even_split">Even A/B Split</option>
            <option value="manual">Manual Variant</option>
          </select>
        </label>
        {schedStrategy === 'manual' && (
          <label style={fieldLabel}>
            Variant
            <input value={schedVariant} onChange={e => setSchedVariant(e.target.value)}
              placeholder="ecomm_pmax_v1_a"
              style={{ ...fieldInput, width: 160 }} />
          </label>
        )}
        <label style={fieldLabel}>
          Test email (optional)
          <input value={schedTestEmail} onChange={e => setSchedTestEmail(e.target.value)}
            placeholder="you@email.com"
            style={{ ...fieldInput, width: 170 }} />
        </label>
        <label style={fieldLabel}>
          Send after (optional)
          <input type="datetime-local" value={schedSendAfter}
            onChange={e => setSchedSendAfter(e.target.value)}
            style={{ ...fieldInput, width: 170 }} />
        </label>
        <button onClick={scheduleBatch} disabled={scheduling}
          style={{
            padding: '7px 18px', fontSize: 12, fontWeight: 500,
            background: 'var(--green)', color: 'white', border: 'none',
            borderRadius: 'var(--radius-sm)', cursor: 'pointer',
            marginBottom: 0
          }}>
          {scheduling ? 'Scheduling...' : `Schedule ${schedCount}`}
        </button>
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        {queue.queued > 0 && (
          <>
            <button onClick={forceSend} style={{
              padding: '6px 14px', fontSize: 11, fontWeight: 500,
              background: 'var(--accent)', color: 'white', border: 'none',
              borderRadius: 'var(--radius-sm)', cursor: 'pointer'
            }}>
              Force send {queue.queued} now
            </button>
            <button onClick={cancelQueued} style={{
              padding: '6px 14px', fontSize: 11,
              background: 'none', color: 'var(--muted)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', cursor: 'pointer'
            }}>
              Cancel queued
            </button>
          </>
        )}
        {queue.failed > 0 && (
          <button onClick={clearFailed} style={{
            padding: '6px 14px', fontSize: 11,
            background: 'none', color: 'var(--muted)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)', cursor: 'pointer'
          }}>
            Clear {queue.failed} failed
          </button>
        )}
      </div>

      {/* Upcoming queue preview */}
      {queue.upcoming?.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Queued ({queue.queued})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {queue.upcoming.map(item => (
              <div key={item.Queue_ID} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '6px 10px', fontSize: 10, borderRadius: 4,
                background: 'var(--bg)', border: '1px solid var(--border)',
                fontFamily: 'DM Mono, monospace', color: 'var(--muted)'
              }}>
                <span style={{ color: 'var(--text)', fontWeight: 500, flex: '0 0 160px' }}>
                  {item.CompanyName?.slice(0, 22) || item.CIN}
                </span>
                <span>{item.Email_Address || 'no email'}</span>
                <span style={{ marginLeft: 'auto', color: 'var(--blue)' }}>
                  {item.Strategy || 'auto'}
                </span>
                {item.Test_Email && <span style={{ color: 'var(--yellow)' }}>test</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent sent/failed */}
      {queue.recent?.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Recent
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {queue.recent.slice(0, 5).map(item => (
              <div key={item.Queue_ID} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '5px 10px', fontSize: 10, borderRadius: 4,
                background: item.Status === 'sent' ? 'var(--green-soft)' : 'var(--accent-soft)',
                fontFamily: 'DM Mono, monospace',
                color: item.Status === 'sent' ? 'var(--green)' : 'var(--accent)'
              }}>
                <span>{item.Status === 'sent' ? '✓' : '✕'}</span>
                <span style={{ color: 'var(--text)' }}>{item.CompanyName?.slice(0, 20) || item.CIN}</span>
                <span>{item.Variant_Key || 'auto'}</span>
                {item.Error && <span style={{ marginLeft: 'auto' }} title={item.Error}>error</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Week plan */}
      {showWeek && weekPlan && (
        <div style={{ marginTop: 14, padding: '14px 16px', background: 'var(--bg)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
          <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            7-day projection · {weekPlan.total_projected} emails
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {weekPlan.days.map(d => (
              <div key={d.date} style={{
                flex: 1, textAlign: 'center', padding: '8px 4px',
                borderRadius: 'var(--radius-sm)',
                background: d.is_today ? 'var(--blue-soft)' : d.is_weekend ? 'transparent' : 'var(--surface)',
                border: d.is_today ? '1px solid var(--blue)' : '1px solid transparent',
                opacity: d.is_weekend ? 0.4 : 1
              }}>
                <div style={{ fontSize: 10, color: 'var(--muted)' }}>{d.day_name}</div>
                <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 16, fontWeight: 500, color: d.is_weekend ? 'var(--muted)' : 'var(--text)', marginTop: 2 }}>
                  {d.projected_sends}
                </div>
                <div style={{ fontSize: 9, color: 'var(--muted)', marginTop: 2 }}>day {d.warmup_day}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Settings panel */}
      {showConfig && configDraft && (
        <div style={{
          marginTop: 14, padding: '16px 18px', background: 'var(--bg)',
          borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)'
        }}>
          <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Schedule settings
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 14 }}>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              Start hour (IST)
              <input type="number" min={0} max={23} value={configDraft.start_hour}
                onChange={e => setConfigDraft(d => ({ ...d, start_hour: parseInt(e.target.value) || 0 }))}
                style={configInput} />
            </label>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              End hour (IST)
              <input type="number" min={0} max={23} value={configDraft.end_hour}
                onChange={e => setConfigDraft(d => ({ ...d, end_hour: parseInt(e.target.value) || 0 }))}
                style={configInput} />
            </label>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              Peak hours
              <input value={configDraft.peak_hours}
                onChange={e => setConfigDraft(d => ({ ...d, peak_hours: e.target.value }))}
                placeholder="10,11,14,15"
                style={configInput} />
            </label>
          </div>

          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>Send days</div>
            <div style={{ display: 'flex', gap: 4 }}>
              {dayNames.map((name, i) => {
                const active = configDraft.send_days.includes(i)
                return (
                  <button key={name} onClick={() => {
                    setConfigDraft(d => ({
                      ...d,
                      send_days: active ? d.send_days.filter(x => x !== i) : [...d.send_days, i].sort()
                    }))
                  }} style={{
                    flex: 1, padding: '6px 0', fontSize: 11, fontWeight: 500,
                    borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer',
                    background: active ? 'var(--green)' : 'var(--surface)',
                    color: active ? 'white' : 'var(--muted)',
                    transition: 'all 0.15s ease'
                  }}>
                    {name}
                  </button>
                )
              })}
            </div>
          </div>

          <button onClick={saveConfig} disabled={configSaving} style={{
            padding: '7px 16px', fontSize: 12, fontWeight: 500,
            background: 'var(--text)', color: 'white', border: 'none',
            borderRadius: 'var(--radius-sm)', cursor: 'pointer'
          }}>
            {configSaving ? 'Saving...' : 'Save settings'}
          </button>
        </div>
      )}
    </div>
  )
}

// Styles
const secTitle = {
  fontSize: 11, fontWeight: 600, color: 'var(--muted)',
  textTransform: 'uppercase', letterSpacing: '0.08em'
}

const linkBtn = {
  fontSize: 11, color: 'var(--blue)', background: 'none',
  border: 'none', cursor: 'pointer', textDecoration: 'underline'
}

const fieldLabel = {
  display: 'flex', flexDirection: 'column', fontSize: 10,
  color: 'var(--muted)', gap: 3
}

const fieldInput = {
  padding: '6px 8px', fontSize: 12, fontFamily: 'DM Mono, monospace',
  border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
  background: 'var(--surface)', color: 'var(--text)', outline: 'none'
}

const configInput = {
  display: 'block', width: '100%', marginTop: 4, padding: '6px 8px',
  fontSize: 13, fontFamily: 'DM Mono, monospace',
  border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
  background: 'var(--surface)', color: 'var(--text)', outline: 'none'
}

const dayNames = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']