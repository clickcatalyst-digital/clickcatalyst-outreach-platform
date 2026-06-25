// dashboard/app/campaigns/page.jsx
'use client'

import { useState, useEffect } from 'react'
import { getCountry } from '../lib/api'

const API = process.env.NEXT_PUBLIC_API_URL
  || (typeof window !== 'undefined' && window.location.hostname === 'localhost'
        ? 'http://localhost:8000/api' : '/api')

export default function CampaignsPage() {
  const [templates, setTemplates] = useState([])
  const [selected, setSelected]   = useState(null)
  const [preview, setPreview]     = useState(null)
  const [saved, setSaved]         = useState(false)
  const [country, setCountry]     = useState('us')

  useEffect(() => {
    setCountry(getCountry())
    const on = () => { setCountry(getCountry()); setSelected(null) }
    window.addEventListener('cc-country-change', on)
    return () => window.removeEventListener('cc-country-change', on)
  }, [])

  useEffect(() => {
    fetch(`${API}/campaigns?country=${country}`).then(r => r.json()).then(setTemplates).catch(() => {})
  }, [country])

  async function selectTemplate(t) {
    const r = await fetch(`${API}/campaigns/${t.Template_ID}`)
    setSelected(await r.json())
    setPreview(null)
    setSaved(false)
  }

  async function saveTemplate() {
    await fetch(`${API}/campaigns/${selected.Template_ID}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        Subject_Line: selected.Subject_Line,
        Body_HTML:    selected.Body_HTML,
        Body_Plain:   selected.Body_Plain,
        CTA_URL:      selected.CTA_URL,
        Is_Active:    selected.Is_Active,
      })
    })
    setSaved(true)
    fetch(`${API}/campaigns?country=${country}`).then(r => r.json()).then(setTemplates).catch(() => {})
  }

  async function loadPreview() {
    const r = await fetch(`${API}/campaigns/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_id: selected.Template_ID })
    })
    setPreview(await r.json())
  }

  // Group templates by segment
  const grouped = templates.reduce((acc, t) => {
    if (!acc[t.Segment]) acc[t.Segment] = []
    acc[t.Segment].push(t)
    return acc
  }, {})

  return (
    <div className="page-enter" style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>

      {/* ── TEMPLATE LIST ── */}
      <div style={{
        width: 280, flexShrink: 0,
        borderRight: '1px solid var(--border)',
        overflow: 'auto', padding: '28px 0',
        background: 'var(--surface)'
      }}>
        <div style={{ padding: '0 20px 20px', fontSize: 16, fontWeight: 600, letterSpacing: '-0.01em' }}>
          Campaigns
        </div>

        {Object.entries(grouped).map(([seg, tmps]) => (
          <div key={seg}>
            <div style={{
              padding: '8px 20px', fontSize: 10, fontWeight: 600,
              color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.1em'
            }}>{seg}</div>
            {tmps.map(t => (
              <div key={t.Template_ID} onClick={() => selectTemplate(t)} style={{
                padding: '10px 20px', cursor: 'pointer', fontSize: 12,
                background: selected?.Template_ID === t.Template_ID ? 'var(--bg)' : 'transparent',
                borderLeft: selected?.Template_ID === t.Template_ID
                  ? '2px solid var(--text)' : '2px solid transparent',
                transition: 'all 0.1s ease'
              }}>
                <div style={{ fontWeight: 500, marginBottom: 3 }}>
                  {t.Variant_Key.replace(/_/g, ' ')}
                  {!t.Is_Active && (
                    <span style={{ color: 'var(--muted)', marginLeft: 6, fontSize: 10 }}>(off)</span>
                  )}
                </div>
                <div style={{
                  color: 'var(--muted)', fontSize: 10,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                }}>{t.Subject_Line}</div>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* ── EDITOR ── */}
      <div style={{ flex: 1, overflow: 'auto', padding: '36px 40px' }}>
        {!selected ? (
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 80, textAlign: 'center' }}>
            Select a template to edit
          </div>
        ) : (
          <div style={{ maxWidth: 800 }}>
            <div style={{
              display: 'flex', justifyContent: 'space-between',
              alignItems: 'center', marginBottom: 28
            }}>
              <div>
                <div style={{
                  fontFamily: 'DM Mono, monospace', fontSize: 11,
                  color: 'var(--muted)', marginBottom: 4
                }}>{selected.Variant_Key}</div>
                <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: '-0.01em' }}>
                  {selected.Segment}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <label style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  fontSize: 13, cursor: 'pointer', color: 'var(--text)'
                }}>
                  <input type="checkbox" checked={!!selected.Is_Active}
                    onChange={e => setSelected(s => ({ ...s, Is_Active: e.target.checked ? 1 : 0 }))} />
                  Active
                </label>
                <button onClick={loadPreview} style={btnGhost}>Preview</button>
                <button onClick={saveTemplate} style={btnPrimary}>
                  {saved ? '✓ Saved' : 'Save Changes'}
                </button>
              </div>
            </div>

            <label style={fieldLabel}>
              Subject Line
              <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 4 }}>
                Use {'{company_name}'}, {'{competitor_count}'} as variables
              </div>
              <input value={selected.Subject_Line}
                onChange={e => setSelected(s => ({ ...s, Subject_Line: e.target.value }))}
                style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }} />
            </label>

            <label style={fieldLabel}>
              CTA URL
              <input value={selected.CTA_URL}
                onChange={e => setSelected(s => ({ ...s, CTA_URL: e.target.value }))}
                style={{ ...inputStyle, fontFamily: 'DM Mono, monospace' }} />
            </label>

            <label style={fieldLabel}>
              HTML Body
              <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 4 }}>
                Variables: {'{company_name}'} {'{personalized_sentence}'} {'{audit_url}'}
              </div>
              <textarea value={selected.Body_HTML} rows={12}
                onChange={e => setSelected(s => ({ ...s, Body_HTML: e.target.value }))}
                style={{
                  ...inputStyle, fontFamily: 'DM Mono, monospace',
                  fontSize: 11, resize: 'vertical'
                }} />
            </label>

            <label style={fieldLabel}>
              Plain Text Body
              <textarea value={selected.Body_Plain} rows={8}
                onChange={e => setSelected(s => ({ ...s, Body_Plain: e.target.value }))}
                style={{
                  ...inputStyle, fontFamily: 'DM Mono, monospace',
                  fontSize: 11, resize: 'vertical'
                }} />
            </label>

            {/* Preview */}
            {preview && (
              <div style={{ marginTop: 36 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>
                  Preview (sample data)
                </div>
                <div style={{
                  background: 'var(--bg)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)', padding: 24
                }}>
                  <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 4 }}>Subject:</div>
                  <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 20 }}>{preview.subject}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>HTML:</div>
                  <div style={{
                    background: 'white', padding: 24, borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border)'
                  }}
                    dangerouslySetInnerHTML={{ __html: preview.body_html }} />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}


/* ── Shared styles ── */
const fieldLabel = {
  display: 'block', fontSize: 12, color: 'var(--muted)', marginBottom: 16
}

const inputStyle = {
  display: 'block', width: '100%', marginTop: 5,
  padding: '9px 12px', border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)', fontSize: 13,
  background: 'var(--surface)', color: 'var(--text)', outline: 'none'
}

const btnPrimary = {
  padding: '9px 18px', background: 'var(--text)', color: 'white',
  border: 'none', borderRadius: 'var(--radius-sm)', fontSize: 13,
  cursor: 'pointer', fontWeight: 500
}

const btnGhost = {
  padding: '9px 16px', background: 'transparent', color: 'var(--muted)',
  border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
  fontSize: 13, cursor: 'pointer'
}