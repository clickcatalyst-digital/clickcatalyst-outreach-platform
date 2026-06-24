'use client'

import { useState, useEffect } from 'react'
import { Play, AlertCircle } from 'lucide-react'
import { checkKeyword, enqueueSearch } from '../lib/api'

const TEMPLATES = [
  'PPC agency in {city}',
  'Google Ads agency in {city}',
  'performance marketing agency in {city}',
  'digital marketing agency in {city}',
  'SEM agency in {city}',
  'paid media agency in {city}',
  'ecommerce marketing agency in {city}',
  'B2B marketing agency in {city}',
]

export default function SearchForm({ cities, onJobEnqueued }) {
  const [mode, setMode]         = useState('template')  // 'template' | 'freeform'
  const [template, setTemplate] = useState(TEMPLATES[0])
  const [cityKey, setCityKey]   = useState('')

  // Default to first city once cities load
  useEffect(() => {
    if (cities?.length > 0 && !cityKey) {
      setCityKey(cities[0].key)
    }
  }, [cities, cityKey])

  const [freeform, setFreeform] = useState('')
  const [warning, setWarning]   = useState(null)
  const [running, setRunning]   = useState(false)

  // Build the actual query string from current state
  const cityName = cities?.find(c => c.key === cityKey)?.name || ''
  const builtQuery = mode === 'template'
    ? template.replace('{city}', cityName)
    : freeform.trim()

  // Check for existing keyword whenever query changes
  useEffect(() => {
    if (!builtQuery) { setWarning(null); return }
    const t = setTimeout(async () => {
      const result = await checkKeyword(builtQuery)
      if (result?.exists) {
        const days = daysSince(result.last_run)
        setWarning({
          message: `Last searched ${days === 0 ? 'today' : `${days}d ago`} · ${result.total_leads} leads found · ${result.run_count} run${result.run_count > 1 ? 's' : ''}`,
          severity: days < 1 ? 'high' : days < 7 ? 'medium' : 'low',
          ...result,
        })
      } else {
        setWarning(null)
      }
    }, 300)
    return () => clearTimeout(t)
  }, [builtQuery])

  async function submit() {
    if (!builtQuery || running) return
    setRunning(true)
    const cityHint = mode === 'template' ? cityKey : null
    const res = await enqueueSearch(builtQuery, cityHint)
    setRunning(false)
    if (res?.job_id) {
      onJobEnqueued?.(res.job_id)
      if (mode === 'freeform') setFreeform('')
    }
  }

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '18px 20px', marginBottom: 20,
      boxShadow: 'var(--shadow-sm)'
    }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 12 }}>
        Run a search
      </div>

      {/* Mode toggle */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 14 }}>
        <ModeButton active={mode === 'template'} onClick={() => setMode('template')} label="Template + city" />
        <ModeButton active={mode === 'freeform'} onClick={() => setMode('freeform')} label="Free-form" />
      </div>

      {/* Inputs */}
      {mode === 'template' ? (
        <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
          <select value={template} onChange={e => setTemplate(e.target.value)} style={{ ...inputStyle, flex: 1 }}>
            {TEMPLATES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={cityKey} onChange={e => setCityKey(e.target.value)} style={{ ...inputStyle, width: 160 }}>
            {(cities ?? []).map(c => <option key={c.key} value={c.key}>{c.name}</option>)}
          </select>
        </div>
      ) : (
        <input
          value={freeform}
          onChange={e => setFreeform(e.target.value)}
          placeholder='e.g. "ecommerce agencies near Bandra Kurla Complex"'
          onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submit() }}
          style={{ ...inputStyle, width: '100%', marginBottom: 14, fontFamily: 'inherit' }}
        />
      )}

      {/* Preview + warning */}
      <div style={{
        padding: '8px 12px', background: 'var(--bg)',
        borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)',
        fontSize: 12, color: 'var(--muted)', fontFamily: 'DM Mono, monospace',
        marginBottom: 14, minHeight: 38, display: 'flex', alignItems: 'center'
      }}>
        {builtQuery
          ? <><span style={{ color: 'var(--muted)' }}>→</span>&nbsp;<span style={{ color: 'var(--text)' }}>"{builtQuery}"</span></>
          : <span>Build a query to preview...</span>}
      </div>

      {warning && (
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 8,
          padding: '8px 12px', marginBottom: 14, fontSize: 12,
          background: warning.severity === 'high' ? 'var(--yellow-soft)' : 'var(--bg)',
          color: warning.severity === 'high' ? 'var(--yellow)' : 'var(--muted)',
          border: `1px solid ${warning.severity === 'high' ? 'var(--yellow)' : 'var(--border)'}`,
          borderRadius: 'var(--radius-sm)',
        }}>
          <AlertCircle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>{warning.message}. Run again?</span>
        </div>
      )}

      <button
        onClick={submit}
        disabled={!builtQuery || running}
        style={{
          padding: '8px 18px', fontSize: 13, fontWeight: 500,
          background: !builtQuery ? 'var(--border)' : 'var(--green)',
          color: !builtQuery ? 'var(--muted)' : 'white',
          border: 'none', borderRadius: 'var(--radius-sm)',
          cursor: !builtQuery || running ? 'not-allowed' : 'pointer',
          display: 'inline-flex', alignItems: 'center', gap: 6,
          opacity: running ? 0.7 : 1,
          transition: 'all 0.15s ease',
        }}
      >
        <Play size={13} />
        {running ? 'Queueing…' : 'Run search'}
      </button>
    </div>
  )
}

function ModeButton({ active, onClick, label }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '5px 12px', fontSize: 11, fontWeight: 500,
        borderRadius: 'var(--radius-sm)', border: '1px solid',
        cursor: 'pointer',
        background: active ? 'var(--bg)' : 'transparent',
        color: active ? 'var(--text)' : 'var(--muted)',
        borderColor: active ? 'var(--text)' : 'var(--border)',
        transition: 'all 0.15s ease',
      }}
    >
      {label}
    </button>
  )
}

function daysSince(iso) {
  if (!iso) return 0
  const d = new Date(iso.replace(' ', 'T') + (iso.includes('Z') ? '' : 'Z'))
  return Math.floor((Date.now() - d.getTime()) / 86400000)
}

const inputStyle = {
  padding: '8px 10px', fontSize: 13,
  border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
  background: 'var(--surface)', color: 'var(--text)', outline: 'none',
}