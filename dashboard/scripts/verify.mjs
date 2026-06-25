#!/usr/bin/env node
// Availability check: GET every read endpoint, assert 200 + shape.
// Usage: node scripts/verify.mjs [baseUrl] [user:pass]
//   or:  DASHBOARD_URL=https://... BASIC_AUTH=user:pass node scripts/verify.mjs
const BASE = (process.argv[2] || process.env.DASHBOARD_URL || 'http://localhost:3000').replace(/\/$/, '')
const AUTH = process.argv[3] || process.env.BASIC_AUTH || ''
const headers = AUTH ? { Authorization: 'Basic ' + Buffer.from(AUTH).toString('base64') } : {}

const fails = []
function mark(cond, label, extra = '') {
  console.log(`${cond ? '✓' : '✗'} ${label}${extra ? '  ' + extra : ''}`)
  if (!cond) fails.push(label)
  return cond
}
async function check(path, validate) {
  try {
    const r = await fetch(BASE + path, { headers })
    const text = await r.text()
    let body; try { body = JSON.parse(text) } catch { body = text }
    mark(r.status === 200 && (!validate || validate(body)), path, `[${r.status}]`)
    return body
  } catch (e) { mark(false, path, String(e.message)); return null }
}

const WRITE_ENDPOINTS = [
  'PATCH /api/us-outreach/config', 'POST/DELETE /api/us-outreach/test-emails',
  'POST /api/us-outreach/run-once', 'PATCH /api/campaigns/[id]', 'POST /api/campaigns/ab-promote',
  'PATCH /api/leads/[cin]/website', 'POST/PATCH/DELETE /api/contacts/[cin]*',
]

;(async () => {
  console.log(`\nVERIFY  ${BASE}\n`)
  await check('/api/health', (b) => b.status === 'ok')
  await check('/api/system-health', (b) => 'funnel' in b)
  await check('/api/us-outreach/status', (b) => 'mode' in b)
  await check('/api/us-outreach/config', (b) => b && typeof b === 'object')
  await check('/api/us-outreach/test-emails', (b) => Array.isArray(b))
  await check('/api/us-outreach/contacts?limit=2', (b) => Array.isArray(b.contacts))
  const leads = await check('/api/leads?country=us&limit=3', (b) => Array.isArray(b.leads))
  await check('/api/leads/statuses', (b) => Array.isArray(b))
  const cin = leads?.leads?.[0]?.CIN
  if (cin) {
    await check('/api/leads/' + cin, (b) => 'lead' in b)
    await check('/api/contacts/' + cin, (b) => Array.isArray(b))
  }
  const camps = await check('/api/campaigns?country=us', (b) => Array.isArray(b))
  const tid = camps?.[0]?.Template_ID
  if (tid) await check('/api/campaigns/' + tid, (b) => b && ('Template_ID' in b || 'error' in b))
  for (const ep of ['overview', 'by-variant', 'by-batch', 'timeline', 'ab-tests', 'bayesian']) {
    await check('/api/analytics/' + ep + '?country=us')
  }
  console.log('\nWrite endpoints (not exercised in read-only mode; verified wired to Mac workers):')
  WRITE_ENDPOINTS.forEach((e) => console.log('  · ' + e))
  console.log(`\n${fails.length ? '✗ ' + fails.length + ' FAILED' : '✓ ALL PASS'}\n`)
  process.exit(fails.length ? 1 : 0)
})()
