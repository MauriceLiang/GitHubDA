import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockService } from './mock'

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  mockService.resetMock?.()
})

describe('Mock provider', () => {
  it('rejects an invalid repository without changing the library', async () => {
    const before = await mockService.listRepositories()
    await expect(mockService.addAndAnalyze('not a repository')).rejects.toThrow('owner/repo')
    expect(await mockService.listRepositories()).toHaveLength(before.length)
  })

  it('adds once and reuses an existing repository without a duplicate task', async () => {
    vi.useFakeTimers()
    const finishDelay = async <T,>(promise: Promise<T>) => { await vi.advanceTimersByTimeAsync(120); return promise }
    const firstRequest = mockService.addAndAnalyze('https://github.com/example/one.git')
    const first = await finishDelay(firstRequest)
    expect(first.existing).toBe(false)
    expect(first.taskId).toBeTruthy()
    const countAfterFirst = (await finishDelay(mockService.listTasks())).length

    const duplicateRequest = mockService.addAndAnalyze('example/one')
    const duplicate = await finishDelay(duplicateRequest)
    expect(duplicate).toEqual({ repositoryId: first.repositoryId, taskId: null, existing: true })
    expect(await finishDelay(mockService.listTasks())).toHaveLength(countAfterFirst)
  })

  it('keeps empty research data empty and does not fabricate statistics', async () => {
    const result = await mockService.researchStatistics('oss-empty', 'language')
    expect(result.validSampleSize).toBe(0)
    expect(result.groups).toEqual([])
    expect(result.correlations).toEqual([])
  })

  it('does not expose a deep result after only basic collection has completed', async () => {
    vi.useFakeTimers()
    const addedPromise = mockService.addAndAnalyze('example/basic-only')
    await vi.advanceTimersByTimeAsync(120)
    const added = await addedPromise
    await vi.advanceTimersByTimeAsync(3700)
    const basicPromise = mockService.repositoryAnalysis(added.repositoryId, 'basic')
    await vi.advanceTimersByTimeAsync(120)
    expect(await basicPromise).toMatchObject({ status: 'completed', coverage: 'complete' })
    const deepPromise = mockService.repositoryAnalysis(added.repositoryId, 'deep')
    await vi.advanceTimersByTimeAsync(120)
    expect(await deepPromise).toMatchObject({ status: 'not_started', metrics: null, source: null })
  })

  it('allows comparing only repositories with collected snapshots', async () => {
    await expect(mockService.compare([101, 102], 'basic')).resolves.toMatchObject({ repositories: [{ repositoryId: 101 }, { repositoryId: 102 }] })
    await expect(mockService.compare([101, 104], 'basic')).rejects.toThrow('已采集过数据')
    await expect(mockService.compare([101], 'basic')).rejects.toThrow('2–5')
  })
})
