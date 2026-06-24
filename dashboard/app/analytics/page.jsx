// dashboard/app/analytics/page.jsx
'use client'

import { useState, useEffect } from 'react'
import { getCountry } from '../lib/api'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  LineChart, Line, CartesianGrid, ResponsiveContainer, Legend
} from 'recharts'

const API = 'http://localhost:8000/api'

export default function AnalyticsPage() {
  const [overview, setOverview]   = useState(null)
  const [byVariant, setByVariant] = useState([])
  const [byBatch, setByBatch]     = useState([])
  const [timeline, setTimeline]   = useState([])
  const [abTests, setAbTests]   = useState([])
  const [scheduler, setScheduler] = useState(null)
  const [bayesian, setBayesian]   = useState(null)
  const [country, setCountry]     = useState('us')

  useEffect(() => {
    setCountry(getCountry())
    const on = () => setCountry(getCountry())
    window.addEventListener('cc-country-change', on)
    return () => window.removeEventListener('cc-country-change', on)
  }, [])

  useEffect(() => {
    const c = `?country=${country}`
    fetch(`${API}/analytics/overview${c}`).then(r => r.json()).then(setOverview).catch(() => {})
    fetch(`${API}/analytics/by-variant${c}`).then(r => r.json()).then(setByVariant).catch(() => {})
    fetch(`${API}/analytics/by-batch${c}`).then(r => r.json()).then(setByBatch).catch(() => {})
    fetch(`${API}/analytics/timeline${c}`).then(r => r.json()).then(setTimeline).catch(() => {})
    fetch(`${API}/analytics/ab-tests${c}`).then(r => r.json()).then(setAbTests).catch(() => {})
    fetch(`${API}/analytics/bayesian${c}`).then(r => r.json()).then(setBayesian).catch(() => {})
    // The legacy send-scheduler is India-only; US scheduling lives on the US Outreach tab.
    if (country === 'india') {
      fetch(`${API}/pipeline/scheduler/status`).then(r => r.json()).then(setScheduler).catch(() => {})
    } else {
      setScheduler(null)
    }
  }, [country])

  const metricCards = overview ? [
    { label: 'Total Sent',       value: overview.total_sent,       color: 'var(--text)' },
    { label: 'Unique Companies', value: overview.unique_companies, color: '#2563eb' },
    { label: 'Total Clicked',    value: overview.total_clicked,    color: '#16a34a' },
    { label: 'Click Rate',       value: `${overview.click_rate}%`, color: '#16a34a' },
    { label: 'Total Opened',     value: overview.total_opened,     color: '#ca8a04' },
    { label: 'Open Rate',        value: `${overview.open_rate}%`,  color: '#ca8a04' },
    { label: 'Reply Rate',        value: `${overview.reply_rate}%`,  color: '#6661df' },
  ] : []

  return (
    <div className="page-enter" style={{ padding: '36px 44px' }}>
      <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 4, letterSpacing: '-0.01em' }}>
        Analytics
      </h1>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 32 }}>
        Campaign performance across all batches and variants.
      </p>

      {/* Metric cards */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)',
        gap: 10, marginBottom: 36
      }}>
        {metricCards.map(({ label, value, color }) => (
          <div key={label} style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '18px 20px',
            boxShadow: 'var(--shadow-sm)'
          }}>
            <div style={{
              fontFamily: 'DM Mono, monospace', fontSize: 24,
              fontWeight: 500, color
            }}>{value ?? '—'}</div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>

        {/* Timeline */}
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: 26,
          boxShadow: 'var(--shadow-sm)'
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 20 }}>
            Daily Activity (last 30 days)
          </div>
          {timeline.length === 0
            ? <NoData />
            : (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={timeline}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#8c8c86' }}
                    tickFormatter={d => d.slice(5)} />
                  <YAxis tick={{ fontSize: 10, fill: '#8c8c86' }} />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--surface)', border: '1px solid var(--border)',
                      borderRadius: 8, fontSize: 12, boxShadow: 'var(--shadow-md)'
                    }} />
                  <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="sent" stroke="#2563eb"
                    dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="clicked" stroke="#16a34a"
                    dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            )
          }
        </div>

        {/* By variant */}
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: 26,
          boxShadow: 'var(--shadow-sm)'
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 20 }}>
            Click Rate by Variant
          </div>
          {byVariant.length === 0
            ? <NoData />
            : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={byVariant} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis type="number" tick={{ fontSize: 10, fill: '#8c8c86' }} unit="%" />
                  <YAxis type="category" dataKey="Campaign_Variant"
                    tick={{ fontSize: 9, fill: '#8c8c86' }} width={140} />
                  <Tooltip
                    formatter={v => `${v}%`}
                    contentStyle={{
                      background: 'var(--surface)', border: '1px solid var(--border)',
                      borderRadius: 8, fontSize: 12, boxShadow: 'var(--shadow-md)'
                    }} />
                  <Bar dataKey="click_rate" fill="#2563eb" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )
          }
        </div>
      </div>

      {/* Batch history table */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden',
        boxShadow: 'var(--shadow-sm)'
      }}>
        <div style={{
          padding: '15px 22px', borderBottom: '1px solid var(--border)',
          fontSize: 13, fontWeight: 600
        }}>Batch History</div>
        {byBatch.length === 0
          ? <div style={{ padding: 28, color: 'var(--muted)', fontSize: 13 }}>
              No batches sent yet.
            </div>
          : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Batch ID', 'Date', 'Sent', 'Clicked', 'CTR'].map(h => (
                    <th key={h} style={{
                      padding: '10px 18px', textAlign: 'left',
                      color: 'var(--muted)', fontWeight: 500, fontSize: 11
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {byBatch.map(b => (
                  <tr key={b.Batch_ID} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{
                      padding: '10px 18px', fontFamily: 'DM Mono, monospace', fontSize: 11
                    }}>{b.Batch_ID}</td>
                    <td style={{ padding: '10px 18px', color: 'var(--muted)' }}>{b.sent_date}</td>
                    <td style={{ padding: '10px 18px' }}>{b.sent}</td>
                    <td style={{ padding: '10px 18px', color: 'var(--green)', fontWeight: 500 }}>
                      {b.clicked}
                    </td>
                    <td style={{ padding: '10px 18px', fontWeight: 500 }}>
                      {b.sent > 0 ? `${((b.clicked / b.sent) * 100).toFixed(1)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      </div>
      
      {/* A/B Test Results */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden', marginTop: 24,
        boxShadow: 'var(--shadow-sm)'
      }}>
        <div style={{
          padding: '15px 22px', borderBottom: '1px solid var(--border)',
          fontSize: 13, fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center'
        }}>
          <span>A/B test results</span>
          <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 400 }}>
            Two-proportion z-test · p {'<'} 0.05 = significant
          </span>
        </div>

        {abTests.length === 0
          ? <div style={{ padding: 24, color: 'var(--muted)', fontSize: 13 }}>
              No A/B data yet — send emails with variant routing active.
            </div>
          : <div style={{ padding: '16px 22px' }}>
              {abTests.map(test => (
                <ABTestCard key={test.base} test={test} onPromote={async (winnerKey) => {
                  await fetch(`${API}/campaigns/ab-promote`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ winner_variant: winnerKey })
                  })
                  fetch(`${API}/analytics/ab-tests?country=${country}`).then(r => r.json()).then(setAbTests)
                }} />
              ))}
            </div>
        }
      </div>

      {/* ── Scheduler Status ── */}
      {scheduler && (
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20,
          marginTop: 24
        }}>
          {/* Warmup & Volume */}
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: 26,
            boxShadow: 'var(--shadow-sm)'
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 20 }}>
              Send scheduler
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 20 }}>
              {[
                { label: 'Warmup day', value: scheduler.warmup_day, color: 'var(--blue)' },
                { label: 'Daily limit', value: scheduler.daily_limit, color: 'var(--text)' },
                { label: 'Sent today', value: `${scheduler.sent_today} / ${scheduler.daily_limit}`, color: scheduler.sent_today >= scheduler.daily_limit ? 'var(--green)' : 'var(--text)' },
              ].map(m => (
                <div key={m.label} style={{ padding: '12px 14px', background: 'var(--bg)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 20, fontWeight: 500, color: m.color }}>
                    {m.value}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{m.label}</div>
                </div>
              ))}
            </div>
            {/* Send window indicator */}
            <div style={{
              padding: '10px 14px', borderRadius: 'var(--radius-sm)',
              background: scheduler.can_send ? 'var(--green-soft)' : 'var(--accent-soft)',
              border: `1px solid ${scheduler.can_send ? 'var(--green)' : 'var(--accent)'}`,
              fontSize: 12, fontWeight: 500,
              color: scheduler.can_send ? 'var(--green)' : 'var(--accent)',
              marginBottom: 14
            }}>
              {scheduler.can_send
                ? `${scheduler.is_peak ? '⚡ Peak hour' : '✅ Good window'} — ${scheduler.remaining} sends remaining`
                : scheduler.is_weekend ? '⏸ Weekend — no sends' : `⏸ Outside business hours (${scheduler.current_hour}:00)`
              }
            </div>
            <div style={{ fontSize: 11, color: 'var(--muted)' }}>
              Queue: {scheduler.queue_size} leads ready · Sent this week: {scheduler.sent_week}
            </div>
          </div>

          {/* Hour performance heatmap */}
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: 26,
            boxShadow: 'var(--shadow-sm)'
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 20 }}>
              Performance by hour
            </div>
            {(!scheduler.by_hour || scheduler.by_hour.length === 0)
              ? <div style={{ color: 'var(--muted)', fontSize: 12 }}>No data yet</div>
              : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {scheduler.by_hour.map(h => {
                    const openRate = h.sent > 0 ? (h.opened / h.sent * 100) : 0
                    return (
                      <div key={h.Send_Hour} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--muted)', width: 36 }}>
                          {String(h.Send_Hour).padStart(2, '0')}:00
                        </span>
                        <div style={{ flex: 1, height: 6, background: 'var(--bg)', borderRadius: 3, overflow: 'hidden' }}>
                          <div style={{
                            height: '100%', borderRadius: 3,
                            width: `${Math.min(openRate * 2, 100)}%`,
                            background: openRate > 40 ? 'var(--green)' : openRate > 20 ? 'var(--blue)' : 'var(--border-strong)'
                          }} />
                        </div>
                        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--muted)', width: 50, textAlign: 'right' }}>
                          {openRate.toFixed(0)}% open
                        </span>
                      </div>
                    )
                  })}
                </div>
              )
            }
            {scheduler.by_day?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8 }}>By day of week</div>
                <div style={{ display: 'flex', gap: 6 }}>
                  {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((name, i) => {
                    const d = scheduler.by_day?.find(x => x.Send_DayOfWeek === i)
                    const openRate = d && d.sent > 0 ? (d.opened / d.sent * 100) : 0
                    return (
                      <div key={name} style={{
                        flex: 1, textAlign: 'center', padding: '6px 0',
                        borderRadius: 'var(--radius-sm)',
                        background: openRate > 40 ? 'var(--green-soft)' : openRate > 20 ? 'var(--blue-soft)' : 'var(--bg)',
                        fontSize: 10
                      }}>
                        <div style={{ color: 'var(--muted)', marginBottom: 2 }}>{name}</div>
                        <div style={{ fontFamily: 'DM Mono, monospace', fontWeight: 500, color: 'var(--text)' }}>
                          {d ? `${openRate.toFixed(0)}%` : '—'}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Bayesian Model ── */}
      {bayesian && (
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20,
          marginTop: 24
        }}>
          {/* Deliverability */}
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: 26,
            boxShadow: 'var(--shadow-sm)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Domain reputation</div>
              <span style={{
                fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 4,
                background: bayesian.deliverability.reputation >= 0.6 ? 'var(--green-soft)' : bayesian.deliverability.reputation >= 0.3 ? 'var(--yellow-soft)' : 'var(--accent-soft)',
                color: bayesian.deliverability.reputation >= 0.6 ? 'var(--green)' : bayesian.deliverability.reputation >= 0.3 ? 'var(--yellow)' : 'var(--accent)',
              }}>
                {bayesian.deliverability.trend}
              </span>
            </div>
            {/* Score bar */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 28, fontWeight: 500 }}>
                  {(bayesian.deliverability.reputation * 100).toFixed(0)}
                </span>
                <span style={{ fontSize: 11, color: 'var(--muted)', alignSelf: 'flex-end' }}>/ 100</span>
              </div>
              <div style={{ height: 8, background: 'var(--bg)', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 4,
                  width: `${bayesian.deliverability.reputation * 100}%`,
                  background: bayesian.deliverability.reputation >= 0.6 ? 'var(--green)' : bayesian.deliverability.reputation >= 0.3 ? 'var(--yellow)' : 'var(--accent)',
                  transition: 'width 0.5s ease'
                }} />
              </div>
            </div>
            {/* History sparkline */}
            {bayesian.deliverability.history.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'end', gap: 2, height: 40, marginBottom: 12 }}>
                {bayesian.deliverability.history.map((h, i) => (
                  <div key={i} style={{
                    flex: 1, borderRadius: 2,
                    height: `${h.reputation * 100}%`,
                    background: h.reputation >= 0.6 ? 'var(--green)' : h.reputation >= 0.3 ? 'var(--yellow)' : 'var(--accent)',
                    opacity: 0.6
                  }} title={`${h.date}: ${(h.reputation * 100).toFixed(0)}`} />
                ))}
              </div>
            )}
            {/* Reply stats */}
            <div style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', gap: 16 }}>
              <span>Replies: {bayesian.reply_stats.total_replies}</span>
              <span>Reply rate: {bayesian.reply_stats.reply_rate}%</span>
              <span>Companies replied: {bayesian.reply_stats.unique_companies}</span>
            </div>
          </div>

          {/* Thompson Sampling variants */}
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: 26, overflow: 'hidden',
            boxShadow: 'var(--shadow-sm)'
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>
              Thompson sampling posteriors
            </div>
            {bayesian.variants.length === 0
              ? <div style={{ color: 'var(--muted)', fontSize: 12 }}>No variant data yet</div>
              : (
                <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border)' }}>
                        {['Variant', 'Sent', 'Clicks', 'Mean', '95% CI'].map(h => (
                          <th key={h} style={{ padding: '6px 8px', textAlign: 'left', color: 'var(--muted)', fontWeight: 500 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {bayesian.variants.sort((a, b) => b.mean - a.mean).map(v => (
                        <tr key={v.Campaign_Variant} style={{ borderBottom: '1px solid var(--border)' }}>
                          <td style={{ padding: '6px 8px', fontFamily: 'DM Mono, monospace', fontSize: 10 }}>
                            {v.Campaign_Variant}
                          </td>
                          <td style={{ padding: '6px 8px' }}>{v.total}</td>
                          <td style={{ padding: '6px 8px', color: 'var(--green)' }}>{v.clicked}</td>
                          <td style={{ padding: '6px 8px', fontWeight: 500 }}>{(v.mean * 100).toFixed(1)}%</td>
                          <td style={{ padding: '6px 8px', color: 'var(--muted)', fontFamily: 'DM Mono, monospace' }}>
                            [{(v.ci_low * 100).toFixed(1)}–{(v.ci_high * 100).toFixed(1)}]
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            }
          </div>
        </div>
      )}

    </div>
  )
}


function NoData() {
  return (
    <div style={{
      height: 200, display: 'flex', alignItems: 'center',
      justifyContent: 'center', color: 'var(--muted)', fontSize: 13
    }}>
      No data yet — send some emails first.
    </div>
  )
}


function ABTestCard({ test, onPromote }) {
  const { base, a, b, winner, significant, p_value, min_sample } = test

  function variantBar(data, side, isWinner, isSignificant) {
    if (!data) return (
      <div style={{
        flex: 1, padding: '14px 16px', background: 'var(--bg)',
        borderRadius: 'var(--radius-sm)', fontSize: 12, color: 'var(--muted)'
      }}>
        Variant {side.toUpperCase()} — no data yet
      </div>
    )

    return (
      <div style={{
        flex: 1, padding: '14px 16px',
        background: isWinner && isSignificant ? 'var(--green-soft)' : 'var(--bg)',
        borderRadius: 'var(--radius-sm)',
        border: isWinner && isSignificant ? '1px solid var(--green)' : '1px solid var(--border)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 500 }}>
            Variant {side.toUpperCase()}
            {isWinner && isSignificant && ' ✓ winner'}
          </span>
          <span style={{
            fontFamily: 'DM Mono, monospace', fontSize: 18, fontWeight: 500,
            color: isWinner && isSignificant ? 'var(--green)' : 'var(--text)'
          }}>{data.click_rate}%</span>
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', gap: 12 }}>
          <span>{data.sent} sent</span>
          <span>{data.clicked} clicked</span>
          <span>{data.opened} opened</span>
          <span>{data.open_rate}% open rate</span>
        </div>
        {/* Visual bar */}
        <div style={{
          marginTop: 8, height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden'
        }}>
          <div style={{
            height: '100%', borderRadius: 2,
            width: `${Math.min(data.click_rate * 2, 100)}%`,
            background: isWinner && isSignificant ? 'var(--green)' : 'var(--blue)',
            transition: 'width 0.3s ease'
          }} />
        </div>
      </div>
    )
  }

  const totalSent = (a?.sent || 0) + (b?.sent || 0)

  return (
    <div style={{
      marginBottom: 16, padding: '18px 20px',
      border: '1px solid var(--border)', borderRadius: 'var(--radius)',
      background: 'var(--surface)'
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500 }}>
            {base.replace(/_/g, ' ')}
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'DM Mono, monospace', marginTop: 2 }}>
            {totalSent} total sends
            {min_sample && ` · need ~${min_sample} per variant for 80% power`}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {p_value !== null && (
            <span style={{
              fontSize: 11, fontFamily: 'DM Mono, monospace',
              padding: '3px 8px', borderRadius: 4,
              background: significant ? 'var(--green-soft)' : 'var(--yellow-soft)',
              color: significant ? 'var(--green)' : 'var(--yellow)',
              fontWeight: 500
            }}>
              p = {p_value}
            </span>
          )}
          {significant && winner && (
            <button onClick={() => {
              const winnerKey = winner === 'a' ? a.variant : b.variant
              if (confirm(`Promote ${winnerKey} and deactivate the loser?`)) {
                onPromote(winnerKey)
              }
            }} style={{
              padding: '5px 12px', fontSize: 11, fontWeight: 500,
              background: 'var(--green)', color: 'white', border: 'none',
              borderRadius: 'var(--radius-sm)', cursor: 'pointer'
            }}>
              Promote winner
            </button>
          )}
        </div>
      </div>

      {/* A vs B comparison */}
      <div style={{ display: 'flex', gap: 10 }}>
        {variantBar(a, 'a', winner === 'a', significant)}
        {variantBar(b, 'b', winner === 'b', significant)}
      </div>

      {/* Sample size warning */}
      {min_sample && totalSent < min_sample * 2 && !significant && (
        <div style={{
          marginTop: 10, fontSize: 11, color: 'var(--yellow)',
          padding: '8px 12px', background: 'var(--yellow-soft)',
          borderRadius: 'var(--radius-sm)'
        }}>
          Not enough data yet — need ~{min_sample} sends per variant to detect a 5 percentage point difference with 80% power.
        </div>
      )}
    </div>
  )
}