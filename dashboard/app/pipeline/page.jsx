// dashboard/app/pipeline/page.jsx
'use client'

import { useState, useEffect, useRef } from 'react'
import { Play, Square, RefreshCw } from 'lucide-react'
import QueuePanel from '../components/QueuePanel'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

const STAGES = [
  { id: 1, name: 'Domain Finder',       file: 'domain_extractor_01.py',  color: '#2563eb' },
  { id: 2, name: 'Pixel Checker',       file: 'pixel_checker_02.py',     color: '#16a34a' },
  { id: 3, name: 'Intelligence Engine',  file: 'competition_intel_03.py', color: '#ca8a04' },
  { id: 4, name: 'Email Dispatch',      file: 'email_engine_04.py',      color: '#e63946' },
]

export default function PipelinePage() {
  const [status, setStatus]         = useState(null)
  const [batchSize, setBatchSize]   = useState(50)
  const [maxWorkers, setMaxWorkers] = useState(10)
  const [running, setRunning]       = useState(null)
  const [logs, setLogs]             = useState([])
  const [history, setHistory]       = useState([])
  const [preview, setPreview]     = useState(null)
  const [calendar, setCalendar] = useState(null)
  const [showPreview, setShowPreview] = useState(false)
  const termRef = useRef(null)
  const esRef   = useRef(null)

  useEffect(() => {
    fetchStatus()
    fetchHistory()
    fetch(`${API}/queue/calendar?days=14`).then(r => r.json()).then(setCalendar).catch(() => {})
  }, [])

  useEffect(() => {
    if (termRef.current) termRef.current.scrollTop = termRef.current.scrollHeight
  }, [logs])

  async function fetchStatus() {
    try {
      const r = await fetch(`${API}/pipeline/status`)
      setStatus(await r.json())
    } catch {}
  }

  async function fetchHistory() {
    try {
      const r = await fetch(`${API}/pipeline/history?limit=10`)
      setHistory(await r.json())
    } catch {}
  }

  async function runStage(stageId) {
    setRunning(stageId)
    setLogs([`▶ Starting Stage ${stageId}: ${STAGES[stageId - 1].name}...`])

    const body = { stage: stageId, batch_size: batchSize, max_workers: maxWorkers }

    const r = await fetch(`${API}/pipeline/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
    const { run_id } = await r.json()

    if (esRef.current) esRef.current.close()
    const es = new EventSource(`${API}/pipeline/stream/${run_id}`)
    esRef.current = es

    es.onmessage = (e) => {
      const { line } = JSON.parse(e.data)
      if (line === '__DONE__' || line === '__TIMEOUT__') {
        es.close()
        setRunning(null)
        fetchStatus()
        fetchHistory()
        setLogs(prev => [...prev, '─'.repeat(50), '✓ Stage complete.'])
      } else {
        setLogs(prev => [...prev, line])
      }
    }

    es.onerror = () => {
      es.close()
      setRunning(null)
      setLogs(prev => [...prev, '❌ Stream connection lost.'])
    }
  }

  function stopStage() {
    esRef.current?.close()
    setRunning(null)
    setLogs(prev => [...prev, '⚠ Stopped by user.'])
  }

  async function loadPreview() {
    try {
      const r = await fetch(`${API}/pipeline/preview-next-email`)
      const d = await r.json()
      setPreview(d)
      setShowPreview(true)
    } catch {
      setPreview({ has_preview: false, error: 'Could not connect to API' })
      setShowPreview(true)
    }
  }

  const statusItems = [
    { label: 'Qualified Leads', key: 'total_qualified',   color: 'var(--muted)' },
    { label: 'Enriched',        key: 'enriched',           color: '#2563eb' },
    { label: 'Pixel Confirmed', key: 'pixel_confirmed',    color: '#16a34a' },
    { label: 'Intel Ready',     key: 'intelligence_ready', color: '#ca8a04' },
    { label: 'Contacts Added',  key: 'contacts_added',     color: '#7c3aed' },
    { label: 'Emails Sent',     key: 'outreach_sent',      color: '#e63946' },
    { label: 'Max Retries (manual)',  key: 'max_retries_reached', color: 'var(--muted)' },
    { label: 'Unsubscribed',         key: 'unsubscribed',         color: 'var(--muted)' },
    { label: 'Hard Bounced',          key: 'hard_bounced',          color: '#e63946' },
  ]

  return (
    <div className="page-enter" style={{ padding: '36px 44px' }}>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 4, letterSpacing: '-0.01em' }}>
        Pipeline
      </h1>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 36 }}>
        Trigger each stage manually. Live logs stream below.
      </p>

      {/* ── STATUS BAR ── */}
      {status && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 10, marginBottom: 36
        }}>
          {statusItems.map(({ label, key, color }) => (
            <div key={key} style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              padding: '16px 18px',
              boxShadow: 'var(--shadow-sm)'
            }}>
              <div style={{
                fontFamily: 'DM Mono, monospace',
                fontSize: 22, fontWeight: 500, color
              }}>
                {(status[key] ?? 0).toLocaleString()}
              </div>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── SCHEDULER CONTROLS ── */}
      {/* <SchedulerPanel api={API} running={running} onRunStage={(runId) => {
        setRunning(4)
        // Connect to SSE for logs
        if (esRef.current) esRef.current.close()
        const es = new EventSource(`${API}/pipeline/stream/${runId}`)
        esRef.current = es
        es.onmessage = (e) => {
          const { line } = JSON.parse(e.data)
          if (line === '__DONE__' || line === '__TIMEOUT__') {
            es.close()
            setRunning(null)
            fetchStatus()
            fetchHistory()
            setLogs(prev => [...prev, '─'.repeat(50), '✓ Scheduled send complete.'])
          } else {
            setLogs(prev => [...prev, line])
          }
        }
        es.onerror = () => { es.close(); setRunning(null); setLogs(prev => [...prev, '❌ Stream lost.']) }
      }} /> */}

      <QueuePanel api={API} />

      {/* ── EMAIL CALENDAR ── */}
      {calendar && calendar.days?.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{
            fontSize: 11, fontWeight: 600, color: 'var(--muted)',
            textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10
          }}>Email calendar</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {calendar.days.map(day => (
              <CalendarDay key={day.date} day={day} />
            ))}
          </div>
        </div>
      )}

      {/* ── EMAIL PREVIEW ── */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden', marginBottom: 24,
        boxShadow: 'var(--shadow-sm)'
      }}>
        <div style={{
          padding: '13px 18px', borderBottom: showPreview ? '1px solid var(--border)' : 'none',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center'
        }}>
          <div style={sectionTitle}>Email Preview</div>
          <button onClick={loadPreview} style={{
            fontSize: 11, padding: '5px 12px', borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)', background: 'var(--bg)',
            cursor: 'pointer', color: 'var(--text)', fontWeight: 500
          }}>
            {showPreview ? 'Refresh' : 'Preview next email'}
          </button>
        </div>

        {showPreview && preview && (
          preview.has_preview ? (
            <div style={{ padding: 20 }}>
              {/* Meta */}
              <div style={{ display: 'flex', gap: 20, marginBottom: 16, fontSize: 12 }}>
                <div>
                  <span style={{ color: 'var(--muted)' }}>To: </span>
                  <span style={{ fontFamily: 'DM Mono, monospace' }}>{preview.recipient}</span>
                </div>
                <div>
                  <span style={{ color: 'var(--muted)' }}>Company: </span>
                  <span style={{ fontWeight: 500 }}>{preview.company_name}</span>
                </div>
                <div>
                  <span style={{ color: 'var(--muted)' }}>Variant: </span>
                  <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11 }}>{preview.variant_key}</span>
                </div>
              </div>

              {/* Subject */}
              <div style={{
                padding: '10px 14px', background: 'var(--bg)', borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border)', marginBottom: 14
              }}>
                <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 4 }}>Subject</div>
                <div style={{ fontSize: 14, fontWeight: 500 }}>{preview.subject}</div>
              </div>

              {/* HTML preview */}
              <div style={{
                border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                overflow: 'hidden'
              }}>
                <div style={{
                  padding: '8px 14px', borderBottom: '1px solid var(--border)',
                  fontSize: 10, color: 'var(--muted)', background: 'var(--bg)'
                }}>HTML Preview</div>
                <div style={{
                  padding: 20, background: 'white',
                  maxHeight: 400, overflowY: 'auto'
                }}
                  dangerouslySetInnerHTML={{ __html: preview.body_html }}
                />
              </div>

              {/* Note about scatter plot */}
              <div style={{
                marginTop: 12, fontSize: 11, color: 'var(--muted)', fontStyle: 'italic'
              }}>
                Note: scatter plot image generates at send time and isn't shown in preview.
              </div>
            </div>
          ) : (
            <div style={{ padding: 20, color: 'var(--muted)', fontSize: 13 }}>
              {preview.error || 'No leads in queue to preview.'}
            </div>
          )
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32 }}>

        {/* ── LEFT: CONTROLS ── */}
        <div>
          {/* Batch settings */}
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: 22, marginBottom: 14,
            boxShadow: 'var(--shadow-sm)'
          }}>
            <div style={sectionTitle}>Batch Settings</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <label style={labelStyle}>
                Batch Size
                <input type="number" value={batchSize}
                  onChange={e => setBatchSize(+e.target.value)}
                  style={inputStyle} />
              </label>
              <label style={labelStyle}>
                Pixel Workers
                <input type="number" value={maxWorkers}
                  onChange={e => setMaxWorkers(+e.target.value)}
                  style={inputStyle} />
              </label>
            </div>
          </div>

          {/* Email settings */}
          {/* <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: 22, marginBottom: 18,
            boxShadow: 'var(--shadow-sm)'
          }}>
            <div style={sectionTitle}>Email Stage</div>
            <label style={{
              display: 'flex', alignItems: 'center', gap: 8,
              fontSize: 13, marginBottom: 12, cursor: 'pointer', color: 'var(--text)'
            }}>
              <input type="checkbox" checked={testMode}
                onChange={e => setTestMode(e.target.checked)} />
              Test Mode (redirect all to test address)
            </label>
            {testMode && (
              <input
                placeholder="test@youremail.com"
                value={testEmail}
                onChange={e => setTestEmail(e.target.value)}
                style={{ ...inputStyle, width: '100%' }}
              />
            )}
          </div> */}

          {/* Stage buttons */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {STAGES.map(s => (
              <div key={s.id} style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderLeft: `3px solid ${s.color}`,
                borderRadius: 'var(--radius)',
                padding: '14px 18px',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                boxShadow: 'var(--shadow-sm)'
              }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>
                    Stage {s.id} — {s.name}
                  </div>
                  <div style={{
                    fontFamily: 'DM Mono, monospace',
                    fontSize: 10, color: 'var(--muted)', marginTop: 3
                  }}>{s.file}</div>
                </div>
                <button
                  onClick={() => running === s.id ? stopStage() : runStage(s.id)}
                  disabled={running !== null && running !== s.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '7px 16px', borderRadius: 'var(--radius-sm)',
                    border: 'none',
                    cursor: running !== null && running !== s.id ? 'not-allowed' : 'pointer',
                    fontSize: 12, fontWeight: 500,
                    background: running === s.id ? '#fef2f2' : s.color,
                    color: running === s.id ? '#e63946' : 'white',
                    opacity: running !== null && running !== s.id ? 0.35 : 1,
                    transition: 'all 0.15s ease'
                  }}
                >
                  {running === s.id
                    ? <><Square size={12} /> Stop</>
                    : <><Play size={12} /> Run</>
                  }
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* ── RIGHT: TERMINAL + HISTORY ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* Terminal */}
          <div style={{
            background: '#0d0d0d', borderRadius: 'var(--radius)',
            border: '1px solid #222', overflow: 'hidden',
            boxShadow: '0 4px 20px rgba(0,0,0,0.12)'
          }}>
            <div style={{
              padding: '11px 16px',
              borderBottom: '1px solid #222',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between'
            }}>
              <div style={{ display: 'flex', gap: 6 }}>
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff5f57' }} />
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#febc2e' }} />
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#28c840' }} />
              </div>
              <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: '#555' }}>
                pipeline log
              </span>
              <button onClick={() => setLogs([])} style={{
                background: 'none', border: 'none', cursor: 'pointer', color: '#555', padding: 0
              }}>
                <RefreshCw size={12} />
              </button>
            </div>
            <div ref={termRef} style={{
              height: 360, overflowY: 'auto', padding: '14px 18px',
              fontFamily: 'DM Mono, monospace', fontSize: 11,
              lineHeight: 1.8, color: '#ccc'
            }}>
              {logs.length === 0
                ? <span style={{ color: '#3a3a3a' }}>Run a stage to see live output...</span>
                : logs.map((l, i) => (
                  <div key={i} style={{
                    color: l.startsWith('❌') ? '#f87171'
                         : l.startsWith('✅') || l.startsWith('✓') ? '#4ade80'
                         : l.startsWith('⚠') ? '#fbbf24'
                         : l.startsWith('🎯') ? '#60a5fa'
                         : '#bbb'
                  }}>{l}</div>
                ))
              }
            </div>
          </div>

          {/* Run history */}
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', overflow: 'hidden',
            boxShadow: 'var(--shadow-sm)'
          }}>
            <div style={{
              padding: '13px 18px', borderBottom: '1px solid var(--border)',
              ...sectionTitle, marginBottom: 0, paddingBottom: 13
            }}>Recent Runs</div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Stage', 'Batch', 'Started', 'Status'].map(h => (
                    <th key={h} style={{
                      padding: '9px 14px', textAlign: 'left',
                      color: 'var(--muted)', fontWeight: 500, fontSize: 11
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.map(r => (
                  <tr key={r.Run_ID} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '9px 14px' }}>{r.Stage_Name}</td>
                    <td style={{ padding: '9px 14px', fontFamily: 'DM Mono, monospace' }}>{r.Batch_Size}</td>
                    <td style={{ padding: '9px 14px', color: 'var(--muted)', fontFamily: 'DM Mono, monospace', fontSize: 11 }}>
                      {r.Started_At?.slice(0, 16).replace('T', ' ')}
                    </td>
                    <td style={{ padding: '9px 14px' }}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 500,
                        background: r.Status === 'Completed' ? 'var(--green-soft)'
                                  : r.Status === 'Failed' ? '#fef2f2'
                                  : 'var(--yellow-soft)',
                        color: r.Status === 'Completed' ? 'var(--green)'
                             : r.Status === 'Failed' ? 'var(--accent)'
                             : 'var(--yellow)'
                      }}>{r.Status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Shared styles ── */
const sectionTitle = {
  fontSize: 11, fontWeight: 600, marginBottom: 14,
  color: 'var(--muted)', textTransform: 'uppercase',
  letterSpacing: '0.08em'
}

const labelStyle = {
  display: 'block', fontSize: 12, color: 'var(--muted)'
}

const inputStyle = {
  display: 'block', width: '100%', marginTop: 5,
  padding: '8px 10px', borderRadius: 'var(--radius-sm)',
  border: '1px solid var(--border)',
  background: 'var(--bg)', fontSize: 13,
  fontFamily: 'DM Mono, monospace',
  color: 'var(--text)', outline: 'none'
}

function CalendarDay({ day }) {
  const [expanded, setExpanded] = useState(false)

  const today = new Date().toISOString().slice(0, 10)
  const isToday = day.date === today
  const isFuture = day.date > today
  const dayName = new Date(day.date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short' })
  const dateLabel = new Date(day.date + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

  const queuedCount = day.emails.filter(e => e.status === 'queued' || e.status === 'sending').length
  const sentCount = day.emails.filter(e => e.status === 'sent').length
  const openedCount = day.emails.filter(e => e.opened).length
  const clickedCount = day.emails.filter(e => e.clicked).length
  const repliedCount = day.emails.filter(e => e.replied).length
  const bouncedCount = day.emails.filter(e => e.bounced).length
  const total = day.emails.length

  if (total === 0) return null

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderLeft: isToday ? '3px solid var(--blue)' : isFuture ? '3px solid var(--yellow)' : '3px solid var(--border)',
      borderRadius: 'var(--radius)', overflow: 'hidden',
      boxShadow: 'var(--shadow-sm)'
    }}>
      <div onClick={() => setExpanded(!expanded)} style={{
        padding: '10px 16px', cursor: 'pointer',
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <div style={{ width: 64, flexShrink: 0 }}>
          <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 12, fontWeight: 500, color: isToday ? 'var(--blue)' : 'var(--text)' }}>{dayName}</div>
          <div style={{ fontSize: 10, color: 'var(--muted)' }}>{dateLabel}</div>
        </div>
        <div style={{ flex: 1, display: 'flex', gap: 2, alignItems: 'center', height: 16 }}>
          {day.emails.map((e, i) => (
            <div key={i} style={{
              width: 6, borderRadius: 1,
              height: e.replied ? 16 : e.clicked ? 12 : e.opened ? 8 : 4,
              background: e.bounced ? 'var(--accent)' : e.replied ? 'var(--green)' : e.clicked ? 'var(--blue)' : e.opened ? 'var(--yellow)' : e.status === 'queued' ? 'var(--border-strong)' : 'var(--border)',
            }} title={e.company || e.cin} />
          ))}
        </div>
        <div style={{ display: 'flex', gap: 10, fontSize: 10, fontFamily: 'DM Mono, monospace', flexShrink: 0 }}>
          {queuedCount > 0 && <span style={{ color: 'var(--yellow)' }}>{queuedCount} queued</span>}
          {sentCount > 0 && <span style={{ color: 'var(--text)' }}>{sentCount} sent</span>}
          {openedCount > 0 && <span style={{ color: 'var(--yellow)' }}>{openedCount} opened</span>}
          {clickedCount > 0 && <span style={{ color: 'var(--blue)' }}>{clickedCount} clicked</span>}
          {repliedCount > 0 && <span style={{ color: 'var(--green)' }}>{repliedCount} replied</span>}
          {bouncedCount > 0 && <span style={{ color: 'var(--accent)' }}>{bouncedCount} bounced</span>}
        </div>
        <div style={{ color: 'var(--muted)', flexShrink: 0 }}>
          {expanded ? '▾' : '▸'}
        </div>
      </div>
      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)' }}>
          {(() => {
            const byHour = {}
            day.emails.forEach(e => {
              const h = e.hour != null ? `${String(e.hour).padStart(2, '0')}:00` : 'Queued'
              if (!byHour[h]) byHour[h] = []
              byHour[h].push(e)
            })
            return Object.entries(byHour).sort().map(([hour, emails]) => (
              <div key={hour}>
                <div style={{
                  padding: '5px 16px 5px 24px', fontSize: 9, fontWeight: 600,
                  color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em',
                  background: 'var(--bg)', borderBottom: '1px solid var(--border)'
                }}>{hour} · {emails.length} email{emails.length > 1 ? 's' : ''}</div>
                {emails.map((e, i) => (
                  <div key={i} style={{
                    padding: '7px 16px 7px 24px', display: 'flex', alignItems: 'center', gap: 10,
                    borderBottom: '1px solid var(--border)', fontSize: 11
                  }}>
                    <div style={{
                      width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                      background: e.bounced ? 'var(--accent)' : e.replied ? 'var(--green)' : e.clicked ? 'var(--blue)' : e.opened ? 'var(--yellow)' : e.status === 'queued' ? 'var(--border-strong)' : 'var(--border)'
                    }} />
                    <div style={{ flex: '0 0 180px', fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.company || e.cin}</div>
                    <div style={{ flex: '0 0 180px', fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.email || '—'}</div>
                    <div style={{ flex: 1, fontFamily: 'DM Mono, monospace', fontSize: 9, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.variant || '—'}</div>
                    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                      {e.status === 'queued' && <Tag text="queued" color="var(--yellow)" bg="var(--yellow-soft)" />}
                      {e.status === 'sending' && <Tag text="sending" color="var(--blue)" bg="var(--blue-soft)" />}
                      {e.opened && <Tag text="opened" color="var(--yellow)" bg="var(--yellow-soft)" />}
                      {e.clicked && <Tag text="clicked" color="var(--blue)" bg="var(--blue-soft)" />}
                      {e.replied && <Tag text="replied" color="var(--green)" bg="var(--green-soft)" />}
                      {e.bounced && <Tag text="bounced" color="var(--accent)" bg="var(--accent-soft)" />}
                      {e.status === 'sent' && !e.opened && !e.clicked && !e.replied && !e.bounced && <Tag text="delivered" color="var(--muted)" bg="var(--bg)" />}
                    </div>
                  </div>
                ))}
              </div>
            ))
          })()}
        </div>
      )}
    </div>
  )
}

function Tag({ text, color, bg }) {
  return (
    <span style={{ fontSize: 8, padding: '1px 5px', borderRadius: 3, background: bg, color, fontWeight: 500, whiteSpace: 'nowrap' }}>{text}</span>
  )
}