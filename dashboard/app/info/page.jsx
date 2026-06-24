'use client'

import { useState, useEffect } from 'react'
import { getCountry } from '../lib/api'

export default function InfoPage() {
  const [country, setCountry] = useState('india')
  useEffect(() => {
    setCountry(getCountry())
    const on = () => setCountry(getCountry())
    window.addEventListener('cc-country-change', on)
    return () => window.removeEventListener('cc-country-change', on)
  }, [])

  const isUS = country === 'us'

  return (
    <div style={{ padding: '44px 44px', maxWidth: 760, margin: '0 auto' }}>
      <h1 style={{ fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em', margin: 0 }}>
        How this works
      </h1>
      <p style={{ color: 'var(--muted)', fontSize: 13.5, lineHeight: 1.7, margin: '8px 0 32px' }}>
        Showing <b style={{ color: 'var(--text)' }}>{isUS ? '🇺🇸 United States' : '🇮🇳 India'}</b>.
        Switch country in the sidebar — every tab, including this one, re-scopes to it.
      </p>

      <Block title="The country switch" accent>
        The <b>🇮🇳/🇺🇸 dropdown</b> at the top of the sidebar scopes the whole dashboard.
        India and US are separate pipelines that share tracking, analytics, and the learning engine —
        switching never mixes their data.
      </Block>

      {isUS ? (
        <>
          <Block title="US — runs itself">
            <Step n="1" t="Discover">Apollo finds US marketing-agency founders matching your ICP (free search).</Step>
            <Step n="2" t="Qualify">Title scored + only ad-running agencies kept — before any credit is spent.</Step>
            <Step n="3" t="Reveal">Verified email unlocked (1 Apollo credit), then a pixel check confirms Google Ads.</Step>
            <Step n="4" t="Send">A problem-first email (A/B tested, auto-personalized) goes out, warmup-paced.</Step>
            <Step n="5" t="Learn" last>Opens, clicks & replies feed the Bayesian engine — it picks the best email, the best send hours, and protects your domain.</Step>
            <Note>You mostly watch the <b>US Outreach</b> tab — it’s the control tower.</Note>
          </Block>

          <Block title="The US Outreach control tower">
            <Li><b>Test ↔ Production</b> — test sends only to your test inboxes, never touches real prospects or the warmup count; flip to prod and it resumes exactly where it left off.</Li>
            <Li><b>Schedule</b> — set send days, the CST window, and cadence. Past a threshold the system learns the best hours itself.</Li>
            <Li><b>Run cycle now</b> — fire one cycle immediately to test the flow.</Li>
            <Li><b>Pause all</b> — kill switch that stops even test sends.</Li>
            <Li><b>Heartbeat</b> — the dot top-right shows the engine is alive; red means the daemon stopped.</Li>
            <Li><b>Alerts</b> — red (bounce/reputation), yellow (corpus/credits), <b>green = a reply</b> (the one you want).</Li>
          </Block>

          <Block title="Going live (US)" accent>
            <Step n="1" t="Test">Add a test email, keep mode on Test, hit Run cycle — check your inbox.</Step>
            <Step n="2" t="Watch">Let it run a few real prod batches and read the first replies.</Step>
            <Step n="3" t="Trust" last>Once replies flow and reputation holds, leave it — just watch for green alerts.</Step>
          </Block>
        </>
      ) : (
        <>
          <Block title="India — staged pipeline">
            <Step n="1" t="Find domains">From <b>Pipeline</b>: Google Places + DuckDuckGo + Serper locate each company’s website.</Step>
            <Step n="2" t="Check pixels">Scan HTML + GTM for a Google Ads pixel to find active advertisers.</Step>
            <Step n="3" t="Intelligence">Generate competitor analysis + a personalized line for the email.</Step>
            <Step n="4" t="Add contacts">In <b>Contacts</b> — Queue mode auto-loads the next lead; or CSV import.</Step>
            <Step n="5" t="Send" last>Warmup-paced emails with the competitor scatter plot, A/B + Bayesian optimized.</Step>
            <Note>India is run manually stage-by-stage from the <b>Pipeline</b> tab (US, by contrast, runs itself).</Note>
          </Block>

          <Block title="Phone outreach (India)">
            <b>Discover</b> finds Google Places leads by city/keyword; call them and log notes in <b>Phone</b>
            (to-call / contacted tabs, comment thread per lead).
          </Block>
        </>
      )}

      <Block title="Every tab">
        <Tab name="Home">Snapshot + next action for the selected country.</Tab>
        <Tab name="Leads">Every lead, filterable. {isUS ? 'US leads come from Apollo.' : 'India leads come from MCA registry.'}</Tab>
        <Tab name="Contacts">{isUS ? 'US contacts arrive auto-filled from Apollo — use Search to view/edit.' : 'Manual entry (Queue / CSV).'}</Tab>
        <Tab name="Campaigns">Email templates / A/B arms. The Bayesian engine optimizes them.</Tab>
        <Tab name="Analytics">Sends, open/click/reply rates, A/B significance, domain reputation.</Tab>
        {isUS
          ? <Tab name="US Outreach" last>The autonomous control tower (US only).</Tab>
          : <Tab name="Pipeline / Phone" last>Run the 4 stages; call Places leads.</Tab>}
      </Block>
    </div>
  )
}

function Block({ title, children, accent }) {
  return (
    <div style={{
      border: '1px solid var(--border)', borderRadius: 14, padding: '20px 22px', marginBottom: 14,
      background: 'var(--surface)', borderLeft: accent ? '3px solid var(--accent)' : '1px solid var(--border)',
    }}>
      <div style={{ fontSize: 14.5, fontWeight: 600, marginBottom: 12 }}>{title}</div>
      <div style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.7 }}>{children}</div>
    </div>
  )
}
function Step({ n, t, children, last }) {
  return (
    <div style={{ display: 'flex', gap: 12, paddingBottom: last ? 0 : 12 }}>
      <span style={{
        flexShrink: 0, width: 22, height: 22, borderRadius: 999, background: 'var(--bg)',
        border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 11, fontFamily: 'DM Mono, monospace', color: 'var(--muted)',
      }}>{n}</span>
      <div><b>{t}.</b> <span style={{ color: 'var(--muted)' }}>{children}</span></div>
    </div>
  )
}
function Li({ children }) {
  return <div style={{ paddingLeft: 16, position: 'relative', marginBottom: 9 }}>
    <span style={{ position: 'absolute', left: 0, color: 'var(--muted)' }}>·</span>{children}
  </div>
}
function Tab({ name, children, last }) {
  return (
    <div style={{ display: 'flex', gap: 12, padding: '7px 0', borderBottom: last ? 'none' : '1px solid var(--border)' }}>
      <span style={{ width: 120, flexShrink: 0, fontWeight: 500 }}>{name}</span>
      <span style={{ color: 'var(--muted)' }}>{children}</span>
    </div>
  )
}
function Note({ children }) {
  return <div style={{ marginTop: 12, padding: '9px 13px', background: 'var(--bg)', borderRadius: 8, fontSize: 12.5, color: 'var(--muted)' }}>{children}</div>
}
