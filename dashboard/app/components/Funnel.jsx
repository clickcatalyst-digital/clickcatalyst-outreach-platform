'use client'
// Shared lead funnel band: Generated → Qualified → Ready → Sent → Opened → Clicked → Replied.
const STAGES = [
  ['generated', 'Generated'], ['qualified', 'Qualified'], ['ready', 'Ready'],
  ['sent', 'Sent'], ['opened', 'Opened'], ['clicked', 'Clicked'], ['replied', 'Replied'],
]

export default function Funnel({ f }) {
  if (!f) return null
  return (
    <div className="cc-funnel" style={{ display: 'flex', alignItems: 'center', gap: 0, overflowX: 'auto' }}>
      {STAGES.map(([k, label], i) => (
        <div key={k} style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
          <div style={{
            minWidth: 76, textAlign: 'center', padding: '10px 12px',
            border: '1px solid var(--border)', borderRadius: 10, background: 'var(--surface)',
          }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', lineHeight: 1.1 }}>{f[k] ?? '—'}</div>
            <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 3 }}>{label}</div>
          </div>
          {i < STAGES.length - 1 && (
            <span style={{ color: 'var(--muted)', padding: '0 6px', fontSize: 13 }}>→</span>
          )}
        </div>
      ))}
    </div>
  )
}
