'use client'

import { RotateCw } from 'lucide-react'

export default function SearchHistory({ history, activeJobs, recentJobs, onRerun }) {
  // Build a set of active query texts to disable their re-run buttons
  const activeQueries = new Set((activeJobs ?? []).map(j => j.Query_Text.toLowerCase().trim()))

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '16px 18px',
      boxShadow: 'var(--shadow-sm)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Past Searches ({history?.length ?? 0})
        </div>
      </div>

      {/* Active jobs banner */}
      {activeJobs?.length > 0 && (
        <div style={{
          padding: '10px 12px', marginBottom: 12,
          background: 'var(--blue-soft)', border: '1px solid var(--blue)',
          borderRadius: 'var(--radius-sm)', fontSize: 12,
        }}>
          {activeJobs.map(j => (
            <div key={j.Job_ID} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              fontFamily: 'DM Mono, monospace', color: 'var(--blue)',
            }}>
              <span style={{ animation: 'pulse 1.5s ease-in-out infinite' }}>●</span>
              <span style={{ fontWeight: 500 }}>{j.Status}</span>
              <span style={{ color: 'var(--text)' }}>"{j.Query_Text}"</span>
            </div>
          ))}
        </div>
      )}

      {/* Recent done */}
      {recentJobs?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          {dedupRecent(recentJobs).slice(0, 3).map(j => (
            <div key={j.Job_ID} style={{
              padding: '6px 12px', marginBottom: 4, fontSize: 11,
              background: j.Status === 'done' ? 'var(--green-soft)' : 'var(--accent-soft)',
              color: j.Status === 'done' ? 'var(--green)' : 'var(--accent)',
              borderRadius: 'var(--radius-sm)',
              display: 'flex', alignItems: 'center', gap: 8,
              fontFamily: 'DM Mono, monospace',
            }}>
              <span>{j.Status === 'done' ? '✓' : '✕'}</span>
              <span style={{ color: 'var(--text)', flex: 1 }}>{j.Query_Text}</span>
              {j.Status === 'done' ? (
                <span>{j.Leads_Returned} leads · {j.Leads_New} new · {j.Leads_HighQ} HQ</span>
              ) : (
                <span title={j.Error_Message}>error</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* History table */}
      {!history || history.length === 0 ? (
        <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--muted)', fontSize: 12 }}>
          No searches yet. Try one above to get started.
        </div>
      ) : (
        <div style={{ maxHeight: 480, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead style={{ position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Query', 'Last run', 'Runs', 'Total leads', 'New leads', ''].map(h => (
                  <th key={h} style={{
                    padding: '8px 10px', textAlign: 'left',
                    color: 'var(--muted)', fontWeight: 500, fontSize: 10,
                    position: 'sticky', top: 0, background: 'var(--surface)',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map(h => {
                const isActive = activeQueries.has(h.Query_Text.toLowerCase().trim())
                return (
                  <tr key={h.Query_Text} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '8px 10px', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {h.Query_Text}
                    </td>
                    <td style={{ padding: '8px 10px', color: 'var(--muted)', fontFamily: 'DM Mono, monospace', fontSize: 11 }}>
                      {timeAgo(h.last_run)}
                    </td>
                    <td style={{ padding: '8px 10px', fontFamily: 'DM Mono, monospace' }}>
                      {h.run_count}
                    </td>
                    <td style={{ padding: '8px 10px', fontFamily: 'DM Mono, monospace' }}>
                      {h.total_leads || 0}
                    </td>
                    <td style={{ padding: '8px 10px', fontFamily: 'DM Mono, monospace', color: 'var(--green)' }}>
                      {h.total_new || 0}
                    </td>
                    <td style={{ padding: '8px 10px', textAlign: 'right' }}>
                      <button
                        onClick={() => onRerun?.(h.Query_Text)}
                        disabled={isActive}
                        title={isActive ? 'Already running' : 'Run again'}
                        style={{
                          padding: '4px 8px', fontSize: 10,
                          border: '1px solid var(--border)',
                          borderRadius: 4, background: 'var(--surface)',
                          color: 'var(--muted)',
                          cursor: isActive ? 'not-allowed' : 'pointer',
                          opacity: isActive ? 0.5 : 1,
                          display: 'inline-flex', alignItems: 'center', gap: 3,
                        }}
                      >
                        <RotateCw size={10} />
                        Re-run
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function dedupRecent(jobs) {
  // Keep only the most recent entry per query text
  const seen = new Set()
  const out = []
  for (const j of jobs) {
    const key = j.Query_Text.toLowerCase().trim()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(j)
  }
  return out
}


function timeAgo(iso) {
  if (!iso) return '—'
  const d = new Date(iso.replace(' ', 'T') + (iso.includes('Z') ? '' : 'Z'))
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const dd = Math.floor(h / 24)
  return `${dd}d ago`
}