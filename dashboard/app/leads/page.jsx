// dashboard/app/leads/page.jsx
'use client'

import { useState, useEffect } from 'react'
import { Search, ExternalLink, ChevronLeft, ChevronRight } from 'lucide-react'
import { getCountry } from '../lib/api'

const API = 'http://localhost:8000/api'

const STATUS_COLORS = {
  'Enriched_Ready':     { background: 'var(--blue-soft)',   color: 'var(--blue)' },
  'Intelligence_Ready': { background: 'var(--yellow-soft)', color: 'var(--yellow)' },
  'Outreach_Sent':      { background: 'var(--green-soft)',  color: 'var(--green)' },
  'No_Contact_Found':   { background: 'var(--accent-soft)', color: 'var(--accent)' },
  'Failed / Not Found': { background: '#f5f5f4',            color: '#78716c' },
}

export default function LeadsPage() {
  const [leads, setLeads]       = useState([])
  const [total, setTotal]       = useState(0)
  const [page, setPage]         = useState(1)
  const [search, setSearch]     = useState('')
  const [segment, setSegment]   = useState('')
  const [status, setStatus]     = useState('')
  const [segments, setSegments] = useState([])
  const [statuses, setStatuses] = useState([])
  const [selected, setSelected] = useState(null)
  const [country, setCountry]   = useState('india')
  const limit = 50

  useEffect(() => {
    setCountry(getCountry())
    const onCountry = () => { setCountry(getCountry()); setPage(1); setSelected(null) }
    window.addEventListener('cc-country-change', onCountry)
    return () => window.removeEventListener('cc-country-change', onCountry)
  }, [])

  useEffect(() => {
    fetch(`${API}/leads/segments`).then(r => r.json()).then(setSegments).catch(() => {})
    fetch(`${API}/leads/statuses`).then(r => r.json()).then(setStatuses).catch(() => {})
  }, [])

  useEffect(() => { fetchLeads() }, [page, search, segment, status, country])

  async function fetchLeads() {
    try {
      const params = new URLSearchParams({
        page: String(page), limit: String(limit),
        ...(search  && { search }),
        ...(segment && { segment }),
        ...(status  && { status }),
        ...(country === 'us' && { country: 'us' }),
      })
      const r = await fetch(`${API}/leads?${params}`)
      const d = await r.json()
      setLeads(d.leads)
      setTotal(d.total)
    } catch {}
  }

  async function selectLead(cin) {
    try {
      const r = await fetch(`${API}/leads/${cin}`)
      setSelected(await r.json())
    } catch {}
  }

  const pages = Math.ceil(total / limit)

  return (
    <div className="page-enter" style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>

      {/* ── LIST ── */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        borderRight: '1px solid var(--border)', overflow: 'hidden'
      }}>
        {/* Header */}
        <div style={{ padding: '28px 28px 18px', borderBottom: '1px solid var(--border)' }}>
          <h1 style={{ fontSize: 18, fontWeight: 600, marginBottom: 14, letterSpacing: '-0.01em' }}>
            Leads{' '}
            <span style={{ color: 'var(--muted)', fontSize: 14, fontWeight: 400 }}>
              ({total.toLocaleString()})
            </span>
          </h1>

          <div style={{ display: 'flex', gap: 8 }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <Search size={13} style={{
                position: 'absolute', left: 10, top: '50%',
                transform: 'translateY(-50%)', color: 'var(--muted)'
              }} />
              <input
                placeholder="Search CIN or company name..."
                value={search}
                onChange={e => { setSearch(e.target.value); setPage(1) }}
                style={{
                  width: '100%', padding: '8px 10px 8px 32px',
                  border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                  fontSize: 13, background: 'var(--surface)', outline: 'none',
                  color: 'var(--text)'
                }}
              />
            </div>
            <select value={segment} onChange={e => { setSegment(e.target.value); setPage(1) }}
              style={selectStyle}>
              <option value="">All Segments</option>
              {segments.map(s => (
                <option key={s.ICP_Segment} value={s.ICP_Segment}>
                  {s.ICP_Segment.replace('Tier 1: ', '').replace('Tier 2: ', 'T2: ').replace('Tier 3: ', 'T3: ')} ({s.count})
                </option>
              ))}
            </select>
            <select value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}
              style={selectStyle}>
              <option value="">All Statuses</option>
              {statuses.map(s => (
                <option key={s.Pipeline_Status} value={s.Pipeline_Status}>
                  {s.Pipeline_Status || 'NULL'} ({s.count})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Table */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead style={{ position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Company', 'State', 'Capital', 'Pixel', 'Status', 'Contacts'].map(h => (
                  <th key={h} style={{
                    padding: '10px 14px', textAlign: 'left',
                    color: 'var(--muted)', fontWeight: 500, fontSize: 11
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {leads.map(l => (
                <tr key={l.CIN}
                  onClick={() => selectLead(l.CIN)}
                  style={{
                    borderBottom: '1px solid var(--border)',
                    cursor: 'pointer',
                    background: selected?.lead?.CIN === l.CIN ? 'var(--bg)' : 'transparent',
                    transition: 'background 0.1s ease'
                  }}>
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ fontWeight: 500 }}>{l.CompanyName}</div>
                    <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--muted)', marginTop: 1 }}>
                      {l.CIN}
                    </div>
                  </td>
                  <td style={{ padding: '10px 14px', color: 'var(--muted)' }}>{l.State || '—'}</td>
                  <td style={{ padding: '10px 14px', fontFamily: 'DM Mono, monospace' }}>
                    {l.PaidupCapital != null ? `₹${(+l.PaidupCapital / 100000).toFixed(1)}L` : '—'}
                  </td>
                  <td style={{ padding: '10px 14px' }}>
                    {l.Has_Google_Ads_Pixel === 1 ? '✅'
                   : l.Has_Google_Ads_Pixel === 0 ? '❌'
                   : <span style={{ color: 'var(--muted)' }}>—</span>}
                  </td>
                  <td style={{ padding: '10px 14px' }}>
                    {l.Pipeline_Status ? (
                      <span style={{
                        padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 500,
                        ...(STATUS_COLORS[l.Pipeline_Status] || { background: '#f5f5f4', color: '#666' })
                      }}>{l.Pipeline_Status}</span>
                    ) : <span style={{ color: 'var(--muted)' }}>—</span>}
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                    {l.Contact_Count > 0
                      ? <span style={{ color: 'var(--green)', fontWeight: 500 }}>{l.Contact_Count}</span>
                      : <span style={{ color: 'var(--muted)' }}>0</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div style={{
          padding: '12px 18px', borderTop: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          fontSize: 12, color: 'var(--muted)'
        }}>
          <span>Page {page} of {pages} · {total} leads</span>
          <div style={{ display: 'flex', gap: 4 }}>
            <button onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1} style={pageBtn}>
              <ChevronLeft size={14} />
            </button>
            <button onClick={() => setPage(p => Math.min(pages, p + 1))}
              disabled={page === pages} style={pageBtn}>
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* ── DETAIL PANEL ── */}
      <div style={{
        width: 380, flexShrink: 0,
        overflow: 'auto', padding: 28,
        background: 'var(--surface)'
      }}>
        {!selected ? (
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 60, textAlign: 'center' }}>
            Select a lead to view details
          </div>
        ) : (
          <LeadDetail data={selected} onRefresh={() => selectLead(selected.lead.CIN)} />
        )}
      </div>
    </div>
  )
}


function LeadDetail({ data, onRefresh }) {
  const { lead, contacts, outreach } = data
  const [editUrl, setEditUrl] = useState(lead.Website_URL || '')
  const [saving, setSaving]   = useState(false)

  async function saveUrl() {
    setSaving(true)
    await fetch(`${API}/leads/${lead.CIN}/website`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ website_url: editUrl })
    })
    setSaving(false)
    onRefresh()
  }

  const fields = [
    ['Segment',     lead.ICP_Segment],
    ['Industry',    lead.Industry || '—'],
    ['State',       lead.State || '—'],
    ['Capital',     lead.PaidupCapital != null ? `₹${(+lead.PaidupCapital / 100000).toFixed(1)}L` : '—'],
    ['Status',      lead.Pipeline_Status || '—'],
    ['Has GMB',     lead.Has_GMB ? 'Yes' : 'No'],
    ['Pixel',       lead.Has_Google_Ads_Pixel === 1 ? 'Confirmed' : lead.Has_Google_Ads_Pixel === 0 ? 'Not found' : 'Unknown'],
    ['Competitors', lead.Competitor_Count || '—'],
  ]

  return (
    <div style={{ fontSize: 13 }}>
      <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 2, letterSpacing: '-0.01em' }}>
        {lead.CompanyName}
      </div>
      <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--muted)', marginBottom: 20 }}>
        {lead.CIN}
      </div>

      {fields.map(([k, v]) => (
        <div key={k} style={{
          display: 'flex', justifyContent: 'space-between',
          padding: '7px 0', borderBottom: '1px solid var(--border)',
          color: 'var(--muted)', fontSize: 12
        }}>
          <span>{k}</span>
          <span style={{ color: 'var(--text)', fontWeight: 400 }}>{v}</span>
        </div>
      ))}

      {/* Website edit */}
      <div style={{ marginTop: 20, marginBottom: 20 }}>
        <div style={sectionLabel}>Website</div>
        <div style={{ display: 'flex', gap: 6 }}>
          <input value={editUrl} onChange={e => setEditUrl(e.target.value)}
            style={{
              flex: 1, padding: '7px 9px', fontSize: 12,
              border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              fontFamily: 'DM Mono, monospace', background: 'var(--bg)',
              color: 'var(--text)', outline: 'none'
            }} />
          <button onClick={saveUrl} disabled={saving} style={{
            padding: '7px 12px', borderRadius: 'var(--radius-sm)', border: 'none',
            background: 'var(--text)', color: 'white', fontSize: 12, cursor: 'pointer',
            fontWeight: 500
          }}>Save</button>
          {lead.Website_URL && (
            <a href={lead.Website_URL} target="_blank" rel="noreferrer" style={{
              padding: '7px 9px', borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)', display: 'flex', alignItems: 'center',
              color: 'var(--muted)'
            }}>
              <ExternalLink size={12} />
            </a>
          )}
        </div>
      </div>

      {/* Personalized sentence */}
      {lead.Personalized_Sentence && (
        <div style={{ marginBottom: 20 }}>
          <div style={sectionLabel}>Email Copy</div>
          <div style={{
            fontSize: 12, color: 'var(--muted)', lineHeight: 1.7,
            background: 'var(--bg)', padding: 12, borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)'
          }}>{lead.Personalized_Sentence}</div>
        </div>
      )}

      {/* Contacts */}
      <div style={{ marginBottom: 20 }}>
        <div style={sectionLabel}>Contacts ({contacts.length})</div>
        {contacts.length === 0
          ? <div style={{ color: 'var(--muted)', fontSize: 12 }}>No contacts yet</div>
          : contacts.map(c => (
            <div key={c.Contact_ID} style={{
              padding: '10px 12px', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', marginBottom: 6, fontSize: 12
            }}>
              <div style={{ fontWeight: 500 }}>
                {c.Is_Primary_Contact ? '⭐ ' : ''}{c.Full_Name}
              </div>
              <div style={{ color: 'var(--muted)', marginTop: 2 }}>{c.Job_Title} · {c.Email_Label}</div>
              <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, marginTop: 2 }}>{c.Email_Address}</div>
            </div>
          ))
        }
      </div>

      {/* Outreach history */}
      {outreach.length > 0 && (
        <div>
          <div style={sectionLabel}>Outreach History</div>
          {outreach.map(o => (
            <div key={o.Analytics_ID} style={{
              padding: '10px 12px', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', marginBottom: 6, fontSize: 11
            }}>
              <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--muted)' }}>
                {o.Email_Sent_Date} · {o.Batch_ID}
              </div>
              <div style={{ marginTop: 3 }}>{o.Campaign_Variant}</div>
              <div style={{ color: 'var(--muted)', marginTop: 3 }}>
                {o.Audit_Link_Clicked ? '✅ Clicked' : '○ Not clicked'} ·{' '}
                {o.Email_Opened ? '👁 Opened' : '○ Not opened'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


/* ── Shared styles ── */
const sectionLabel = {
  fontSize: 11, color: 'var(--muted)', marginBottom: 8,
  fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em'
}

const selectStyle = {
  padding: '8px 10px', border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)', fontSize: 12,
  background: 'var(--surface)', color: 'var(--text)',
  outline: 'none', cursor: 'pointer'
}

const pageBtn = {
  padding: '5px 9px', border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)', background: 'var(--surface)',
  cursor: 'pointer', display: 'flex', alignItems: 'center'
}