// dashboard/app/discover/lib/api.js
import { apiFetch } from '../../lib/api'

export function fetchDiscoverSummary() {
  return apiFetch('/discover/summary')
}

export function checkKeyword(query) {
  return apiFetch(`/discover/check-keyword?query=${encodeURIComponent(query)}`)
}

export function enqueueSearch(query, cityHint) {
  return apiFetch('/discover/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, city_hint: cityHint || null }),
  })
}

export function fetchJob(jobId) {
  return apiFetch(`/discover/jobs/${jobId}`)
}