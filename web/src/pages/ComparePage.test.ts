import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Comparison, Metrics } from '@/services/domain'
import { useAppStore } from '@/stores/app'
import ComparePage from './ComparePage.vue'

const api = vi.hoisted(() => ({ listRepositories: vi.fn(), compare: vi.fn() }))
vi.mock('@/services', () => ({ services: api }))
let wrapper: VueWrapper | undefined
afterEach(() => { wrapper?.unmount(); vi.resetAllMocks() })

it('does not show the previous scope while another comparison is loading', async () => {
  const metrics: Metrics = { stars: 20, forks: 3, ageDays: 100, daysSincePush: 2, commits90d: null, issuesClosed90d: null, prsMerged90d: null, releases365d: null }
  const basic: Comparison = { repositories: [1, 2].map((id) => ({ repositoryId: id, fullName: `sample/${id}`, metrics, coverage: 'complete' })), basis: { depth: 'basic', metricWindow: 'latest', sameProjectType: false, warnings: [] } }
  let finishDeep!: (value: Comparison) => void
  api.listRepositories.mockResolvedValue([1, 2].map((id) => ({ repositoryId: id, fullName: `sample/${id}`, dataStatus: 'fresh' })))
  api.compare.mockResolvedValueOnce(basic).mockImplementationOnce(() => new Promise<Comparison>((resolve) => { finishDeep = resolve }))
  const pinia = createPinia()
  useAppStore(pinia).selected = [1, 2]
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/compare', component: ComparePage }] })
  await router.push('/compare')
  await router.isReady()
  wrapper = mount(ComparePage, { global: { plugins: [pinia, router], stubs: { TrendChart: true } } })
  await flushPromises()
  expect(wrapper.find('.compare-table').exists()).toBe(true)
  await wrapper.get('select[aria-label="比较分析深度"]').setValue('deep')
  await flushPromises()
  expect(wrapper.find('.compare-table').exists()).toBe(false)
  expect(wrapper.text()).toContain('正在生成比较结果')
  finishDeep({ ...basic, repositories: basic.repositories.map((repo) => ({ ...repo, metrics: { ...metrics, commits90d: 42 } })), basis: { ...basic.basis, depth: 'deep' } })
  await flushPromises()
  expect(wrapper.find('.compare-table').text()).toContain('42')
})
