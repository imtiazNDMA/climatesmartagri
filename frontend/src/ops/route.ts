/** The dashboard's views, kept in the URL hash so each one can be linked to and survives a reload. */
export type OpsRoute =
  | { view: 'overview' }
  | { view: 'runs' }
  | { view: 'run'; id: string }
  | { view: 'compare'; a: string; b: string }
  | { view: 'traces' }
  | { view: 'trace'; id: string }
  | { view: 'labels' }

export function parseRoute(hash: string): OpsRoute {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?')
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent)
  const params = new URLSearchParams(query)
  switch (parts[0]) {
    case 'runs':
      return parts[1] ? { view: 'run', id: parts[1] } : { view: 'runs' }
    case 'compare': {
      const a = params.get('a')
      const b = params.get('b')
      return a && b ? { view: 'compare', a, b } : { view: 'runs' }
    }
    case 'traces':
      return parts[1] ? { view: 'trace', id: parts[1] } : { view: 'traces' }
    case 'labels':
      return { view: 'labels' }
    default:
      return { view: 'overview' }
  }
}

export function routeHash(route: OpsRoute): string {
  switch (route.view) {
    case 'run':
      return `#/runs/${encodeURIComponent(route.id)}`
    case 'compare':
      return `#/compare?${new URLSearchParams({ a: route.a, b: route.b })}`
    case 'trace':
      return `#/traces/${encodeURIComponent(route.id)}`
    default:
      return `#/${route.view}`
  }
}
