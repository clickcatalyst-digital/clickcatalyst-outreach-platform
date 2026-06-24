'use client'

import { useState, useEffect, useCallback } from 'react'
import QuotaCard from './components/QuotaCard'
import SearchForm from './components/SearchForm'
import SearchHistory from './components/SearchHistory'
import { fetchDiscoverSummary, enqueueSearch } from './lib/api'

export default function DiscoverPage() {
  const [summary, setSummary] = useState(null)

  const refresh = useCallback(async () => {
    const data = await fetchDiscoverSummary()
    if (data) setSummary(data)
  }, [])

  // Initial + polling while jobs are active
  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    const hasActive = (summary?.active_jobs ?? []).length > 0
    if (!hasActive) return
    const t = setInterval(refresh, 1500)  // poll every 1.5s while jobs running
    return () => clearInterval(t)
  }, [summary?.active_jobs?.length, refresh])

  async function handleEnqueued(jobId) {
    // Trigger immediate refresh so the active job appears
    setTimeout(refresh, 200)
  }

  async function handleRerun(query) {
    // Find city_hint if the query matches a template
    const cityKey = (summary?.cities ?? []).find(c => query.includes(c.name))?.key
    await enqueueSearch(query, cityKey || null)
    setTimeout(refresh, 200)
  }

  return (
    <div className="page-enter" style={{ padding: '32px 36px', maxWidth: 1400, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 4, letterSpacing: '-0.01em' }}>
          Discover
        </h1>
        <p style={{ color: 'var(--muted)', fontSize: 13 }}>
          Find new leads via Google Places. Searches run in the background.
        </p>
      </div>

      <QuotaCard quota={summary?.quota} />

      <SearchForm
        cities={summary?.cities ?? []}
        onJobEnqueued={handleEnqueued}
      />

      <SearchHistory
        history={summary?.history ?? []}
        activeJobs={summary?.active_jobs ?? []}
        recentJobs={summary?.recent_jobs ?? []}
        onRerun={handleRerun}
      />
    </div>
  )
}