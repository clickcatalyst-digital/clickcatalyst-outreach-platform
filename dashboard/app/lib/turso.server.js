// dashboard/app/lib/turso.server.js
// SERVER-ONLY Turso access for Next.js route handlers. The token comes from
// server env vars (TURSO_URL / TURSO_AUTH_TOKEN) and never reaches the browser.
// Do NOT import this from a 'use client' component.

import { createClient } from '@libsql/client'

let _client = null

export function turso() {
  if (!_client) {
    const url = process.env.TURSO_URL || process.env.TURSO_DATABASE_URL
    const authToken = process.env.TURSO_AUTH_TOKEN
    if (!url) throw new Error('TURSO_URL (or TURSO_DATABASE_URL) is not set')
    _client = createClient({ url, authToken })
  }
  return _client
}

// Run a query, return rows as plain objects.
export async function q(sql, args = []) {
  const rs = await turso().execute({ sql, args })
  return rs.rows.map((r) => ({ ...r }))
}

// First row or null.
export async function q1(sql, args = []) {
  const rows = await q(sql, args)
  return rows[0] || null
}

// Single scalar (first column of first row) or a default.
export async function scalar(sql, args = [], dflt = null) {
  const rs = await turso().execute({ sql, args })
  if (!rs.rows.length) return dflt
  const row = rs.rows[0]
  const v = row[rs.columns[0]]
  return v == null ? dflt : v
}

// Write helper.
export async function run(sql, args = []) {
  return turso().execute({ sql, args })
}

// JSON Response shorthand for route handlers.
export function json(data, init) {
  return Response.json(data, init)
}

// SQL fragment to scope outreach_analytics by country (mirrors api/database.country_filter).
// Returns fixed strings (no user input interpolated) so it is injection-safe.
export function countryFilter(country) {
  const c = (country || '').toLowerCase()
  if (c === 'us') return " AND CIN LIKE 'APOLLO_%' AND Batch_ID NOT LIKE 'ustest%'"
  if (c === 'india') return " AND CIN NOT LIKE 'APOLLO_%' AND Batch_ID NOT LIKE 'ustest%'"
  return ''
}
