import { describe, expect, it } from 'vitest'
import { districtRiskColour, districtRiskOpacity } from './districtRisk'

describe('district risk map style', () => {
  it('maps all three risk classes to the configured colours', () => {
    expect(districtRiskColour({ low: '#1', medium: '#2', high: '#3' }, '#0')).toEqual([
      'match', ['feature-state', 'risk'],
      'low', '#1',
      'medium', '#2',
      'high', '#3',
      '#0',
    ])
  })

  it('keeps unclassified districts clear while preserving hover feedback', () => {
    const expression = JSON.stringify(districtRiskOpacity)
    expect(expression).toContain(',0]')
    expect(expression).toContain('0.15')
    expect(expression).toContain('0.66')
  })
})
