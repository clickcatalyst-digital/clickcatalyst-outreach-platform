// dashboard/app/phone/lib/api.js
import { apiFetch } from '../../lib/api'

export function fetchPhoneLeads({ tab, search, city, pixel, page, limit = 50 }) {
  const params = new URLSearchParams({
    tab,
    page: String(page),
    limit: String(limit),
    ...(search && { search }),
    ...(city && { city }),
    ...(pixel && { pixel }),
  })
  return apiFetch(`/places/with-interactions/list?${params}`)
}

export function fetchInteractions(cin) {
  return apiFetch(`/interactions/${cin}`)
}

export function postInteraction(cin, comment, interacted = true) {
  return apiFetch(`/interactions/${cin}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment, interacted }),
  })
}

export function deleteInteraction(interactionId) {
  return apiFetch(`/interactions/${interactionId}`, {
    method: 'DELETE',
  })
}