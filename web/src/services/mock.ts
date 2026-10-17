import type { Comparison, DataQuality, Dataset, Depth, Metrics, Overview, Repository, RepositoryFilters, RepositoryService, ResearchResult, Task, TaskStatus } from './domain'

const STORE_KEY = 'githubda.v5.mock'
const SCHEMA_VERSION = 1
const demoMetrics = (stars: number | null, forks: number | null, commits90d: number | null, issuesClosed90d: number | null, prsMerged90d: number | null, releases365d: number | null): Metrics => ({ stars, forks, commits90d, issuesClosed90d, prsMerged90d, releases365d, ageDays: null, daysSincePush: null })

const seeds: Repository[] = [
  { repositoryId: 101, fullName: 'vuejs/core', htmlUrl: 'https://github.com/vuejs/core', description: 'Vue 3 核心运行时、编译器与响应式系统', language: 'TypeScript', stars: 48600, forks: 8200, archived: false, analysisStatus: 'completed', dataStatus: 'fresh', lastCollectedAt: '2026-10-16T08:00:00Z', topics: ['vue', 'frontend'], license: 'MIT', metadata: { coverage: 'complete', collectedAt: '2026-10-16T08:00:00Z', notes: [] }, metrics: demoMetrics(48600, 8200, 188, 42, 106, 12), trend: [{ date: '2026-10-10', value: 48020 }, { date: '2026-10-16', value: 48600 }] },
  { repositoryId: 102, fullName: 'facebook/react', htmlUrl: 'https://github.com/facebook/react', description: '用于构建用户界面的 JavaScript 库', language: 'JavaScript', stars: 240000, forks: 49000, archived: false, analysisStatus: 'completed', dataStatus: 'fresh', lastCollectedAt: '2026-10-16T07:00:00Z', topics: ['react', 'ui'], license: 'MIT', metadata: { coverage: 'complete', collectedAt: '2026-10-16T07:00:00Z', notes: [] }, metrics: demoMetrics(240000, 49000, 92, 81, 44, 4), trend: [{ date: '2026-10-09', value: 238400 }, { date: '2026-10-16', value: 240000 }] },
  { repositoryId: 103, fullName: 'tiangolo/fastapi', htmlUrl: 'https://github.com/tiangolo/fastapi', description: '高性能的 Python Web API 框架', language: 'Python', stars: 93300, forks: 8100, archived: false, analysisStatus: 'partial', dataStatus: 'fresh', lastCollectedAt: '2026-10-16T06:20:00Z', topics: ['api', 'python'], license: 'MIT', metadata: { coverage: 'partial', collectedAt: '2026-10-16T06:20:00Z', notes: ['部分历史 Issue 数据未采集'] }, metrics: demoMetrics(93300, 8100, 76, null, 58, 8), trend: [{ date: '2026-10-08', value: 92000 }, { date: '2026-10-16', value: 93300 }] },
  { repositoryId: 104, fullName: 'psf/requests', htmlUrl: 'https://github.com/psf/requests', description: '简洁友好的 Python HTTP 客户端', language: 'Python', stars: 54600, forks: 9100, archived: false, analysisStatus: 'not_started', dataStatus: 'missing', lastCollectedAt: null, topics: ['http', 'python'], license: 'Apache-2.0', metrics: null, trend: [] },
  { repositoryId: 105, fullName: 'shadcn-ui/ui', htmlUrl: 'https://github.com/shadcn-ui/ui', description: '可复用组件与设计系统示例', language: 'TypeScript', stars: 98000, forks: 6200, archived: false, analysisStatus: 'failed', dataStatus: 'missing', lastCollectedAt: null, topics: ['components'], license: 'MIT', metrics: null, trend: [] },
  { repositoryId: 106, fullName: 'astral-sh/ruff', htmlUrl: 'https://github.com/astral-sh/ruff', description: '快速的 Python linter 和 formatter', language: 'Rust', stars: 44000, forks: 1500, archived: false, analysisStatus: 'processing', dataStatus: 'missing', lastCollectedAt: null, metrics: null, trend: [] },
  { repositoryId: 107, fullName: 'golang/go', htmlUrl: 'https://github.com/golang/go', description: 'Go 编程语言', language: 'Go', stars: 132000, forks: 18000, archived: false, analysisStatus: 'completed', dataStatus: 'fresh', lastCollectedAt: '2026-10-14T12:00:00Z', metrics: demoMetrics(132000, 18000, 510, 214, 175, 2), trend: [] },
  { repositoryId: 108, fullName: 'rust-lang/rust', htmlUrl: 'https://github.com/rust-lang/rust', description: 'Rust 编程语言', language: 'Rust', stars: 108000, forks: 14000, archived: false, analysisStatus: 'completed', dataStatus: 'stale', lastCollectedAt: '2026-09-30T12:00:00Z', metrics: demoMetrics(108000, 14000, 730, 480, 340, 3), trend: [{ date: '2026-09-20', value: 107100 }, { date: '2026-09-30', value: 108000 }] },
]

