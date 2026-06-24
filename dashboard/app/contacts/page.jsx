// dashboard/app/contacts/page.jsx
'use client'

import { useState, useEffect, useCallback, useRef, Fragment } from 'react'
import { Search, ChevronLeft, ChevronRight, ExternalLink, SkipForward, Save, Plus, Keyboard, Eye, MousePointerClick, Reply, Sparkles } from 'lucide-react'
import { getCountry } from '../lib/api'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

const JOB_TITLES = [
  'Founder', 'Co-Founder', 'CEO', 'CMO', 'Head of Marketing',
  'VP Marketing', 'Growth Lead', 'Digital Marketing Manager', 'Director', 'Other'
]
const EMAIL_LABELS = ['Work', 'Personal', 'Founder', 'Marketing', 'Info / Generic', 'Other']

export default function ContactsPage() {
  const [tab, setTab] = useState('queue')
  const [country, setCountry] = useState('us')

  useEffect(() => {
    setCountry(getCountry())
    const on = () => setCountry(getCountry())
    window.addEventListener('cc-country-change', on)
    return () => window.removeEventListener('cc-country-change', on)
  }, [])

  // US has no manual queue — Apollo fills contacts. Force Search and hide Queue/CSV.
  useEffect(() => { if (country === 'us' && tab !== 'search') setTab('search') }, [country])

  const TABS = [
    ...(country !== 'us' ? [{ id: 'queue', label: 'Queue Mode', desc: 'auto-loads next lead' }] : []),
    { id: 'search', label: 'Search', desc: country === 'us' ? 'find a US contact' : 'find any company' },
    ...(country !== 'us' ? [{ id: 'import', label: 'CSV Import', desc: 'bulk upload contacts' }] : []),
  ]

  return (
    <div className="page-enter" style={{ padding: '36px 44px', maxWidth: 1100 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, letterSpacing: '-0.01em' }}>Contacts</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--muted)', fontFamily: 'DM Mono, monospace' }}>
          <Keyboard size={11} />
          <span>Alt+S save · Alt+N next · Alt+K skip</span>
        </div>
      </div>

      {country === 'us' ? (
        <USContactsView />
      ) : (
        <>
          {/* Tab bar */}
          <div style={{ display: 'flex', gap: 0, marginBottom: 28, borderBottom: '1px solid var(--border)' }}>
            {TABS.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                padding: '10px 20px', fontSize: 13, fontWeight: tab === t.id ? 500 : 400,
                color: tab === t.id ? 'var(--text)' : 'var(--muted)',
                background: 'none', border: 'none', cursor: 'pointer',
                borderBottom: tab === t.id ? '2px solid var(--text)' : '2px solid transparent',
                marginBottom: -1, transition: 'all 0.15s ease'
              }}>
                {t.label}
                <span style={{ fontSize: 10, color: 'var(--muted)', marginLeft: 6 }}>({t.desc})</span>
              </button>
            ))}
          </div>

          {tab === 'queue' ? <QueueMode /> : tab === 'search' ? <SearchMode /> : <CSVImport />}
        </>
      )}
    </div>
  )
}


// ═══════════════════════════════════════════════
// QUEUE MODE — auto-loads next lead without contacts
// ═══════════════════════════════════════════════

