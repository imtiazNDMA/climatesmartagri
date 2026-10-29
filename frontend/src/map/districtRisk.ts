import type { DistrictRiskLevel } from '../api/types'

export const DEFAULT_RISK_COLOURS: Record<DistrictRiskLevel, string> = {
  low: '#facc15',
  medium: '#f97316',
  high: '#dc2626',
}

export function districtRiskColour(
  colours: Record<DistrictRiskLevel, string>,
  fallback: string,
): unknown[] {
  return [
    'match', ['feature-state', 'risk'],
    'low', colours.low,
    'medium', colours.medium,
    'high', colours.high,
    fallback,
  ]
}

export const districtRiskOpacity: unknown[] = [
  'case',
  ['boolean', ['feature-state', 'hover'], false],
  ['match', ['feature-state', 'risk'], 'low', 0.58, 'medium', 0.62, 'high', 0.66, 0.15],
  ['match', ['feature-state', 'risk'], 'low', 0.34, 'medium', 0.4, 'high', 0.46, 0],
]