const seedTasks: Task[] = [
  { taskId: 'demo-task-1', repositoryId: 103, depth: 'deep', status: 'partial', phase: null, progressPercent: 100, progressKind: 'stages', message: '部分历史数据未完成采集', createdAt: '2026-10-16T06:00:00Z', etaSeconds: null, modules: [{ name: 'profile', status: 'complete', coverage: 'complete' }, { name: 'issues', status: 'partial', coverage: 'partial' }] },
  { taskId: 'demo-task-2', repositoryId: 105, depth: 'basic', status: 'failed', phase: null, progressPercent: null, progressKind: 'unknown', message: '演示场景：Worker 暂不可用', createdAt: '2026-10-15T05:00:00Z', etaSeconds: null, modules: [] },
  { taskId: 'demo-task-3', repositoryId: 106, depth: 'basic', status: 'running', phase: 'collecting', progressPercent: 42, progressKind: 'stages', message: '正在采集仓库基础信息', createdAt: '2026-10-17T01:00:00Z', etaSeconds: null, modules: [{ name: 'profile', status: 'running', coverage: 'unknown' }] },
  { taskId: 'demo-task-4', repositoryId: 107, depth: 'deep', status: 'succeeded', phase: null, progressPercent: 100, progressKind: 'stages', message: '分析已完成', createdAt: '2026-10-14T12:00:00Z', etaSeconds: null, modules: [{ name: 'profile', status: 'complete', coverage: 'complete' }] },
  { taskId: 'demo-task-5', repositoryId: 108, depth: 'basic', status: 'queued', phase: null, progressPercent: null, progressKind: 'unknown', message: '等待 Worker 处理', createdAt: '2026-10-17T02:00:00Z', etaSeconds: null, modules: [] },
]

