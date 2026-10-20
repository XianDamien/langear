import { API_BASE_URL } from './coreApi'

export type LegacyRouteName = 'Study' | 'Summary'

interface LegacyRouteHit {
  route: LegacyRouteName
  date: string
  release_sha: string
}

/**
 * Count-only telemetry for retired SPA routes. It contains no user identifiers,
 * card content or query strings: just the route name, local date and release.
 */
export function reportLegacyRouteHit(route: LegacyRouteName) {
  const date = new Date().toLocaleDateString('en-CA')
  const send = (releaseSha: string) => {
    const payload: LegacyRouteHit = { route, date, release_sha: releaseSha }
    const body = new Blob([JSON.stringify(payload)], { type: 'application/json' })
    try {
      if (navigator.sendBeacon?.(`${API_BASE_URL}/telemetry/legacy-route-hits`, body)) return
    } catch {
      // Fall through to fetch for browsers without beacon support.
    }
    void fetch(`${API_BASE_URL}/telemetry/legacy-route-hits`, {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'application/json' },
      keepalive: true,
      credentials: 'same-origin',
    }).catch(() => undefined)
  }

  fetch('/release.json', { cache: 'no-store' })
    .then(response => (response.ok ? response.json() : null))
    .then(meta => send(typeof meta?.sha === 'string' ? meta.sha : 'unknown'))
    .catch(() => send('unknown'))
}
