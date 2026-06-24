'use client'

import { useState, useEffect, useCallback } from 'react'
import PhoneLeadTable from './components/PhoneLeadTable'
import InteractionPanel from './components/InteractionPanel'
import { fetchPhoneLeads } from './lib/api'

export default function PhonePage() {
  const [tab, setTab]         = useState('to_call')
  const [search, setSearch]   = useState('')
  const [city, setCity]       = useState('')
  const [pixel, setPixel]     = useState('')
  const [page, setPage]       = useState(1)

  const [leads, setLeads]     = useState([])
  const [total, setTotal]     = useState(0)
  const [counts, setCounts]   = useState({ to_call: 0, contacted: 0 })
  const [cities, setCities]   = useState([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    const data = await fetchPhoneLeads({ tab, search, city, pixel, page })
    if (data) {
      setLeads(data.leads ?? [])
      setTotal(data.total ?? 0)
      setCounts(data.counts ?? { to_call: 0, contacted: 0 })
      setCities(data.cities ?? [])
    }
    setLoading(false)
  }, [tab, search, city, pixel, page])

  // Debounce search
  useEffect(() => {
    const t = setTimeout(refresh, search ? 250 : 0)
    return () => clearTimeout(t)
  }, [refresh])

  return (
    <div className="page-enter" style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>

      <PhoneLeadTable
        leads={leads}
        total={total}
        counts={counts}
        cities={cities}
        tab={tab} setTab={setTab}
        search={search} setSearch={setSearch}
        city={city} setCity={setCity}
        pixel={pixel} setPixel={setPixel}
        page={page} setPage={setPage}
        selectedCin={selected?.CIN}
        onSelectLead={setSelected}
        loading={loading}
      />

      {/* Side panel */}
      <div style={{
        width: 420, flexShrink: 0,
        overflow: 'auto', padding: 28,
        background: 'var(--surface)',
        position: 'relative',
      }}>
        <InteractionPanel
          lead={selected}
          onClose={() => setSelected(null)}
          onInteractionChange={refresh}
        />
      </div>
    </div>
  )
}