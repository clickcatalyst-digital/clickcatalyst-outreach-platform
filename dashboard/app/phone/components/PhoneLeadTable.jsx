'use client'

import { Search, Phone, Star, ChevronLeft, ChevronRight, MessageSquare } from 'lucide-react'

export default function PhoneLeadTable({
  leads, total, counts, cities,
  tab, setTab,
  search, setSearch,
  city, setCity,
  pixel, setPixel,
  page, setPage,
  selectedCin,
  onSelectLead,
  loading,
}) {
  const limit = 50
  const pages = Math.max(1, Math.ceil(total / limit))

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      borderRight: '1px solid var(--border)', overflow: 'hidden'
    }}>
      {/* Header */}
      <div style={{ padding: '28px 28px 14px', borderBottom: '1px solid var(--border)' }}>
        <h1 style={{ fontSize: 18, fontWeight: 600, marginBottom: 14, letterSpacing: '-0.01em' }}>
          Phone{' '}
          <span style={{ color: 'var(--muted)', fontSize: 14, fontWeight: 400 }}>
            ({total.toLocaleString()})
          </span>
        </h1>

        {/* Sub-tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 14 }}>
          <TabButton
            active={tab === 'to_call'}
            onClick={() => { setTab('to_call'); setPage(1) }}
            label="To call"
            count={counts?.to_call ?? 0}
            color="var(--blue)"
          />
          <TabButton
            active={tab === 'contacted'}
            onClick={() => { setTab('contacted'); setPage(1) }}
            label="Contacted"
            count={counts?.contacted ?? 0}
            color="var(--green)"
          />
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 8 }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={13} style={{
              position: 'absolute', left: 10, top: '50%',
              transform: 'translateY(-50%)', color: 'var(--muted)'
            }} />
            <input
              placeholder="Search company name..."
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
          <select
            value={city}
            onChange={e => { setCity(e.target.value); setPage(1) }}
            style={selectStyle}
          >
            <option value="">All Cities</option>
            {(cities ?? []).map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <select
            value={pixel}
            onChange={e => { setPixel(e.target.value); setPage(1) }}
            style={selectStyle}
            title="Filter by Google Ads pixel status"
          >
            <option value="">All Pixel</option>
            <option value="yes">✓ Has pixel</option>
            <option value="no">✕ No pixel</option>
            <option value="unchecked">— Unchecked</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead style={{ position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Company', 'Phone', 'Pixel', 'Rating', 'Quality', tab === 'contacted' ? 'Last note' : 'City'].map(h => (
                <th key={h} style={{
                  padding: '10px 14px', textAlign: 'left',
                  color: 'var(--muted)', fontWeight: 500, fontSize: 11
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {leads.length === 0 && !loading && (
              <tr>
                <td colSpan={5} style={{ padding: 60, textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>
                  {tab === 'to_call'
                    ? 'No leads to call. Try clearing filters or run more searches.'
                    : 'No contacted leads yet. Make some calls!'}
                </td>
              </tr>
            )}
            {leads.map(l => (
              <tr key={l.CIN}
                onClick={() => onSelectLead(l)}
                style={{
                  borderBottom: '1px solid var(--border)',
                  cursor: 'pointer',
                  background: selectedCin === l.CIN ? 'var(--bg)' : 'transparent',
                  transition: 'background 0.1s ease'
                }}>
                {/* Company */}
                <td style={{ padding: '10px 14px', maxWidth: 260 }}>
                  <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {l.Display_Name}
                  </div>
                  <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--muted)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {l.Source_Query}
                  </div>
                </td>
                {/* Phone */}
                <td style={{ padding: '10px 14px' }}>
                  <a
                    href={`tel:${l.National_Phone || l.Phone_Formatted}`}
                    onClick={e => e.stopPropagation()}
                    style={{
                      fontFamily: 'DM Mono, monospace', fontSize: 12,
                      color: 'var(--blue)', textDecoration: 'none',
                      display: 'inline-flex', alignItems: 'center', gap: 5
                    }}
                  >
                    <Phone size={11} />
                    {l.Phone_Formatted}
                  </a>
                </td>
                {/* Pixel */}
                <td style={{ padding: '10px 14px' }}>
                  <PixelBadge value={l.Has_Google_Ads_Pixel} />
                </td>
                {/* Rating */}
                <td style={{ padding: '10px 14px' }}>
                  {l.Rating ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 11 }}>
                      <Star size={11} color="#ca8a04" fill="#ca8a04" />
                      <span style={{ fontFamily: 'DM Mono, monospace', fontWeight: 500 }}>{l.Rating}</span>
                      <span style={{ color: 'var(--muted)', fontSize: 10 }}>({l.User_Rating_Count})</span>
                    </span>
                  ) : <span style={{ color: 'var(--muted)' }}>—</span>}
                </td>
                {/* Quality */}
                <td style={{ padding: '10px 14px' }}>
                  <QualityBadge score={l.Quality_Score} />
                </td>
                {/* Last note OR city */}
                <td style={{ padding: '10px 14px', color: 'var(--muted)', fontSize: 11, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {tab === 'contacted' ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                      <MessageSquare size={10} />
                      {l.Last_Comment || '—'}
                    </span>
                  ) : (
                    extractCity(l.Formatted_Address)
                  )}
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
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} style={pageBtn}>
            <ChevronLeft size={14} />
          </button>
          <button onClick={() => setPage(p => Math.min(pages, p + 1))} disabled={page === pages} style={pageBtn}>
            <ChevronRight size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}

