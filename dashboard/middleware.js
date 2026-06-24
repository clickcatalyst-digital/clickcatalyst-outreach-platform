// Basic Auth gate for the hosted dashboard. Active only when BASIC_AUTH_USER and
// BASIC_AUTH_PASS are set (so local dev stays open). Covers pages and /api routes.
import { NextResponse } from 'next/server'

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}

export function middleware(req) {
  const user = process.env.BASIC_AUTH_USER
  const pass = process.env.BASIC_AUTH_PASS
  if (!user || !pass) return NextResponse.next() // auth disabled when unset

  const auth = req.headers.get('authorization') || ''
  const [scheme, encoded] = auth.split(' ')
  if (scheme === 'Basic' && encoded) {
    const decoded = atob(encoded)
    const i = decoded.indexOf(':')
    if (decoded.slice(0, i) === user && decoded.slice(i + 1) === pass) {
      return NextResponse.next()
    }
  }
  return new NextResponse('Authentication required', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="ClickCatalyst"' },
  })
}
