import { describe, expect, it } from 'vitest'
import type { Comparison, Metrics } from '@/services/domain'
import { comparisonReadout, correlationReading, observationChange, pValueLabel, repositoryReadout } from './analysis'

const empty: Metrics = { stars: null, forks: null, ageDays: null, daysSincePush: null, commits90d: null, issuesClosed90d: null, prsMerged90d: null, releases365d: null }
const row = (id: number, stars: number | null): Comparison['repositories'][number] => ({ repositoryId: id, fullName: `sample/repo-${id}`, metrics: { ...empty, stars }, coverage: 'complete' })

describe('evidence-based analysis reading', () => {
  it('keeps zero activity distinct from missing data and identifies partial coverage', () => {
    const missing = repositoryReadout(null, 'not_collected', false)
    expect(missing[2]?.fact).toContain('还不能判断')
    const zero = repositoryReadout({ ...empty, stars: 0, daysSincePush: 0, commits90d: 0 }, 'partial', false)
    expect(zero[0]?.fact).toContain('0 个 Stars')
    expect(zero[1]?.fact).toContain('0 天')
    expect(zero[2]?.fact).toContain('提交 0 次')
    expect(zero[2]?.explanation).toContain('1 / 4')
    expect(zero[2]?.explanation).toContain('部分采集')
  })

  it('excludes missing values instead of treating them as a lower comparison value', () => {
    const reading = comparisonReadout([row(1, 10), row(2, null), row(3, 30)], 'stars')
    expect(reading.count).toBe(2)
    expect(reading.detail).toContain('相差 20')
    expect(reading.detail).toContain('1 个仓库缺失')
    expect(comparisonReadout([row(1, null), row(2, 0)], 'stars').count).toBe(1)
  })

  it('reports equal zero values without inventing a winner or a percentage', () => {
    const reading = comparisonReadout([row(1, 0), row(2, 0)], 'stars')
    expect(reading.headline).toContain('数值相同：0')
    expect(reading.headline).not.toContain('最高')
    expect(reading.detail).toContain('相差 0')
  })

  it('does not divide by a zero initial observation or extrapolate a single point', () => {
    expect(observationChange([{ date: '2026-10-01', value: 0 }])).toBeNull()
    expect(observationChange([{ date: '2026-10-01', value: 0 }, { date: '2026-10-07', value: 12 }])).toMatchObject({ change: 12, percent: null })
    expect(observationChange([{ date: '2026-10-01', value: 20 }, { date: '2026-10-07', value: 10 }])).toMatchObject({ change: -10, percent: -50 })
  })

  it('preserves reasons a correlation is undefined and explains negative association', () => {
    expect(correlationReading(null, 4, '有效配对样本少于 10')).toContain('少于 10')
    expect(correlationReading(-0.7, 20, null)).toContain('反向排序关联')
    expect(correlationReading(0, 20, null)).toContain('未呈现')
    expect(pValueLabel(0.00001)).toBe('< 0.001')
    expect(pValueLabel(null)).toBe('—')
  })
})
