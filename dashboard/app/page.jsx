// dashboard/app/page.jsx
'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { getCountry } from './lib/api'
import {
  Zap, Search, Users, Mail, BarChart2,
  ArrowRight, CheckCircle, TrendingUp, Target,
  Brain, Phone, Radar
} from 'lucide-react'

const API = process.env.NEXT_PUBLIC_API_URL
  || (typeof window !== 'undefined' && window.location.hostname === 'localhost'
        ? 'http://localhost:8000/api' : '/api')

export default function HomePage() {
  const [status, setStatus]       = useState(null)
  const [overview, setOverview]   = useState(null)
  const [sched, setSched]         = useState(null)
  const [country, setCountry]     = useState('us')

  useEffect(() => {
    setCountry(getCountry())
    const on = () => setCountry(getCountry())
    window.addEventListener('cc-country-change', on)
    return () => window.removeEventListener('cc-country-change', on)
  }, [])

  useEffect(() => {
    const c = `?country=${country}`
    fetch(`${API}/pipeline/status${c}`).then(r => r.json()).then(setStatus).catch(() => {})
    fetch(`${API}/analytics/overview${c}`).then(r => r.json()).then(setOverview).catch(() => {})
    if (country === 'india') {
      fetch(`${API}/pipeline/scheduler/status`).then(r => r.json()).then(setSched).catch(() => {})
    } else {
      setSched(null)
    }
  }, [country])

  const isUS = country === 'us'

  const phase = !status ? null
    : status.enriched === 0 ? 'enrich'
    : status.pixel_confirmed === 0 ? 'pixel'
    : status.intelligence_ready === 0 && status.contacts_added === 0 ? 'intel'
    : status.contacts_added === 0 ? 'contacts'
    : status.outreach_sent === 0 ? 'send'
    : 'running'

  const phaseMessages = {
    enrich: 'Run Stage 1 to find websites for your leads',
    pixel: 'Run Stage 2 to check for Google Ads pixels',
    intel: 'Run Stage 3 to generate competitor intelligence',
    contacts: 'Add contacts via the Queue to unlock email dispatch',
    send: 'Your first batch is ready to schedule',
    running: 'Pipeline is active — monitor performance in Analytics',
  }

  return (
    <div className="page-enter" style={{ padding: '40px 44px', maxWidth: 1060 }}>

      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>
          clickcatalyst.digital/ops
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 6 }}>
          Outreach Command Center
        </h1>
        <p style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1.6 }}>
          Find companies running Google Ads, verify pixels, generate intelligence, and send personalized emails — all from one dashboard.
        </p>
      </div>

      {/* Phase indicator (India pipeline) */}
      {!isUS && phase && (
        <div style={{
          padding: '12px 18px', marginBottom: 24,
          background: phase === 'running' ? 'var(--green-soft)' : 'var(--blue-soft)',
          border: `1px solid ${phase === 'running' ? 'var(--green)' : 'var(--blue)'}`,
          borderRadius: 'var(--radius)',
          display: 'flex', alignItems: 'center', gap: 10,
          fontSize: 13, fontWeight: 500,
          color: phase === 'running' ? 'var(--green)' : 'var(--blue)'
        }}>
          {phase === 'running' ? <CheckCircle size={15} /> : <ArrowRight size={15} />}
          {phaseMessages[phase]}
        </div>
      )}

      {/* Quick stats */}
      {status && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 28 }}>
          {[
            { label: 'Leads', value: status.total_qualified, color: 'var(--muted)', icon: Target },
            { label: 'Pixel confirmed', value: status.pixel_confirmed, color: '#16a34a', icon: CheckCircle },
            { label: 'Ready to send', value: status.intelligence_ready, color: '#ca8a04', icon: Mail },
            { label: 'Emails sent', value: status.outreach_sent, color: '#e63946', icon: TrendingUp },
          ].map(s => (
            <div key={s.label} style={{
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius)', padding: '14px 16px',
              boxShadow: 'var(--shadow-sm)', display: 'flex', alignItems: 'center', gap: 12
            }}>
              <s.icon size={16} color={s.color} strokeWidth={1.5} />
              <div>
                <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 18, fontWeight: 500, color: s.color }}>{(s.value ?? 0).toLocaleString()}</div>
                <div style={{ fontSize: 10, color: 'var(--muted)' }}>{s.label}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pipeline workflow (India only) */}
      {!isUS && (
      <div style={{ marginBottom: 32 }}>
        <div style={{
          fontSize: 11, fontWeight: 600, color: 'var(--muted)',
          textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 14
        }}>
          Pipeline workflow
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'stretch' }}>
          {[
            { step: 1, label: 'Find domains', desc: 'Google Places + DuckDuckGo + Serper', stat: status ? `${status.enriched} found` : '—', color: '#2563eb', href: '/pipeline', done: status?.enriched > 0 },
            { step: 2, label: 'Check pixels', desc: 'HTML + GTM container scan', stat: status ? `${status.pixel_confirmed} confirmed` : '—', color: '#16a34a', href: '/pipeline', done: status?.pixel_confirmed > 0 },
            { step: 3, label: 'Intelligence', desc: 'Competitors + email personalization', stat: status ? `${status.intelligence_ready} ready` : '—', color: '#ca8a04', href: '/pipeline', done: status?.intelligence_ready > 0 },
            { step: 'M', label: 'Add contacts', desc: 'Queue mode + CSV import', stat: status ? `${status.contacts_added} added` : '—', color: '#7c3aed', href: '/contacts', done: status?.contacts_added > 0 },
            { step: 4, label: 'Send emails', desc: 'Auto-queue + Thompson Sampling', stat: status ? `${status.outreach_sent} sent` : '—', color: '#e63946', href: '/pipeline', done: status?.outreach_sent > 0 },
          ].map(s => (
            <Link key={s.step} href={s.href} style={{
              flex: 1, textDecoration: 'none',
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderTop: `3px solid ${s.done ? s.color : 'var(--border)'}`,
              borderRadius: 'var(--radius)', padding: '12px 12px 10px',
              boxShadow: 'var(--shadow-sm)', opacity: s.done ? 1 : 0.7,
              display: 'flex', flexDirection: 'column'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 4 }}>
                <span style={{
                  fontFamily: 'DM Mono, monospace', fontSize: 9,
                  width: 18, height: 18, borderRadius: '50%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: s.done ? s.color : 'var(--bg)',
                  color: s.done ? 'white' : 'var(--muted)', fontWeight: 600
                }}>{s.done ? '✓' : s.step}</span>
                <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text)' }}>{s.label}</span>
              </div>
              <div style={{ fontSize: 9, color: 'var(--muted)', lineHeight: 1.4, flex: 1 }}>{s.desc}</div>
              <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: s.color, marginTop: 6, fontWeight: 500 }}>{s.stat}</div>
            </Link>
          ))}
        </div>
      </div>
      )}

      {/* US: the orchestrator runs the flow */}
      {isUS && (
        <Link href="/us-outreach" style={{ textDecoration: 'none', display: 'block', marginBottom: 32 }}>
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '18px 20px', boxShadow: 'var(--shadow-sm)',
            display: 'flex', alignItems: 'center', gap: 12
          }}>
            <Radar size={20} color="#e63946" />
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>US Outreach runs itself</div>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>
                Apollo discovery → qualify → personalized A/B send, on a schedule. Open the control tower to monitor & toggle test/prod.
              </div>
            </div>
            <ArrowRight size={16} color="var(--muted)" style={{ marginLeft: 'auto' }} />
          </div>
        </Link>
      )}

      {/* Tools grid */}
      <div style={{
        fontSize: 11, fontWeight: 600, color: 'var(--muted)',
        textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 14
      }}>Your tools</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 28 }}>
        {[
          { href: '/pipeline', icon: Zap, label: 'Pipeline', desc: 'Run stages, queue emails, preview', features: ['4-stage automation', 'Queue controls', 'Email preview'], color: '#e63946' },
          { href: '/leads', icon: Search, label: 'Leads', desc: 'Browse and inspect your database', features: ['Filter & search', 'Detail panel', 'Website edit'], color: '#2563eb' },
          { href: '/contacts', icon: Users, label: 'Contacts', desc: 'Fast contact entry with Queue mode', features: ['Keyboard shortcuts', 'Research links', 'CSV import'], color: '#16a34a' },
          { href: '/campaigns', icon: Mail, label: 'Campaigns', desc: 'Edit templates and preview', features: ['16 templates', 'A/B variants', 'Variable preview'], color: '#ca8a04' },
          { href: '/analytics', icon: BarChart2, label: 'Analytics', desc: 'Performance and A/B testing', features: ['z-test stats', 'Thompson posteriors', 'Reputation score'], color: '#7c3aed' },
          { href: '/phone', icon: Phone, label: 'Phone', desc: 'Call leads and log interactions', features: ['Places leads', 'Comment thread', 'Tab filters'], color: '#0891b2' },
          { href: null, icon: Brain, label: 'Intelligence', desc: 'Self-learning optimization layer', features: ['Bayesian deliverability', 'Auto variant selection', 'Reply tracking'], color: '#6b6b65', badge: 'Built in' },
        ].map(card => {
          const Wrapper = card.href ? Link : 'div'
          const wrapperProps = card.href ? { href: card.href, style: { textDecoration: 'none' } } : {}
          return (
            <Wrapper key={card.label} {...wrapperProps}>
              <div style={{
                background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius)', padding: '16px 14px',
                boxShadow: 'var(--shadow-sm)', height: '100%',
                display: 'flex', flexDirection: 'column',
                cursor: card.href ? 'pointer' : 'default'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: 6,
                    background: `${card.color}12`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                  }}>
                    <card.icon size={14} color={card.color} />
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{card.label}</span>
                  {card.badge && (
                    <span style={{ fontSize: 8, padding: '1px 5px', borderRadius: 3, background: 'var(--bg)', color: 'var(--muted)', fontWeight: 500, marginLeft: 'auto' }}>
                      {card.badge}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: 'var(--muted)', lineHeight: 1.5, marginBottom: 8 }}>{card.desc}</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 'auto' }}>
                  {card.features.map(f => (
                    <span key={f} style={{
                      fontSize: 9, padding: '1px 6px', borderRadius: 3,
                      background: 'var(--bg)', color: 'var(--muted)', border: '1px solid var(--border)'
                    }}>{f}</span>
                  ))}
                </div>
              </div>
            </Wrapper>
          )
        })}
      </div>

      {/* Scheduler glance */}
      {sched && (
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', padding: '14px 18px', marginBottom: 20,
          boxShadow: 'var(--shadow-sm)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          fontSize: 12
        }}>
          <div style={{ display: 'flex', gap: 16, color: 'var(--muted)' }}>
            <span>Warmup day <strong style={{ color: 'var(--text)' }}>{sched.warmup_day}</strong></span>
            <span>Limit <strong style={{ color: 'var(--text)' }}>{sched.daily_limit}/day</strong></span>
            <span>Sent today <strong style={{ color: 'var(--text)' }}>{sched.sent_today}</strong></span>
            <span>Queue <strong style={{ color: 'var(--text)' }}>{sched.queue_size}</strong></span>
          </div>
          <Link href="/pipeline" style={{ color: 'var(--blue)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
            Pipeline <ArrowRight size={12} />
          </Link>
        </div>
      )}

      {/* Performance footer */}
      {overview && overview.total_sent > 0 && (
        <div style={{
          display: 'flex', gap: 16, fontSize: 12, color: 'var(--muted)',
          justifyContent: 'center', marginBottom: 16
        }}>
          <span>{overview.total_sent} sent</span>
          <span>·</span>
          <span>{overview.open_rate}% open</span>
          <span>·</span>
          <span>{overview.click_rate}% click</span>
        </div>
      )}

      <div style={{
        textAlign: 'center', fontSize: 10, color: 'var(--muted)',
        fontFamily: 'DM Mono, monospace', paddingBottom: 16
      }}>
        ClickCatalyst Ops
      </div>
    </div>
  )
}