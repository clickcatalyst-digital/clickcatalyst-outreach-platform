'use client'

import { useState, useEffect, useRef } from 'react'
import { Phone, Globe, MapPin, Star, MessageSquare, X, RotateCw } from 'lucide-react'
import { fetchInteractions, postInteraction, deleteInteraction } from '../lib/api'
import { API } from '../../lib/api'

export default function InteractionPanel({ lead, onClose, onInteractionChange }) {
  const [interactions, setInteractions] = useState([])
  const [comment, setComment] = useState('')
  const [interacted, setInteracted] = useState(true)
  const [posting, setPosting] = useState(false)
  const [rechecking, setRechecking] = useState(false)
  const [pixelOverride, setPixelOverride] = useState(null)  // optimistic pixel update
  const textareaRef = useRef(null)

  const currentPixel = pixelOverride !== null ? pixelOverride : lead?.Has_Google_Ads_Pixel

  async function recheckPixel() {
    if (!lead || rechecking) return
    setRechecking(true)
    try {
      const res = await fetch(`${API}/places/recheck-pixel/${lead.CIN}`, {
        method: 'POST',
      })
      const data = await res.json()
      setPixelOverride(data.has_pixel ?? null)
      onInteractionChange?.()  // refresh table to pick up the change
    } finally {
      setRechecking(false)
    }
  }

  useEffect(() => {
    if (!lead) return
    setComment('')
    setInteracted(true)
    loadInteractions()
  }, [lead?.CIN])

  async function loadInteractions() {
    const data = await fetchInteractions(lead.CIN)
    setInteractions(data?.interactions ?? [])
  }

  async function submit() {
    if (!comment.trim() || posting) return
    setPosting(true)

    // Optimistic update
    const optimistic = {
      Interaction_ID: `tmp-${Date.now()}`,
      CIN: lead.CIN,
      Comment: comment,
      Interacted: interacted ? 1 : 0,
      Created_At: new Date().toISOString(),
      Created_By: 'ui',
      _pending: true,
    }
    setInteractions(prev => [optimistic, ...prev])
    setComment('')

    const res = await postInteraction(lead.CIN, optimistic.Comment, interacted)
    setPosting(false)

    if (res?.ok) {
      await loadInteractions()
      onInteractionChange?.()  // tells parent to refresh tab counts
    } else {
      // Revert on failure
      setInteractions(prev => prev.filter(i => i.Interaction_ID !== optimistic.Interaction_ID))
      setComment(optimistic.Comment)
    }
  }

  async function remove(id) {
    if (!confirm('Delete this interaction?')) return
    setInteractions(prev => prev.filter(i => i.Interaction_ID !== id))
    await deleteInteraction(id)
    onInteractionChange?.()
  }

  function handleKey(e) {
    // Cmd/Ctrl + Enter to submit
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      submit()
    }
  }

  if (!lead) {
    return (
      <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 60, textAlign: 'center' }}>
        Select a lead to view details
      </div>
    )
  }

  return (
    <div style={{ fontSize: 13 }}>
      {/* Close button */}
      <button onClick={onClose} style={{
        position: 'absolute', top: 18, right: 18,
        padding: 4, background: 'none', border: 'none', cursor: 'pointer',
        color: 'var(--muted)', display: 'flex', alignItems: 'center'
      }}>
        <X size={16} />
      </button>

      {/* Title */}
      <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 4, paddingRight: 24, letterSpacing: '-0.01em' }}>
        {lead.Display_Name}
      </div>
      <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--muted)', marginBottom: 16 }}>
        {lead.CIN}
      </div>

      {/* Big phone number — primary action */}
      <a href={`tel:${lead.National_Phone || lead.Phone_Formatted}`} style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '12px 14px', marginBottom: 14,
        background: 'var(--blue-soft)', border: '1px solid var(--blue)',
        borderRadius: 'var(--radius)', textDecoration: 'none',
      }}>
        <Phone size={16} color="var(--blue)" />
        <span style={{
          fontFamily: 'DM Mono, monospace', fontSize: 16, fontWeight: 500,
          color: 'var(--blue)', flex: 1
        }}>
          {lead.Phone_Formatted}
        </span>
        <button
          onClick={e => {
            e.preventDefault()
            navigator.clipboard.writeText(lead.National_Phone || lead.Phone_Formatted)
          }}
          style={{
            fontSize: 10, padding: '3px 8px', borderRadius: 4,
            border: '1px solid var(--blue)', background: 'transparent',
            color: 'var(--blue)', cursor: 'pointer', fontWeight: 500
          }}
        >Copy</button>
      </a>

      {/* Quick info */}
      <div style={{ marginBottom: 16 }}>
        {lead.Rating && (
          <InfoRow icon={Star} label="Rating">
            <span style={{ fontFamily: 'DM Mono, monospace' }}>
              {lead.Rating} <span style={{ color: 'var(--muted)' }}>({lead.User_Rating_Count} reviews)</span>
            </span>
          </InfoRow>
        )}
        {lead.Formatted_Address && (
          <InfoRow icon={MapPin} label="Address">
            <span style={{ fontSize: 11 }}>{lead.Formatted_Address}</span>
          </InfoRow>
        )}
        {lead.Website_URI && (
          <InfoRow icon={Globe} label="Website">
            <a href={lead.Website_URI} target="_blank" rel="noreferrer"
              style={{ color: 'var(--blue)', textDecoration: 'none', fontSize: 11 }}>
              {lead.Website_URI.replace(/^https?:\/\//, '').replace(/\/$/, '').slice(0, 38)}
            </a>
          </InfoRow>
        )}
        <InfoRow icon={Globe} label="Google Ads">
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
            {currentPixel === 1 || currentPixel === true ? (
              <span style={{ color: 'var(--green)', fontWeight: 500 }}>✓ Pixel installed</span>
            ) : currentPixel === 0 || currentPixel === false ? (
              <span style={{ color: 'var(--accent)' }}>✕ No pixel detected</span>
            ) : (
              <span style={{ color: 'var(--muted)' }}>— Not checked</span>
            )}
            <button
              onClick={recheckPixel}
              disabled={rechecking}
              title="Re-check pixel"
              style={{
                padding: '2px 6px', fontSize: 10,
                border: '1px solid var(--border)', borderRadius: 3,
                background: 'transparent', color: 'var(--muted)',
                cursor: rechecking ? 'wait' : 'pointer',
                display: 'inline-flex', alignItems: 'center', gap: 3,
              }}
            >
              <RotateCw size={9} className={rechecking ? 'spin' : ''} />
              {rechecking ? 'checking…' : 'Recheck'}
            </button>
          </span>
        </InfoRow>
        {lead.Google_Maps_URI && (
          <a href={lead.Google_Maps_URI} target="_blank" rel="noreferrer" style={{
            display: 'inline-block', marginTop: 8, fontSize: 11,
            color: 'var(--muted)', textDecoration: 'underline'
          }}>
            Open in Google Maps →
          </a>
        )}
      </div>

      {/* Comment input */}
      <div style={{
        background: 'var(--bg)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 12, marginBottom: 18
      }}>
        <div style={sectionLabel}>
          <MessageSquare size={11} style={{ display: 'inline', marginRight: 4 }} />
          Log interaction
        </div>
        <textarea
          ref={textareaRef}
          value={comment}
          onChange={e => setComment(e.target.value)}
          onKeyDown={handleKey}
          placeholder="What happened on the call? (Cmd+Enter to save)"
          rows={3}
          style={{
            width: '100%', padding: '8px 10px', fontSize: 12,
            border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
            background: 'var(--surface)', color: 'var(--text)',
            outline: 'none', resize: 'vertical', fontFamily: 'inherit',
            marginBottom: 8,
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--muted)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={interacted}
              onChange={e => setInteracted(e.target.checked)}
              style={{ cursor: 'pointer' }}
            />
            Reached a human
          </label>
          <button
            onClick={submit}
            disabled={!comment.trim() || posting}
            style={{
              padding: '6px 14px', fontSize: 12, fontWeight: 500,
              background: comment.trim() ? 'var(--text)' : 'var(--border)',
              color: 'white', border: 'none',
              borderRadius: 'var(--radius-sm)',
              cursor: comment.trim() ? 'pointer' : 'not-allowed',
            }}
          >
            {posting ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {/* History */}
      <div>
        <div style={sectionLabel}>History ({interactions.length})</div>
        {interactions.length === 0 ? (
          <div style={{ color: 'var(--muted)', fontSize: 12, padding: '12px 0' }}>
            No interactions yet
          </div>
        ) : (
          interactions.map(i => (
            <div key={i.Interaction_ID} style={{
              padding: '10px 12px', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', marginBottom: 6,
              background: i._pending ? 'var(--bg)' : 'var(--surface)',
              opacity: i._pending ? 0.6 : 1,
            }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                marginBottom: 4, fontSize: 10, color: 'var(--muted)',
                fontFamily: 'DM Mono, monospace'
              }}>
                <span>{formatDate(i.Created_At)}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {i.Interacted ? (
                    <span style={{ color: 'var(--green)' }}>● reached</span>
                  ) : (
                    <span style={{ color: 'var(--muted)' }}>○ no answer</span>
                  )}
                  {!i._pending && (
                    <button
                      onClick={() => remove(i.Interaction_ID)}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        color: 'var(--muted)', fontSize: 10, padding: 0,
                      }}
                      title="Delete"
                    >×</button>
                  )}
                </div>
              </div>
              <div style={{ fontSize: 12, lineHeight: 1.5 }}>{i.Comment}</div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function InfoRow({ icon: Icon, label, children }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 8,
      padding: '6px 0', fontSize: 12,
    }}>
      <Icon size={12} color="var(--muted)" style={{ marginTop: 2, flexShrink: 0 }} />
      <div style={{ flex: 1, color: 'var(--text)' }}>{children}</div>
    </div>
  )
}

function formatDate(iso) {
  if (!iso) return ''
  // SQLite "YYYY-MM-DD HH:MM:SS" → Date
  const d = new Date(iso.replace(' ', 'T') + (iso.includes('Z') ? '' : 'Z'))
  if (isNaN(d.getTime())) return iso
  const now = new Date()
  const diffMs = now - d
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  if (diffDay < 7) return `${diffDay}d ago`
  return d.toLocaleDateString()
}

const sectionLabel = {
  fontSize: 11, color: 'var(--muted)', marginBottom: 8,
  fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em'
}