interface MockState { schemaVersion: number; libraryIds: number[]; repositories: Repository[]; tasks: Task[]; nextId: number; nextTask: number; datasetId: string }
const initialState = (): MockState => ({ schemaVersion: SCHEMA_VERSION, libraryIds: [101, 102, 103, 104, 105, 106], repositories: [], tasks: structuredClone(seedTasks), nextId: 200, nextTask: 1, datasetId: 'oss-2025' })
let state = readState()
const listeners = new Set<() => void>()
const notify = () => { persist(); listeners.forEach((listener) => listener()) }
function readState(): MockState {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORE_KEY) ?? 'null') as MockState | null
    if (parsed?.schemaVersion === SCHEMA_VERSION && Array.isArray(parsed.libraryIds) && Array.isArray(parsed.tasks)) return parsed
  } catch { /* corrupted demo state is reset to the fixed seed */ }
  return initialState()
}
function persist() { window.localStorage.setItem(STORE_KEY, JSON.stringify(state)) }
function allRepositories() { return [...seeds, ...state.repositories] }
function repository(id: number) { return allRepositories().find((repo) => repo.repositoryId === id) }
function hasDeepResult(repo: Repository) {
  return Boolean(repo.metrics && ([repo.metrics.commits90d, repo.metrics.issuesClosed90d, repo.metrics.prsMerged90d, repo.metrics.releases365d].some((value) => value !== null) || state.tasks.some((task) => task.repositoryId === repo.repositoryId && task.depth === 'deep' && (task.status === 'succeeded' || task.status === 'partial'))))
}
const clone = <T,>(value: T): T => structuredClone(value)
const delay = () => new Promise((resolve) => window.setTimeout(resolve, 120))
const active = (status: TaskStatus) => status === 'queued' || status === 'running'
function csv(rows: Array<Array<string | number | null>>) { return new Blob(['\ufeff' + rows.map((row) => row.map((cell) => `"${String(cell ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }) }
function createTask(repo: Repository, depth: Depth): Task {
  const existing = state.tasks.find((task) => task.repositoryId === repo.repositoryId && active(task.status))
  if (existing) return existing
  const task: Task = { taskId: `mock-${state.nextTask++}`, repositoryId: repo.repositoryId, depth, status: 'queued', phase: null, progressPercent: null, progressKind: 'unknown', message: '排队中', createdAt: new Date('2026-10-17T03:00:00Z').toISOString(), etaSeconds: null, modules: [] }
  state.tasks.unshift(task)
  repo.analysisStatus = 'queued'
  notify()
  window.setTimeout(() => {
    const current = state.tasks.find((item) => item.taskId === task.taskId)
    const currentRepo = repository(task.repositoryId)
    if (!current || !currentRepo || current.status !== 'queued') return
    current.status = 'running'; current.phase = 'collecting'; current.progressKind = 'stages'; current.progressPercent = 45; current.message = '正在采集仓库基础信息'; currentRepo.analysisStatus = 'processing'
    notify()
  }, 850)
  window.setTimeout(() => {
    const current = state.tasks.find((item) => item.taskId === task.taskId)
    const currentRepo = repository(task.repositoryId)
    if (!current || !currentRepo || current.status !== 'running') return
    current.status = 'succeeded'; current.phase = null; current.progressPercent = 100; current.message = '分析已完成'; currentRepo.analysisStatus = 'completed'; currentRepo.dataStatus = 'fresh'; currentRepo.lastCollectedAt = '2026-10-17T03:00:00Z'; currentRepo.metrics ??= demoMetrics(currentRepo.stars, currentRepo.forks, null, null, null, null); currentRepo.metadata = { coverage: 'complete', collectedAt: currentRepo.lastCollectedAt, notes: [] }
    notify()
  }, 3600)
  return task
}
function normalize(input: string) {
  const match = input.trim().match(/^(?:https?:\/\/(?:www\.)?github\.com\/)?([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?\/?$/i)
  if (!match || match[1].startsWith('.') || match[2].startsWith('.')) throw new Error('请输入 owner/repo 或有效的 GitHub 仓库链接')
  return `${match[1]}/${match[2]}`
}

const datasets: Dataset[] = [
  { datasetId: 'oss-2025', name: '开源生态研究样本 · 2025', type: 'research', sampleSize: 24, frozenAt: '2026-01-01T00:00:00Z', rulesVersion: '1.0' },
  { datasetId: 'oss-2026', name: '开源生态研究样本 · 2026', type: 'research', sampleSize: 0, frozenAt: null, rulesVersion: '1.1' },
  { datasetId: 'oss-empty', name: '空样本演示', type: 'featured', sampleSize: 0, frozenAt: null, rulesVersion: null },
]

export const mockService: RepositoryService = {
  async overview(): Promise<Overview> {
    await delay()
    const library = state.libraryIds.map(repository).filter((repo): repo is Repository => Boolean(repo))
    const tasks = state.tasks.slice(0, 5)
    return { total: library.length, analyzed: library.filter((repo) => repo.dataStatus === 'fresh' || repo.dataStatus === 'stale').length, active: state.tasks.filter((task) => active(task.status)).length, latestCollection: library.find((repo) => repo.lastCollectedAt)?.lastCollectedAt ?? null, recentRepositories: clone(library.slice(0, 4)), recentTasks: clone(tasks) }
  },
  async listRepositories(filters: RepositoryFilters = {}) {
    await delay()
    const query = filters.query?.toLocaleLowerCase() ?? ''
    let rows = state.libraryIds.map(repository).filter((repo): repo is Repository => Boolean(repo))
    if (query) rows = rows.filter((repo) => `${repo.fullName} ${repo.description ?? ''}`.toLocaleLowerCase().includes(query))
    if (filters.language) rows = rows.filter((repo) => repo.language === filters.language)
    if (filters.status) rows = rows.filter((repo) => repo.analysisStatus === filters.status)
    rows.sort((a, b) => {
      const sign = filters.order === 'desc' ? -1 : 1
      if (filters.sort === 'stars') return sign * ((a.stars ?? -1) - (b.stars ?? -1))
      if (filters.sort === 'last_collected') return sign * String(a.lastCollectedAt ?? '').localeCompare(String(b.lastCollectedAt ?? ''))
      return sign * a.fullName.localeCompare(b.fullName)
    })
    return clone(rows)
  },
  async searchRepositories(query, language) {
    await delay()
    const normalized = query.toLocaleLowerCase()
    return clone(allRepositories().filter((repo) => (!normalized || `${repo.fullName} ${repo.description ?? ''}`.toLocaleLowerCase().includes(normalized)) && (!language || repo.language === language)).slice(0, 10).map((repo) => ({ ...repo, alreadyInLibrary: state.libraryIds.includes(repo.repositoryId) })))
  },
  async addAndAnalyze(input) {
    await delay()
    const fullName = normalize(input)
    let repo = allRepositories().find((item) => item.fullName.toLocaleLowerCase() === fullName.toLocaleLowerCase())
    if (repo && state.libraryIds.includes(repo.repositoryId)) return { repositoryId: repo.repositoryId, taskId: null, existing: true }
    if (!repo) {
      repo = { repositoryId: state.nextId++, fullName, htmlUrl: `https://github.com/${fullName}`, description: null, language: null, stars: null, forks: null, archived: false, analysisStatus: 'not_started', dataStatus: 'missing', lastCollectedAt: null, metrics: null, trend: [] }
      state.repositories.push(repo)
    }
    state.libraryIds.unshift(repo.repositoryId)
    const task = createTask(repo, 'basic')
    notify()
    return { repositoryId: repo.repositoryId, taskId: task.taskId, existing: false }
  },
  async repositoryDetail(id) { await delay(); const repo = repository(id); if (!repo) throw new Error('仓库不存在或已从个人库移除'); return clone(repo) },
  async repositoryAnalysis(id, depth) {
    await delay()
    const repo = repository(id)
    if (!repo) throw new Error('仓库不存在')
    const task = state.tasks.find((item) => item.repositoryId === id && item.depth === depth)
    const resultMetrics = clone(depth === 'basic' || hasDeepResult(repo) ? repo.metrics ?? null : null)
    if (depth === 'basic' && resultMetrics) {
      resultMetrics.commits90d = null; resultMetrics.issuesClosed90d = null; resultMetrics.prsMerged90d = null; resultMetrics.releases365d = null
    }
    const coverage = resultMetrics ? depth === 'basic' ? 'complete' : repo.metadata?.coverage ?? 'unknown' : 'not_collected'
    const status = resultMetrics ? coverage === 'partial' ? 'partial' : 'completed' : task?.status === 'running' ? 'processing' : task?.status === 'queued' ? 'queued' : task?.status === 'failed' ? 'failed' : 'not_started'
    return { status, metrics: resultMetrics, coverage, limitations: ['演示样例，不代表当前 GitHub 数据', ...(repo.metadata?.notes ?? [])], source: resultMetrics ? { collectedAt: repo.lastCollectedAt, windowStart: depth === 'deep' && repo.lastCollectedAt ? new Date(new Date(repo.lastCollectedAt).getTime() - 90 * 86400000).toISOString() : null, windowEnd: depth === 'deep' ? repo.lastCollectedAt : null } : null }
  },
  async repositorySeries(id, metric) { await delay(); const repo = repository(id); return clone(repo?.dataStatus === 'fresh' || repo?.dataStatus === 'stale' ? (repo.trend ?? []).map((point) => ({ ...point, value: metric === 'forks' ? Math.round(point.value * 0.17) : point.value })) : []) },
  async refresh(id, depth) { await delay(); const repo = repository(id); if (!repo || !state.libraryIds.includes(id)) throw new Error('仓库不在个人库中'); return clone(createTask(repo, depth)) },
  async remove(id) { await delay(); state.libraryIds = state.libraryIds.filter((item) => item !== id); notify() },
  async compare(ids, depth): Promise<Comparison> {
    await delay()
    if (ids.length < 2 || ids.length > 5) throw new Error('请选择 2–5 个仓库进行比较')
    const rows = ids.map(repository).filter((repo): repo is Repository => Boolean(repo))
    if (rows.length !== ids.length || rows.some((repo) => repo.dataStatus === 'missing' || !repo.metrics)) throw new Error('只有已采集过数据的仓库可以比较')
    return { repositories: rows.map((repo) => {
      const actualDepth = depth === 'deep' && hasDeepResult(repo) ? 'deep' : 'basic'
      return { repositoryId: repo.repositoryId, fullName: repo.fullName, metrics: actualDepth === 'basic' ? { ...clone(repo.metrics!), commits90d: null, issuesClosed90d: null, prsMerged90d: null, releases365d: null } : clone(repo.metrics!), coverage: depth === 'deep' && actualDepth === 'basic' ? 'partial' : actualDepth === 'basic' ? 'complete' : repo.metadata?.coverage ?? 'unknown', source: { profileCollectedAt: repo.lastCollectedAt, analysisCollectedAt: repo.lastCollectedAt, analysisDepth: actualDepth, windowStart: actualDepth === 'deep' && repo.lastCollectedAt ? new Date(new Date(repo.lastCollectedAt).getTime() - 90 * 86400000).toISOString() : null, windowEnd: actualDepth === 'deep' ? repo.lastCollectedAt : null } }
    }), basis: { depth, metricWindow: '近 90 天 / 近一年', sameProjectType: false, warnings: ['数据为可重置的演示样例，不代表当前 GitHub 数据', '项目类型未经分类验证；请先核对用途、年龄与采集时点'] } }
  },
  async exportCsv(scope, datasetId) {
    await delay()
    if (scope === 'library') return csv([['仓库', '语言', 'Stars', 'Forks', '状态', '数据来源'], ...state.libraryIds.map(repository).filter((repo): repo is Repository => Boolean(repo)).map((repo) => [repo.fullName, repo.language, repo.stars, repo.forks, repo.analysisStatus, '演示数据'])])
    return csv([['数据集', '样本数', '说明'], [datasets.find((dataset) => dataset.datasetId === datasetId)?.name ?? '研究样本', datasets.find((dataset) => dataset.datasetId === datasetId)?.sampleSize ?? 0, '演示数据']])
  },
  async exportComparison(ids, depth) {
    const comparison = await mockService.compare(ids, depth)
    return csv([['仓库', 'Stars', 'Forks', '近 90 天提交', '近 90 天关闭 Issues', '近 90 天合并 PR', '近一年 Release', '数据覆盖'], ...comparison.repositories.map((row) => [row.fullName, row.metrics.stars, row.metrics.forks, row.metrics.commits90d, row.metrics.issuesClosed90d, row.metrics.prsMerged90d, row.metrics.releases365d, row.coverage])])
  },
  async listTasks(status) {
    await delay()
    const filtered = !status ? state.tasks : status === 'active' ? state.tasks.filter((task) => active(task.status)) : status === 'problem' ? state.tasks.filter((task) => task.status === 'partial' || task.status === 'failed') : status === 'done' ? state.tasks.filter((task) => task.status === 'succeeded') : state.tasks.filter((task) => task.status === status)
    return clone(filtered)
  },
  async retryTask(taskId) { await delay(); const task = state.tasks.find((item) => item.taskId === taskId); if (!task || !['failed', 'partial'].includes(task.status)) throw new Error('只有失败或部分完成的任务可以重试'); const repo = repository(task.repositoryId); if (!repo) throw new Error('仓库不存在'); const next = createTask(repo, task.depth); next.retryOf = task.taskId; return clone(next) },
  async listDatasets() { await delay(); return clone(datasets) },
  async researchStatistics(datasetId, groupBy, _language): Promise<ResearchResult> {
    await delay()
    if (datasetId !== 'oss-2025') return { datasetId, groupBy, validSampleSize: 0, summary: {}, groups: [], correlations: [] }
    const groups: ResearchResult['groups'] = groupBy === 'language'
      ? [{ group: 'TypeScript', n: 9, starsMedian: 24000, forksMedian: 3200, recentlyPushed90dPct: 77.8 }, { group: 'Python', n: 6, starsMedian: 18300, forksMedian: 2800, recentlyPushed90dPct: 66.7 }, { group: 'Rust', n: 5, starsMedian: 15500, forksMedian: 2200, recentlyPushed90dPct: 80 }, { group: 'Go', n: 3, starsMedian: 15200, forksMedian: 2100, recentlyPushed90dPct: 66.7 }]
      : groupBy === 'star_tier'
        ? [{ group: '0–10k', n: 7, starsMedian: 4800, forksMedian: 750, recentlyPushed90dPct: 57.1 }, { group: '10k–30k', n: 9, starsMedian: 18400, forksMedian: 2980, recentlyPushed90dPct: 66.7 }, { group: '30k+', n: 7, starsMedian: 54200, forksMedian: 9100, recentlyPushed90dPct: 85.7 }]
        : [{ group: '3 年以内', n: 8, starsMedian: 22500, forksMedian: 3700, recentlyPushed90dPct: 87.5 }, { group: '3–8 年', n: 10, starsMedian: 18400, forksMedian: 2980, recentlyPushed90dPct: 70 }, { group: '8 年以上', n: 5, starsMedian: 15200, forksMedian: 2100, recentlyPushed90dPct: 40 }]
    return { datasetId, groupBy, validSampleSize: 23, summary: { stars: { count: 23, mean: 31600, median: 18400, std: 22000 }, forks: { count: 23, mean: 5210, median: 2980, std: 6300 } }, groups, correlations: [{ x: 'Stars', y: 'Forks', method: 'Spearman', n: 23, coefficient: 0.86, pValue: 0.01, note: '仅表示当前演示样本内的相关性' }] }
  },
  async researchQuality(datasetId): Promise<DataQuality> {
    await delay()
    if (datasetId !== 'oss-2025') return { datasetId, recordsTotal: 0, recordsAnalyzable: 0, missingFields: [], excludedByReason: [], staleCount: 0, rulesVersion: null, coverageNotes: ['当前数据集没有样本'] }
    return { datasetId, recordsTotal: 24, recordsAnalyzable: 23, missingFields: [{ field: 'Stars', count: 1, rate: 1 / 24 }], excludedByReason: [{ reason: '关键字段缺失', count: 1 }], staleCount: 2, rulesVersion: '1.0', coverageNotes: ['固定演示样本；不代表 GitHub 全站分布'] }
  },
  resetMock() { state = initialState(); window.localStorage.removeItem(STORE_KEY); listeners.forEach((listener) => listener()) },
}

export function subscribeMock(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener) }