function TabButton({ active, onClick, label, count, color }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '6px 14px', fontSize: 12, fontWeight: 500,
        borderRadius: 'var(--radius-sm)', border: '1px solid',
        cursor: 'pointer',
        background: active ? color : 'var(--surface)',
        color: active ? 'white' : 'var(--muted)',
        borderColor: active ? color : 'var(--border)',
        transition: 'all 0.15s ease',
        display: 'inline-flex', alignItems: 'center', gap: 6,
      }}
    >
      {label}
      <span style={{
        fontFamily: 'DM Mono, monospace', fontSize: 11,
        padding: '0 5px', borderRadius: 3,
        background: active ? 'rgba(255,255,255,0.25)' : 'var(--bg)',
        color: active ? 'white' : 'var(--muted)',
      }}>{count}</span>
    </button>
  )
}

function QualityBadge({ score }) {
  if (score == null) return <span style={{ color: 'var(--muted)' }}>—</span>
  const tier =
    score >= 85 ? { bg: 'var(--green-soft)', fg: 'var(--green)', label: 'High' } :
    score >= 60 ? { bg: 'var(--blue-soft)',  fg: 'var(--blue)',  label: 'Good' } :
    score >= 40 ? { bg: 'var(--yellow-soft)',fg: 'var(--yellow)',label: 'OK' } :
                  { bg: 'var(--accent-soft)',fg: 'var(--accent)',label: 'Low' }
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 500,
      background: tier.bg, color: tier.fg,
      fontFamily: 'DM Mono, monospace',
    }}>
      {score} {tier.label}
    </span>
  )
}

function PixelBadge({ value }) {
  if (value === 1 || value === true) {
    return (
      <span title="Has Google Ads tracking on own site"
        style={{ color: 'var(--green)', fontSize: 14, fontWeight: 500 }}>
        ✓
      </span>
    )
  }
  if (value === 0 || value === false) {
    return (
      <span title="No Google Ads tracking detected"
        style={{ color: 'var(--accent)', fontSize: 14 }}>
        ✕
      </span>
    )
  }
  return (
    <span title="Not yet checked or unreachable" style={{ color: 'var(--muted)' }}>
      —
    </span>
  )
}

function extractCity(address) {
  if (!address) return ''
  const cities = ['Mumbai', 'Bangalore', 'Bengaluru', 'Ahmedabad', 'Delhi', 'Pune', 'Hyderabad', 'Chennai', 'Kolkata']
  const found = cities.find(c => address.includes(c))
  return found || address.split(',').slice(-3, -2)[0]?.trim() || ''
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