function QueueMode() {
  const [lead, setLead]             = useState(null)
  const [contacts, setContacts]     = useState([])
  const [offset, setOffset]         = useState(0)
  const [total, setTotal]           = useState(0)
  const [loading, setLoading]       = useState(true)
  const [success, setSuccess]       = useState('')

  const loadLead = useCallback(async (off = 0) => {
    setLoading(true)
    setSuccess('')
    try {
      const r = await fetch(`${API}/leads/queue/next?offset=${off}`)
      const d = await r.json()
      setLead(d.lead)
      setTotal(d.total)
      setOffset(off)
      if (d.lead) {
        const cr = await fetch(`${API}/contacts/${d.lead.CIN}`)
        setContacts(await cr.json())
      } else {
        setContacts([])
      }
    } catch {
      setLead(null)
      setSuccess('⚠ Cannot reach API — is the backend running on port 8000?')
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadLead(0) }, [loadLead])

  async function handleSkip() {
    if (!lead) return
    await fetch(`${API}/contacts/${lead.CIN}/skip`, { method: 'PATCH' })
    setSuccess(`Skipped ${lead.CompanyName}`)
    loadLead(0)
  }

  async function handleNext() {
    loadLead(0)
  }

  async function handlePrev() {
    if (offset > 0) loadLead(offset - 1)
  }

  async function handleSaveAndNext(formData) {
    const r = await fetch(`${API}/contacts/${lead.CIN}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData)
    })
    const d = await r.json()
    if (d.ok) {
      setSuccess(`Saved ${formData.full_name}`)
      loadLead(0)
    }
  }

  async function handleSaveAndStay(formData) {
    const r = await fetch(`${API}/contacts/${lead.CIN}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData)
    })
    const d = await r.json()
    if (d.ok) {
      setSuccess(`Saved ${formData.full_name} — add another`)
      const cr = await fetch(`${API}/contacts/${lead.CIN}`)
      setContacts(await cr.json())
    }
  }

  // Keyboard shortcuts
  useEffect(() => {
    function onKey(e) {
      if (e.altKey && e.key === 'n') { e.preventDefault(); handleNext() }
      if (e.altKey && e.key === 'k') { e.preventDefault(); handleSkip() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (loading) {
    return <div style={{ color: 'var(--muted)', fontSize: 13, padding: '40px 0' }}>Loading next lead...</div>
  }

  if (!lead) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 6 }}>Queue empty</div>
        <div style={{ color: 'var(--muted)', fontSize: 13 }}>
          All qualified leads have contacts assigned. Run the pipeline to enrich more.
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Queue status bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 20, padding: '10px 16px',
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', boxShadow: 'var(--shadow-sm)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={handlePrev} disabled={offset === 0} style={navBtn}>
            <ChevronLeft size={14} />
          </button>
          <span style={{ fontSize: 12, color: 'var(--muted)', fontFamily: 'DM Mono, monospace' }}>
            {total} remaining in queue
          </span>
          <button onClick={handleNext} style={navBtn}>
            <ChevronRight size={14} />
          </button>
        </div>
        <button onClick={handleSkip} style={{
          ...navBtn, color: 'var(--accent)', gap: 4, display: 'flex', alignItems: 'center', fontSize: 12
        }}>
          <SkipForward size={12} /> Skip (Alt+K)
        </button>
      </div>

      {success && (
        <div style={{
          padding: '8px 14px', marginBottom: 16, fontSize: 12,
          background: 'var(--green-soft)', color: 'var(--green)',
          borderRadius: 'var(--radius-sm)', fontWeight: 500
        }}>{success}</div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <CompanyPanel lead={lead} contacts={contacts}
          onContactsChange={async () => {
            const cr = await fetch(`${API}/contacts/${lead.CIN}`)
            setContacts(await cr.json())
          }}
          onWebsiteChange={() => loadLead(offset)}
        />
        <ContactForm
          lead={lead}
          contacts={contacts}
          onSaveAndNext={handleSaveAndNext}
          onSaveAndStay={handleSaveAndStay}
        />
      </div>
    </div>
  )
}


// ═══════════════════════════════════════════════
// US CONTACTS — enriched table (Apollo-sourced)
// ═══════════════════════════════════════════════

function USContactsView() {
  const [rows, setRows]       = useState([])
  const [total, setTotal]     = useState(0)
  const [q, setQ]             = useState('')
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)

  async function load(search = '') {
    setLoading(true)
    try {
      const r = await fetch(`${API}/us-outreach/contacts?search=${encodeURIComponent(search)}`)
      const d = await r.json()
      setRows(d.contacts || []); setTotal(d.total || 0)
    } catch {}
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 14, maxWidth: 440 }}>
        <div style={{ position: 'relative', flex: 1 }}>
          <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)' }} />
          <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && load(q)}
            placeholder="Search name, email, or company…"
            style={{ width: '100%', padding: '9px 10px 9px 32px', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 13, background: 'var(--surface)', color: 'var(--text)', outline: 'none' }} />
        </div>
        <button onClick={() => load(q)} style={{
          padding: '9px 16px', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
          background: 'var(--surface)', color: 'var(--text)', fontSize: 13, cursor: 'pointer'
        }}>Search</button>
      </div>

      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>
        {total} US contact{total === 1 ? '' : 's'} · auto-sourced from Apollo · click a row for details
      </div>

      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden', boxShadow: 'var(--shadow-sm)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Contact', 'Title', 'Company', 'Pixel', 'Engagement', 'Status'].map(h => (
                <th key={h} style={{ padding: '10px 14px', textAlign: 'left', color: 'var(--muted)', fontWeight: 500, fontSize: 11 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(c => (
              <Fragment key={c.Contact_ID}>
                <tr onClick={() => setExpanded(expanded === c.Contact_ID ? null : c.Contact_ID)}
                  style={{ borderBottom: '1px solid var(--border)', cursor: 'pointer',
                    background: expanded === c.Contact_ID ? 'var(--bg)' : 'transparent' }}>
                  <td style={{ padding: '10px 14px', fontWeight: 500 }}>
                    {c.Is_Primary_Contact ? '⭐ ' : ''}{c.Full_Name}
                    <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--muted)' }}>{c.Email_Address}</div>
                  </td>
                  <td style={{ padding: '10px 14px', color: 'var(--muted)' }}>{c.Job_Title || '—'}</td>
                  <td style={{ padding: '10px 14px' }}>{c.Company_Name}</td>
                  <td style={{ padding: '10px 14px' }}>{c.Has_Google_Ads_Pixel === 1 ? '✅' : c.Has_Google_Ads_Pixel === 0 ? '❌' : <span style={{ color: 'var(--muted)' }}>—</span>}</td>
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ display: 'flex', gap: 10, color: 'var(--muted)', fontSize: 11, alignItems: 'center' }}>
                      <span title="opens" style={{ display: 'flex', gap: 3, alignItems: 'center', color: c.Opens > 0 ? 'var(--green)' : 'var(--muted)' }}><Eye size={12} />{c.Opens}</span>
                      <span title="clicks" style={{ display: 'flex', gap: 3, alignItems: 'center', color: c.Clicks > 0 ? 'var(--blue)' : 'var(--muted)' }}><MousePointerClick size={12} />{c.Clicks}</span>
                      <span title="replies" style={{ display: 'flex', gap: 3, alignItems: 'center', color: c.Replies > 0 ? 'var(--green)' : 'var(--muted)', fontWeight: c.Replies > 0 ? 600 : 400 }}><Reply size={12} />{c.Replies}</span>
                    </div>
                  </td>
                  <td style={{ padding: '10px 14px' }}>
                    <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 500,
                      background: c.Email_Sent_Date ? 'var(--green-soft)' : 'var(--blue-soft)',
                      color: c.Email_Sent_Date ? 'var(--green)' : 'var(--blue)' }}>
                      {c.Email_Sent_Date ? 'Sent' : (c.Pipeline_Status || '—')}
                    </span>
                  </td>
                </tr>
                {expanded === c.Contact_ID && (
                  <tr>
                    <td colSpan={6} style={{ padding: '16px 20px', background: 'var(--bg)', borderBottom: '1px solid var(--border)' }}>
                      <ContactDetail contact={c} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={6} style={{ padding: 28, color: 'var(--muted)', textAlign: 'center' }}>
                No US contacts yet — run discovery + export from the US Outreach tab.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ContactDetail({ contact }) {
  const [notes, setNotes]   = useState(contact.Notes || '')
  const [summary, setSummary] = useState(contact.Conversation_Summary || '')
  const [savedFlag, setSavedFlag] = useState(false)
  const [summarizing, setSummarizing] = useState(false)
  const [sumMsg, setSumMsg] = useState('')

  async function saveNotes() {
    await fetch(`${API}/us-outreach/contacts/${contact.Contact_ID}/notes`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes }),
    })
    setSavedFlag(true); setTimeout(() => setSavedFlag(false), 1500)
  }
  async function summarize() {
    setSummarizing(true); setSumMsg('')
    try {
      const r = await fetch(`${API}/us-outreach/contacts/${contact.CIN}/summarize`, { method: 'POST' })
      const d = await r.json()
      if (d.summary) setSummary(d.summary)
      else setSumMsg('No thread found, or Gmail/OpenRouter not configured yet.')
    } catch { setSumMsg('Request failed.') }
    setSummarizing(false)
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
      {/* Conversation summary (Gemma) */}
      <div>
        <div style={detailLabel}>Conversation summary</div>
        {summary
          ? <div style={{ fontSize: 12.5, lineHeight: 1.6, color: 'var(--text)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>{summary}</div>
          : <div style={{ fontSize: 12, color: 'var(--muted)' }}>No summary yet — generated automatically once they reply, or on demand.</div>}
        <button onClick={summarize} disabled={summarizing} style={{
          marginTop: 10, display: 'flex', alignItems: 'center', gap: 6,
          padding: '7px 12px', borderRadius: 8, border: '1px solid var(--border)',
          background: 'var(--surface)', color: 'var(--text)', fontSize: 12, cursor: 'pointer'
        }}>
          <Sparkles size={13} /> {summarizing ? 'Summarizing…' : 'Summarize thread'}
        </button>
        {sumMsg && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 6 }}>{sumMsg}</div>}
        <div style={{ display: 'flex', gap: 14, marginTop: 14, fontSize: 12, color: 'var(--muted)' }}>
          {contact.LinkedIn_URL && <a href={contact.LinkedIn_URL} target="_blank" rel="noreferrer" style={{ color: 'var(--blue)', textDecoration: 'none' }}>LinkedIn ↗</a>}
          {contact.Website_URL && <a href={contact.Website_URL} target="_blank" rel="noreferrer" style={{ color: 'var(--blue)', textDecoration: 'none' }}>Website ↗</a>}
          {contact.Phone && <span>{contact.Phone}</span>}
        </div>
      </div>

      {/* Manual notes */}
      <div>
        <div style={detailLabel}>Notes (your research / conversation)</div>
        <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={5}
          placeholder="Anything you want to remember about this contact…"
          style={{ width: '100%', padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', fontSize: 12.5, outline: 'none', resize: 'vertical', fontFamily: 'inherit' }} />
        <button onClick={saveNotes} style={{
          marginTop: 8, padding: '7px 14px', borderRadius: 8, border: '1px solid var(--border)',
          background: 'var(--surface)', color: 'var(--text)', fontSize: 12, cursor: 'pointer'
        }}>{savedFlag ? '✓ Saved' : 'Save notes'}</button>
      </div>
    </div>
  )
}

const detailLabel = {
  fontSize: 11, fontWeight: 600, color: 'var(--muted)',
  textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8,
}


// ═══════════════════════════════════════════════
// SEARCH MODE — find any company
// ═══════════════════════════════════════════════

function SearchMode() {
  const [query, setQuery]       = useState('')
  const [results, setResults]   = useState([])
  const [selected, setSelected] = useState(null)
  const [contacts, setContacts] = useState([])
  const [success, setSuccess]   = useState('')

  async function search() {
    if (!query.trim()) return
    const r = await fetch(`${API}/leads?search=${encodeURIComponent(query)}&limit=20&country=${getCountry()}`)
    const d = await r.json()
    setResults(d.leads)
    setSelected(null)
  }

  async function selectCompany(lead) {
    setSelected(lead)
    setSuccess('')
    const cr = await fetch(`${API}/contacts/${lead.CIN}`)
    setContacts(await cr.json())
  }

  async function handleSaveAndNext(formData) {
    const r = await fetch(`${API}/contacts/${selected.CIN}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData)
    })
    const d = await r.json()
    if (d.ok) {
      setSuccess(`Saved ${formData.full_name}`)
      setSelected(null)
      setResults([])
    }
  }

  async function handleSaveAndStay(formData) {
    const r = await fetch(`${API}/contacts/${selected.CIN}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData)
    })
    const d = await r.json()
    if (d.ok) {
      setSuccess(`Saved ${formData.full_name} — add another`)
      const cr = await fetch(`${API}/contacts/${selected.CIN}`)
      setContacts(await cr.json())
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 22 }}>
        <div style={{ position: 'relative', flex: 1, maxWidth: 480 }}>
          <Search size={13} style={{
            position: 'absolute', left: 10, top: '50%',
            transform: 'translateY(-50%)', color: 'var(--muted)'
          }} />
          <input
            placeholder="Search CIN or company name..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
            style={{
              width: '100%', padding: '9px 10px 9px 32px',
              border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              fontSize: 13, background: 'var(--surface)', outline: 'none', color: 'var(--text)'
            }}
          />
        </div>
        <button onClick={search} style={btnPrimary}>Search</button>
      </div>

      {success && (
        <div style={{
          padding: '8px 14px', marginBottom: 16, fontSize: 12,
          background: 'var(--green-soft)', color: 'var(--green)',
          borderRadius: 'var(--radius-sm)', fontWeight: 500
        }}>{success}</div>
      )}

      {/* Results list */}
      {results.length > 0 && !selected && (
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', overflow: 'hidden', marginBottom: 24,
          boxShadow: 'var(--shadow-sm)'
        }}>
          {results.map(r => (
            <div key={r.CIN} onClick={() => selectCompany(r)} style={{
              padding: '12px 18px', borderBottom: '1px solid var(--border)',
              cursor: 'pointer', display: 'flex', justifyContent: 'space-between',
              alignItems: 'center', fontSize: 13, transition: 'background 0.1s'
            }}>
              <div>
                <span style={{ fontWeight: 500 }}>{r.CompanyName}</span>
                <span style={{
                  color: 'var(--muted)', fontFamily: 'DM Mono, monospace',
                  fontSize: 11, marginLeft: 10
                }}>{r.CIN}</span>
              </div>
              <div style={{ display: 'flex', gap: 10, fontSize: 11, color: 'var(--muted)' }}>
                <span>{r.Contact_Count} contact(s)</span>
                <span>{r.Pipeline_Status || '—'}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Selected company */}
      {selected && (
        <div>
          <button onClick={() => { setSelected(null); setResults([]) }}
            style={{ ...btnGhost, marginBottom: 16, fontSize: 12 }}>
            ← Back to results
          </button>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
            <CompanyPanel lead={selected} contacts={contacts}
              onContactsChange={async () => {
                const cr = await fetch(`${API}/contacts/${selected.CIN}`)
                setContacts(await cr.json())
              }}
              onWebsiteChange={async () => {
                const r = await fetch(`${API}/leads/${selected.CIN}`)
                const d = await r.json()
                setSelected(d.lead)
              }}
            />
            <ContactForm
              lead={selected}
              contacts={contacts}
              onSaveAndNext={handleSaveAndNext}
              onSaveAndStay={handleSaveAndStay}
            />
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════
// CSV IMPORT MODE — bulk upload contacts
// ═══════════════════════════════════════════════

function CSVImport() {
  const [rows, setRows]         = useState([])
  const [headers, setHeaders]   = useState([])
  const [mapping, setMapping]   = useState({})
  const [result, setResult]     = useState(null)
  const [importing, setImporting] = useState(false)
  const [fileName, setFileName] = useState('')

  const REQUIRED_FIELDS = [
    { key: 'cin', label: 'CIN' },
    { key: 'full_name', label: 'Full Name' },
    { key: 'email_address', label: 'Email Address' },
  ]
  const OPTIONAL_FIELDS = [
    { key: 'job_title', label: 'Job Title' },
    { key: 'email_label', label: 'Email Type' },
    { key: 'linkedin_url', label: 'LinkedIn URL' },
    { key: 'is_primary', label: 'Is Primary' },
  ]
  const ALL_FIELDS = [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS]

  function parseCSV(text) {
    const lines = text.trim().split('\n')
    if (lines.length < 2) return { headers: [], rows: [] }
    const hdrs = lines[0].split(',').map(h => h.trim().replace(/^["']|["']$/g, ''))
    const data = lines.slice(1).map(line => {
      const vals = line.split(',').map(v => v.trim().replace(/^["']|["']$/g, ''))
      const obj = {}
      hdrs.forEach((h, i) => { obj[h] = vals[i] || '' })
      return obj
    }).filter(row => Object.values(row).some(v => v))
    return { headers: hdrs, rows: data }
  }

  function autoMap(hdrs) {
    const m = {}
    const aliases = {
      cin: ['cin', 'company_cin', 'cin_number'],
      full_name: ['full_name', 'name', 'contact_name', 'full name', 'contact'],
      email_address: ['email_address', 'email', 'email address', 'mail'],
      job_title: ['job_title', 'title', 'role', 'job title', 'designation'],
      email_label: ['email_label', 'email_type', 'type', 'email type', 'label'],
      linkedin_url: ['linkedin_url', 'linkedin', 'linkedin url', 'profile'],
      is_primary: ['is_primary', 'primary', 'is primary'],
    }
    for (const [field, alts] of Object.entries(aliases)) {
      const match = hdrs.find(h => alts.includes(h.toLowerCase()))
      if (match) m[field] = match
    }
    return m
  }

  function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setFileName(file.name)
    setResult(null)
    const reader = new FileReader()
    reader.onload = (evt) => {
      const { headers: hdrs, rows: data } = parseCSV(evt.target.result)
      setHeaders(hdrs)
      setRows(data)
      setMapping(autoMap(hdrs))
    }
    reader.readAsText(file)
  }

  async function doImport() {
    if (!mapping.cin || !mapping.full_name || !mapping.email_address) return
    setImporting(true)
    setResult(null)

    const contacts = rows.map(row => {
      const c = {}
      for (const [field, csvCol] of Object.entries(mapping)) {
        c[field] = row[csvCol] || ''
      }
      if (c.is_primary) {
        c.is_primary = ['1', 'true', 'yes'].includes(c.is_primary.toLowerCase())
      }
      return c
    })

    const r = await fetch(`${API}/contacts/bulk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contacts })
    })
    const d = await r.json()
    setResult(d)
    setImporting(false)
  }

  const allRequiredMapped = REQUIRED_FIELDS.every(f => mapping[f.key])

  return (
    <div style={{ maxWidth: 700 }}>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 20 }}>
        Upload a CSV with contact data. Map columns to fields, preview, then import.
      </p>

      {/* File picker */}
      <div style={{
        border: '2px dashed var(--border)', borderRadius: 'var(--radius)',
        padding: '28px 20px', textAlign: 'center', marginBottom: 20,
        background: 'var(--surface)', cursor: 'pointer', position: 'relative'
      }}>
        <input type="file" accept=".csv" onChange={handleFile}
          style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer' }} />
        <div style={{ fontSize: 13, color: 'var(--muted)' }}>
          {fileName ? `Selected: ${fileName} (${rows.length} rows)` : 'Drop a CSV here or click to browse'}
        </div>
      </div>

      {/* Expected format hint */}
      <div style={{
        fontSize: 11, color: 'var(--muted)', marginBottom: 20,
        padding: '10px 14px', background: 'var(--bg)', borderRadius: 'var(--radius-sm)',
        border: '1px solid var(--border)', fontFamily: 'DM Mono, monospace'
      }}>
        Expected: cin, full_name, email_address, job_title, email_label, linkedin_url, is_primary
      </div>

      {/* Column mapping */}
      {headers.length > 0 && (
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: 22, marginBottom: 20,
          boxShadow: 'var(--shadow-sm)'
        }}>
          <div style={sectionLabel}>Map your CSV columns</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {ALL_FIELDS.map(f => (
              <label key={f.key} style={{ fontSize: 11, color: 'var(--muted)' }}>
                {f.label} {REQUIRED_FIELDS.some(r => r.key === f.key) ? '*' : ''}
                <select value={mapping[f.key] || ''}
                  onChange={e => setMapping(m => ({ ...m, [f.key]: e.target.value || undefined }))}
                  style={{
                    display: 'block', width: '100%', marginTop: 4,
                    padding: '7px 9px', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)', fontSize: 12,
                    background: 'var(--bg)', color: 'var(--text)', outline: 'none'
                  }}>
                  <option value="">— skip —</option>
                  {headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Preview */}
      {rows.length > 0 && allRequiredMapped && (
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', overflow: 'hidden', marginBottom: 20,
          boxShadow: 'var(--shadow-sm)'
        }}>
          <div style={{
            padding: '12px 16px', borderBottom: '1px solid var(--border)',
            fontSize: 11, fontWeight: 600, color: 'var(--muted)',
            textTransform: 'uppercase', letterSpacing: '0.08em'
          }}>Preview (first 5 rows)</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {ALL_FIELDS.filter(f => mapping[f.key]).map(f => (
                    <th key={f.key} style={{
                      padding: '8px 12px', textAlign: 'left',
                      color: 'var(--muted)', fontWeight: 500
                    }}>{f.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 5).map((row, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    {ALL_FIELDS.filter(f => mapping[f.key]).map(f => (
                      <td key={f.key} style={{
                        padding: '8px 12px', fontFamily: 'DM Mono, monospace', fontSize: 11
                      }}>{row[mapping[f.key]] || '—'}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Import button */}
      {rows.length > 0 && allRequiredMapped && (
        <button onClick={doImport} disabled={importing} style={{
          ...btnPrimary, opacity: importing ? 0.6 : 1, marginBottom: 16
        }}>
          {importing ? 'Importing...' : `Import ${rows.length} contacts`}
        </button>
      )}

      {/* Result */}
      {result && (
        <div style={{
          padding: '14px 18px', borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--border)',
          background: result.imported > 0 ? 'var(--green-soft)' : 'var(--accent-soft)',
          fontSize: 12, marginBottom: 16
        }}>
          <div style={{ fontWeight: 500, marginBottom: 4, color: result.imported > 0 ? 'var(--green)' : 'var(--accent)' }}>
            Imported {result.imported} · Skipped {result.skipped}
          </div>
          {result.errors?.length > 0 && (
            <div style={{ color: 'var(--muted)', fontSize: 11, marginTop: 6, lineHeight: 1.6 }}>
              {result.errors.map((e, i) => <div key={i}>{e}</div>)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}


// ═══════════════════════════════════════════════
// SHARED: Company Panel (left side)
// ═══════════════════════════════════════════════

function CompanyPanel({ lead, contacts, onContactsChange, onWebsiteChange }) {
  const [editUrl, setEditUrl] = useState(lead.Website_URL || '')
  const [saving, setSaving]   = useState(false)

  // Sync editUrl when lead changes
  useEffect(() => { setEditUrl(lead.Website_URL || '') }, [lead.CIN])

  async function saveUrl() {
    if (!editUrl.trim()) return
    setSaving(true)
    await fetch(`${API}/leads/${lead.CIN}/website`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ website_url: editUrl.trim() })
    })
    setSaving(false)
    onWebsiteChange?.()
  }

  async function setPrimary(contactId) {
    await fetch(`${API}/contacts/${lead.CIN}/primary/${contactId}`, { method: 'PATCH' })
    onContactsChange?.()
  }

  async function deleteContact(contactId) {
    await fetch(`${API}/contacts/${lead.CIN}/${contactId}`, { method: 'DELETE' })
    onContactsChange?.()
  }

  const companyQuery = encodeURIComponent(lead.CompanyName)

  return (
    <div>
      {/* Company card */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 22, marginBottom: 14,
        boxShadow: 'var(--shadow-sm)'
      }}>
        <div style={{ fontWeight: 600, fontSize: 16, letterSpacing: '-0.01em', marginBottom: 2 }}>
          {lead.CompanyName}
        </div>
        <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--muted)', marginBottom: 12 }}>
          {lead.CIN}
        </div>

        {/* Quick info row */}
        <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--muted)', marginBottom: 14 }}>
          <span>{lead.State}</span>
          {lead.Pipeline_Status && <span style={{
            padding: '1px 7px', borderRadius: 3, fontSize: 10, fontWeight: 500,
            background: 'var(--blue-soft)', color: 'var(--blue)'
          }}>{lead.Pipeline_Status}</span>}
          {lead.Competitor_Count > 0 && <span>{lead.Competitor_Count} competitors</span>}
        </div>

        {/* Website edit — always visible, no expander */}
        <div style={{ marginBottom: 14 }}>
          <div style={sectionLabel}>Website</div>
          <div style={{ display: 'flex', gap: 6 }}>
            <input value={editUrl} onChange={e => setEditUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && saveUrl()}
              placeholder="https://company.com"
              style={{
                flex: 1, padding: '7px 9px', fontSize: 12,
                border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                fontFamily: 'DM Mono, monospace', background: 'var(--bg)',
                color: 'var(--text)', outline: 'none'
              }} />
            <button onClick={saveUrl} disabled={saving} style={{
              padding: '7px 12px', borderRadius: 'var(--radius-sm)', border: 'none',
              background: 'var(--text)', color: 'white', fontSize: 11, cursor: 'pointer', fontWeight: 500
            }}>Save</button>
            {lead.Website_URL && (
              <a href={lead.Website_URL} target="_blank" rel="noreferrer" style={{
                padding: '7px 9px', borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border)', display: 'flex', alignItems: 'center', color: 'var(--muted)'
              }}><ExternalLink size={12} /></a>
            )}
          </div>
        </div>

        {/* Personalized sentence */}
        {lead.Personalized_Sentence && (
          <div style={{ marginBottom: 14 }}>
            <div style={sectionLabel}>Email Copy</div>
            <div style={{
              fontSize: 12, color: 'var(--muted)', lineHeight: 1.7,
              background: 'var(--bg)', padding: 10, borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)'
            }}>{lead.Personalized_Sentence}</div>
          </div>
        )}

        {/* Research links — prominent */}
        <div style={{ display: 'flex', gap: 10, fontSize: 11 }}>
          <a href={`https://www.linkedin.com/search/results/people/?keywords=${companyQuery}`}
            target="_blank" rel="noreferrer" style={linkBtn}>LinkedIn ↗</a>
          <a href={`https://www.google.com/search?q=${companyQuery}+founder+email`}
            target="_blank" rel="noreferrer" style={linkBtn}>Google ↗</a>
          <a href={`https://www.zaubacorp.com/company/${lead.CIN}`}
            target="_blank" rel="noreferrer" style={linkBtn}>Zaubacorp ↗</a>
          {lead.Website_URL && (
            <a href={`${lead.Website_URL}/about`}
              target="_blank" rel="noreferrer" style={linkBtn}>About Page ↗</a>
          )}
        </div>
      </div>

      {/* Existing contacts */}
      <div style={sectionLabel}>Saved Contacts ({contacts.length})</div>
      {contacts.length === 0
        ? <div style={{ color: 'var(--muted)', fontSize: 12, marginBottom: 8 }}>No contacts yet</div>
        : contacts.map(c => (
          <div key={c.Contact_ID} style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)', padding: '10px 14px', marginBottom: 6, fontSize: 12
          }}>
            <div style={{ fontWeight: 500 }}>
              {c.Is_Primary_Contact ? '⭐ ' : ''}{c.Full_Name}
            </div>
            <div style={{ color: 'var(--muted)', marginTop: 2 }}>{c.Job_Title} · {c.Email_Label}</div>
            <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, marginTop: 2 }}>{c.Email_Address}</div>
            <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
              {!c.Is_Primary_Contact && (
                <button onClick={() => setPrimary(c.Contact_ID)} style={btnSmall}>⭐ Primary</button>
              )}
              <button onClick={() => deleteContact(c.Contact_ID)}
                style={{ ...btnSmall, color: 'var(--accent)' }}>Delete</button>
            </div>
          </div>
        ))
      }
    </div>
  )
}


// ═══════════════════════════════════════════════
// SHARED: Contact Form (right side)
// ═══════════════════════════════════════════════

function ContactForm({ lead, contacts, onSaveAndNext, onSaveAndStay }) {
  const [form, setForm]   = useState(defaultForm(contacts))
  const [error, setError] = useState('')
  const firstRef = useRef(null)

  function defaultForm(existingContacts) {
    return {
      first_name: '', last_name: '', job_title: 'Founder',
      email_address: '', email_label: 'Work',
      linkedin_url: '', is_primary: !existingContacts || existingContacts.length === 0
    }
  }

  // Reset form when lead changes
  useEffect(() => {
    setForm(defaultForm(contacts))
    setError('')
    // Auto-focus first name field
    setTimeout(() => firstRef.current?.focus(), 100)
  }, [lead.CIN])

  function validate() {
    if (!form.first_name.trim()) return 'First name required'
    if (!form.last_name.trim())  return 'Last name required'
    if (!form.email_address.trim() || !form.email_address.includes('@')) return 'Valid email required'
    return null
  }

  function buildPayload() {
    return {
      full_name:     `${form.first_name.trim()} ${form.last_name.trim()}`,
      job_title:     form.job_title,
      email_address: form.email_address.trim(),
      email_label:   form.email_label,
      linkedin_url:  form.linkedin_url.trim() || null,
      is_primary:    form.is_primary,
    }
  }

  async function saveAndNext() {
    const err = validate()
    if (err) return setError(err)
    setError('')
    onSaveAndNext(buildPayload())
  }

  async function saveAndStay() {
    const err = validate()
    if (err) return setError(err)
    setError('')
    onSaveAndStay(buildPayload())
    setForm(prev => ({ ...defaultForm(contacts), is_primary: false }))
    setTimeout(() => firstRef.current?.focus(), 100)
  }

  // Keyboard shortcuts
  useEffect(() => {
    function onKey(e) {
      if (e.altKey && e.key === 's') { e.preventDefault(); saveAndNext() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: 22, boxShadow: 'var(--shadow-sm)',
      alignSelf: 'start'
    }}>
      <div style={{ ...sectionLabel, marginBottom: 18 }}>Add Contact</div>

      {error && <div style={{ color: 'var(--accent)', fontSize: 12, marginBottom: 12 }}>{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
        <label style={formLabel}>
          First Name *
          <input ref={firstRef} value={form.first_name}
            onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))}
            style={inputStyle} placeholder="Rahul" />
        </label>
        <label style={formLabel}>
          Last Name *
          <input value={form.last_name}
            onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))}
            style={inputStyle} placeholder="Sharma" />
        </label>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
        <label style={formLabel}>
          Job Title
          <select value={form.job_title}
            onChange={e => setForm(f => ({ ...f, job_title: e.target.value }))}
            style={inputStyle}>
            {JOB_TITLES.map(t => <option key={t}>{t}</option>)}
          </select>
        </label>
        <label style={formLabel}>
          Email Type
          <select value={form.email_label}
            onChange={e => setForm(f => ({ ...f, email_label: e.target.value }))}
            style={inputStyle}>
            {EMAIL_LABELS.map(t => <option key={t}>{t}</option>)}
          </select>
        </label>
      </div>

      <label style={{ ...formLabel, marginBottom: 10 }}>
        Email Address *
        <input value={form.email_address}
          onChange={e => setForm(f => ({ ...f, email_address: e.target.value }))}
          style={inputStyle} placeholder="rahul@company.com" />
      </label>

      <label style={{ ...formLabel, marginBottom: 16 }}>
        LinkedIn URL (optional)
        <input value={form.linkedin_url}
          onChange={e => setForm(f => ({ ...f, linkedin_url: e.target.value }))}
          style={inputStyle} placeholder="https://linkedin.com/in/..." />
      </label>

      <label style={{
        display: 'flex', alignItems: 'center', gap: 8,
        fontSize: 13, marginBottom: 20, cursor: 'pointer', color: 'var(--text)'
      }}>
        <input type="checkbox" checked={form.is_primary}
          onChange={e => setForm(f => ({ ...f, is_primary: e.target.checked }))} />
        ⭐ Primary Contact (receives the email)
      </label>

      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={saveAndNext} style={{
          ...btnPrimary, display: 'flex', alignItems: 'center', gap: 6
        }}>
          <Save size={12} /> Save & Next
          <span style={{ fontSize: 10, opacity: 0.7, marginLeft: 4 }}>Alt+S</span>
        </button>
        <button onClick={saveAndStay} style={{
          ...btnGhost, display: 'flex', alignItems: 'center', gap: 6
        }}>
          <Plus size={12} /> Add Another
        </button>
      </div>
    </div>
  )
}


/* ── Shared styles ── */
const sectionLabel = {
  fontSize: 11, fontWeight: 600, color: 'var(--muted)',
  textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10
}

const formLabel = {
  display: 'block', fontSize: 11, color: 'var(--muted)', marginBottom: 10
}

const inputStyle = {
  display: 'block', width: '100%', marginTop: 5,
  padding: '8px 10px', border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)', fontSize: 13,
  background: 'var(--bg)', color: 'var(--text)', outline: 'none'
}

const linkBtn = {
  padding: '5px 10px', borderRadius: 'var(--radius-sm)',
  border: '1px solid var(--border)', color: 'var(--blue)',
  textDecoration: 'none', background: 'var(--surface)',
  fontWeight: 500, transition: 'all 0.1s'
}

const navBtn = {
  padding: '6px 10px', border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)', background: 'var(--surface)',
  cursor: 'pointer', fontSize: 12, color: 'var(--text)',
  display: 'flex', alignItems: 'center'
}

const btnPrimary = {
  padding: '9px 18px', background: 'var(--text)', color: 'white',
  border: 'none', borderRadius: 'var(--radius-sm)', fontSize: 13,
  cursor: 'pointer', fontWeight: 500
}

const btnGhost = {
  padding: '9px 18px', background: 'transparent', color: 'var(--muted)',
  border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
  fontSize: 13, cursor: 'pointer'
}

const btnSmall = {
  padding: '4px 9px', background: 'var(--bg)',
  border: '1px solid var(--border)', borderRadius: 4,
  fontSize: 11, cursor: 'pointer', color: 'var(--text)'
}