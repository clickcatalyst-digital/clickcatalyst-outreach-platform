// dashboard/app/lib/api.js
//
// Shared fetch wrapper for the ops dashboard.
// Shows connection status instead of crashing on failed fetches.

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

let _toastCallback = null

export function setToastCallback(fn) {
  _toastCallback = fn
}

function showError(msg) {
  if (_toastCallback) _toastCallback(msg)
}

export async function apiFetch(path, options = {}) {
  try {
    const r = await fetch(`${API}${path}`, options)
    if (!r.ok) {
      const text = await r.text().catch(() => '')
      showError(`API error ${r.status}: ${path}`)
      return null
    }
    return await r.json()
  } catch (e) {
    showError('Backend not reachable — start FastAPI server on port 8000')
    return null
  }
}

// Global country scope (India = MCA pipeline, US = Apollo pipeline).
export function getCountry() {
  if (typeof window === 'undefined') return 'us'
  return localStorage.getItem('cc_country') || 'us'
}

export function setCountry(c) {
  if (typeof window === 'undefined') return
  localStorage.setItem('cc_country', c)
  window.dispatchEvent(new Event('cc-country-change'))
}

export { API }