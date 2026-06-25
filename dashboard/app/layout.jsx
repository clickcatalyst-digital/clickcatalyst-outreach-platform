// dashboard/app/layout.jsx
'use client'

import './globals.css'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { getCountry, setCountry, API } from './lib/api'
import {
  Zap, Search, Users, Mail, BarChart2, Activity, Phone, Compass, Radar, BookOpen
} from 'lucide-react'

// Hosted build is US-only (India/Places/Pipeline are local-only); local dev keeps both.
const COUNTRIES = process.env.NEXT_PUBLIC_HOSTED === 'true'
  ? [{ key: 'us', label: '🇺🇸 US (Apollo)' }]
  : [
      { key: 'india', label: '🇮🇳 India (MCA)' },
      { key: 'us',    label: '🇺🇸 US (Apollo)' },
    ]

const NAV = [
  { href: '/',            label: 'Home',         icon: Activity },
  { href: '/pipeline',    label: 'Pipeline',   icon: Zap,       only: 'india' },
  { href: '/discover',    label: 'Discover',   icon: Compass,   only: 'india' },
  { href: '/leads',       label: 'Leads',      icon: Search },
  { href: '/contacts',    label: 'Contacts',   icon: Users },
  { href: '/phone',       label: 'Phone',      icon: Phone,     only: 'india' },
  { href: '/campaigns',   label: 'Campaigns',  icon: Mail },
  { href: '/analytics',   label: 'Analytics',  icon: BarChart2 },
  { href: '/us-outreach', label: 'US Outreach', icon: Radar,    only: 'us' },
  { href: '/info',        label: 'Info',       icon: BookOpen },
]

export default function RootLayout({ children }) {
  const path = usePathname()
  const [dark, setDark] = useState(false)
  const [country, setC] = useState('us')

  useEffect(() => { setC(getCountry()) }, [])

  function changeCountry(c) {
    setC(c)
    setCountry(c)  // persists + dispatches cc-country-change for pages to refetch
  }

  useEffect(() => {
    const saved = localStorage.getItem('cc_ops_theme')
    if (saved === 'dark') {
      setDark(true)
      document.documentElement.setAttribute('data-theme', 'dark')
    }
  }, [])

  function toggleTheme() {
    const next = !dark
    setDark(next)
    document.documentElement.setAttribute('data-theme', next ? 'dark' : '')
    localStorage.setItem('cc_ops_theme', next ? 'dark' : 'light')
  }

  const [apiDown, setApiDown] = useState(false)

  useEffect(() => {
    fetch(`${API}/health`)
      .then(r => { if (!r.ok) throw new Error(); setApiDown(false) })
      .catch(() => setApiDown(true))
  }, [path])

  return (
    <html lang="en">
      <body style={{ display: 'flex', minHeight: '100vh' }}>

        {/* ── SIDEBAR ── */}
        <aside style={{
          width: 220, flexShrink: 0,
          background: 'var(--surface)',
          borderRight: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column',
          padding: '28px 0',
          position: 'sticky', top: 0, height: '100vh'
        }}>
          {/* Logo */}
          <div style={{ padding: '0 20px 32px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div>
                <div style={{
                  fontFamily: 'DM Mono, monospace',
                  fontSize: 16, fontWeight: 700,
                  color: 'var(--text)', lineHeight: 1.1
                }}>Catalyst Mail</div>
                <div style={{
                  fontSize: 10, color: 'var(--muted)',
                  fontFamily: 'DM Mono, monospace'
                }}>Ops Dashboard</div>
              </div>
            </div>
          </div>

          {/* Country scope */}
          <div style={{ padding: '0 16px 18px' }}>
            <select value={country} onChange={e => changeCountry(e.target.value)} style={{
              width: '100%', padding: '8px 10px', borderRadius: 6,
              border: '1px solid var(--border)', background: 'var(--bg)',
              color: 'var(--text)', fontSize: 12, cursor: 'pointer', outline: 'none'
            }}>
              {COUNTRIES.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
          </div>

          {/* Nav */}
          <nav style={{ flex: 1, padding: '0 12px' }}>
            {NAV.filter(n => !n.only || n.only === country).map(({ href, label, icon: Icon }) => {
              const active = href === '/' ? path === '/' : path.startsWith(href)
              return (
                <Link key={href} href={href} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 12px', borderRadius: 8,
                  marginBottom: 2, textDecoration: 'none',
                  fontSize: 13, fontWeight: active ? 500 : 400,
                  color: active ? 'var(--text)' : 'var(--muted)',
                  background: active ? 'var(--bg)' : 'transparent',
                  transition: 'all 0.15s ease'
                }}>
                  <Icon size={15} strokeWidth={active ? 2 : 1.5} />
                  {label}
                </Link>
              )
            })}
          </nav>

          {/* Footer */}
          <div style={{
            padding: '16px 20px 0',
            borderTop: '1px solid var(--border)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between'
          }}>
            <button onClick={toggleTheme} style={{
              background: 'none', border: '1px solid var(--border)',
              borderRadius: 4, padding: '3px 8px', cursor: 'pointer',
              fontSize: 10, color: 'var(--muted)', fontFamily: 'DM Mono, monospace'
            }}>
              {dark ? '☀' : '●'}
            </button>
          </div>
        </aside>

        {/* ── MAIN ── */}
        <main style={{ flex: 1, overflow: 'auto', minHeight: '100vh' }}>
          {apiDown && (
            <div style={{
              padding: '10px 20px', fontSize: 12, fontWeight: 500,
              background: 'var(--accent-soft)', color: 'var(--accent)',
              borderBottom: '1px solid var(--accent)',
              display: 'flex', alignItems: 'center', gap: 8
            }}>
              ⚠ Database not reachable — check the Turso connection (TURSO_URL / TURSO_AUTH_TOKEN)
            </div>
          )}
          {children}
        </main>

      </body>
    </html>
  )
}