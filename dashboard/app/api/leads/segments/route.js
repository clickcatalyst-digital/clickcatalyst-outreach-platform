import { json } from '../../../lib/turso.server'

// Segments come from vw_qualified_leads (India MCA, not in Turso). US has no
// segment taxonomy, so the hosted dashboard returns an empty list (filter hidden).
export async function GET() {
  return json([])
}
