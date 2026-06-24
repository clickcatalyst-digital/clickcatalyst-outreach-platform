'use client'

import { ExternalLink } from 'lucide-react'

export default function QuotaCard({ quota }) {
  if (!quota) return null

  const pct = quota.percent_used
  const color =
    pct < 50 ? 'var(--green)' :
    pct < 80 ? 'var(--yellow)' :
               'var(--accent)'

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '16px 18px', marginBottom: 20,
      boxShadow: 'var(--shadow-sm)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          API Quota · This Month (estimate)
        </div>
        <a
          href="https://console.cloud.google.com/apis/api/places-backend.googleapis.com/metrics"
          target="_blank" rel="noreferrer"
          style={{
            fontSize: 11, color: 'var(--blue)', textDecoration: 'none',
            display: 'inline-flex', alignItems: 'center', gap: 4
          }}
        >
          GCP Console <ExternalLink size={11} />
        </a>
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 22, fontWeight: 500, color }}>
          {quota.used_this_month.toLocaleString()}
        </span>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          of {quota.free_tier_limit.toLocaleString()} free searches used
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--muted)' }}>
          {quota.remaining.toLocaleString()} remaining
        </span>
      </div>

      <div style={{ height: 6, background: 'var(--bg)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${Math.min(100, pct)}%`,
          background: color, transition: 'width 0.3s ease'
        }} />
      </div>

      <div style={{ marginTop: 8, fontSize: 11, color: 'var(--muted)' }}>
        {pct < 1
          ? "Plenty of headroom. Free tier resets on the 1st."
          : `${pct}% used · resets on the 1st of next month`}
      </div>
    </div>
  )
}