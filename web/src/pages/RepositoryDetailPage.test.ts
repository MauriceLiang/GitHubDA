import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { RepositoryAnalysis } from '@/services/domain'
import RepositoryDetailPage from './RepositoryDetailPage.vue'

const api = vi.hoisted(() => ({ repositoryDetail: vi.fn(), repositoryAnalysis: vi.fn(), repositorySeries: vi.fn(), listTasks: vi.fn() }))
vi.mock('@/services', () => ({ dataMode: 'http', services: api }))
const metrics = { stars: 100, forks: 5, ageDays: 365, daysSincePush: 2, commits90d: null, issuesClosed90d: null, prsMerged90d: null, releases365d: null }
const basic: RepositoryAnalysis = { status: 'completed', metrics, coverage: 'complete', limitations: [], source: { collectedAt: '2026-10-15T00:00:00Z', windowStart: null, windowEnd: null } }
let wrapper: VueWrapper | undefined
beforeEach(() => {
  api.repositoryDetail.mockResolvedValue({ repositoryId: 1, fullName: 'example/project', language: 'TypeScript', htmlUrl: 'https://github.com/example/project', dataStatus: 'fresh', topics: [] })
  api.repositorySeries.mockResolvedValue([])
  api.listTasks.mockResolvedValue([])
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.resetAllMocks() })
async function openDetail() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/repositories/:repositoryId', component: RepositoryDetailPage }] })
  await router.push('/repositories/1')
  await router.isReady()
  wrapper = mount(RepositoryDetailPage, { global: { plugins: [createPinia(), router], stubs: { TrendChart: true } } })
  await flushPromises()
  return wrapper
}

describe('reading saved analysis scopes', () => {
  it('opens saved deep results and lets the user switch to basic without mixing metrics', async () => {
    api.repositoryAnalysis.mockImplementation((_id, depth) => Promise.resolve(depth === 'basic' ? basic : { ...basic, status: 'partial', coverage: 'partial', metrics: { ...metrics, commits90d: 42 } }))
    const page = await openDetail()
    expect(page.text()).toContain('42')
    expect(page.text()).toContain('部分覆盖')
    await page.get('button[aria-pressed="false"]').trigger('click')
    expect(page.get('button[aria-pressed="true"]').text()).toBe('基础概况')
    expect(page.text()).not.toContain('42')
    expect(page.text()).toContain('完整覆盖')
  })

  it('shows an uncollected deep scope instead of reusing the available basic result', async () => {
    api.repositoryAnalysis.mockImplementation((_id, depth) => Promise.resolve(depth === 'basic' ? basic : { status: 'not_started', metrics: null, coverage: 'not_collected', limitations: [], source: null }))
    const page = await openDetail()
    await page.get('button[aria-pressed="false"]').trigger('click')
    expect(page.text()).toContain('这个范围还没有可用结果')
    expect(page.text()).toContain('未采集')
    expect(page.find('.metric-grid').exists()).toBe(false)
  })
})
