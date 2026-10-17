import type { AnalysisStatus, Coverage, DataQuality, Dataset, Depth, Metrics, Overview, Repository, RepositoryFilters, RepositoryService, ResearchResult, Task, TaskStatus } from './domain'

interface Envelope<T> { data: T; meta?: { request_id?: string } }
interface ErrorBody { error?: { code?: string; message?: string }; request_id?: string }

let csrfToken: string | null = null
let sessionRequest: Promise<void> | null = null

async function openSession() {
  if (!sessionRequest) {
    sessionRequest = fetch('/api/browser/session', { credentials: 'same-origin', headers: { 'X-GDA-Request': 'browser' } }).then(async (response) => {
      if (!response.ok) throw new Error('无法建立本机浏览器会话，请确认应用只在本机运行后刷新页面')
      const body = await response.json() as { csrf_token: string }
      csrfToken = body.csrf_token
    }).finally(() => { sessionRequest = null })
  }
  await sessionRequest
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  await openSession()
  const headers = new Headers(init.headers)
  headers.set('X-GDA-Request', 'browser')
  if (csrfToken && init.method && init.method.toUpperCase() !== 'GET') headers.set('X-CSRF-Token', csrfToken)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api/browser/v1${path}`, { ...init, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as ErrorBody
    const message = body.error?.message ?? `请求失败（${response.status}）`
    const error = new Error(body.request_id ? `${message}（请求编号 ${body.request_id}）` : message)
    Object.assign(error, { code: body.error?.code, status: response.status })
    throw error
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function data<T>(path: string, init?: RequestInit): Promise<T> {
  const result = await request<Envelope<T>>(path, init)
  return result.data
}

async function csv(path: string): Promise<Blob> {
  await openSession()
  const response = await fetch(`/api/browser/v1${path}`, { credentials: 'same-origin', headers: { 'X-GDA-Request': 'browser' } })
  if (!response.ok) throw new Error(`导出失败（${response.status}）`)
  return response.blob()
}

function metrics(value: Record<string, unknown> | null | undefined): Metrics | null {
  if (!value) return null
  return {
    stars: numberOrNull(value.stars), forks: numberOrNull(value.forks), commits90d: numberOrNull(value.commits_90d),
    issuesClosed90d: numberOrNull(value.issues_closed_90d), prsMerged90d: numberOrNull(value.pr_merged_90d),
    releases365d: numberOrNull(value.release_count_365d), ageDays: numberOrNull(value.age_days), daysSincePush: numberOrNull(value.days_since_push),
  }
}
function numberOrNull(value: unknown): number | null { return typeof value === 'number' && Number.isFinite(value) ? value : null }
function mapRepository(value: Record<string, unknown>): Repository {
  return {
    repositoryId: Number(value.repository_id), fullName: String(value.full_name ?? ''), htmlUrl: String(value.html_url ?? ''),
    description: typeof value.description === 'string' ? value.description : null, language: typeof value.language === 'string' ? value.language : null,
    stars: numberOrNull(value.stars), forks: numberOrNull(value.forks), archived: Boolean(value.archived),
    analysisStatus: String(value.analysis_status ?? 'not_started') as AnalysisStatus, dataStatus: String(value.data_status ?? 'missing') as Repository['dataStatus'],
    lastCollectedAt: typeof value.last_successful_collection_at === 'string' ? value.last_successful_collection_at : null,
  }
}
function mapTask(value: Record<string, unknown>): Task {
  const modules = Array.isArray(value.modules) ? value.modules.map((item) => {
    const module = item as Record<string, unknown>
    return { name: String(module.name), status: String(module.status), coverage: String(module.coverage ?? 'unknown') as Task['modules'][number]['coverage'] }
  }) : []
  return {
    taskId: String(value.task_id), repositoryId: Number(value.repository_id), depth: String(value.depth ?? 'basic') as Depth,
    status: String(value.status) as TaskStatus, phase: typeof value.phase === 'string' ? value.phase : null,
    progressPercent: numberOrNull(value.progress_percent), progressKind: value.progress_kind === 'stages' ? 'stages' : 'unknown',
    message: typeof value.message === 'string' ? value.message : null, createdAt: String(value.created_at ?? ''),
    etaSeconds: numberOrNull(value.eta_seconds), modules,
  }
}

export const httpService: RepositoryService = {
  async overview(): Promise<Overview> {
    const [library, taskData, stats] = await Promise.all([
      data<{ items: Record<string, unknown>[] }>('/library/repositories?sort=last_collected&order=desc&per_page=100'),
      data<{ items: Record<string, unknown>[] }>('/tasks?per_page=5'),
      data<Record<string, unknown>>('/overview?scope=library'),
    ])
    const repos = library.items.map(mapRepository)
    const tasks = taskData.items.map(mapTask)
    const kpis = stats.kpis as Record<string, unknown>
    return { total: Number(kpis.repositories_total ?? repos.length), analyzed: Number(kpis.repositories_analyzed ?? 0), active: tasks.filter((task) => task.status === 'queued' || task.status === 'running').length, latestCollection: repos.find((repo) => repo.lastCollectedAt)?.lastCollectedAt ?? null, recentRepositories: repos.slice(0, 4), recentTasks: tasks }
  },
  async listRepositories(filters: RepositoryFilters = {}) {
    const params = new URLSearchParams()
    if (filters.query) params.set('q', filters.query)
    if (filters.language) params.set('language', filters.language)
    if (filters.status) params.set('status', filters.status)
    if (filters.sort) params.set('sort', filters.sort)
    params.set('order', filters.order ?? 'asc'); params.set('per_page', '100')
    const result = await data<{ items: Record<string, unknown>[] }>(`/library/repositories?${params}`)
    return result.items.map(mapRepository)
  },
  async searchRepositories(query, language) {
    const params = new URLSearchParams({ q: query, per_page: '20' }); if (language) params.set('language', language)
    const result = await data<{ items: Record<string, unknown>[] }>(`/github/search?${params}`)
    return result.items.map((item) => ({ ...mapRepository(item), alreadyInLibrary: Boolean(item.already_in_library) }))
  },
  async addAndAnalyze(input) {
    const resolved = await data<Record<string, unknown>>('/github/resolve', { method: 'POST', body: JSON.stringify({ input }) })
    const repo = mapRepository(resolved)
    if (resolved.already_in_library) return { repositoryId: repo.repositoryId, taskId: null, existing: true }
    const added = await data<Record<string, unknown>>('/library/repositories', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ full_name: repo.fullName, auto_analyze: true, depth: 'basic' }) })
    return { repositoryId: Number(added.repository_id), taskId: typeof added.task_id === 'string' ? added.task_id : null, existing: false }
  },
  async repositoryDetail(id) {
    const result = await data<Record<string, unknown>>(`/repositories/${id}`)
    const repo = result.repository as Record<string, unknown>
    const mapped = mapRepository(repo)
    mapped.htmlUrl = String(result.html_url ?? `https://github.com/${mapped.fullName}`)
    mapped.topics = Array.isArray(result.topics) ? result.topics.map(String) : []
    mapped.license = typeof result.license_spdx === 'string' ? result.license_spdx : null
    const metadata = result.source_metadata as Record<string, unknown> | null
    mapped.metadata = metadata ? { coverage: String(metadata.coverage ?? 'unknown') as Coverage, collectedAt: typeof metadata.collected_at === 'string' ? metadata.collected_at : null, notes: Array.isArray(metadata.notes) ? metadata.notes.map(String) : [] } : null
    return mapped
  },
  async repositoryAnalysis(id, depth) {
    const result = await data<Record<string, unknown>>(`/repositories/${id}/analysis?depth=${depth}`)
    const metadata = result.source_metadata as Record<string, unknown> | null
    return { status: String(result.analysis_status ?? 'not_started') as AnalysisStatus, metrics: metrics(result.metrics as Record<string, unknown> | null), coverage: String(metadata?.coverage ?? 'not_collected') as NonNullable<Repository['metadata']>['coverage'], limitations: Array.isArray(result.limitations) ? result.limitations.map(String) : [], source: metadata ? { collectedAt: typeof metadata.collected_at === 'string' ? metadata.collected_at : null, windowStart: typeof metadata.window_start === 'string' ? metadata.window_start : null, windowEnd: typeof metadata.window_end === 'string' ? metadata.window_end : null } : null }
  },
  async repositorySeries(id, metric) { const result = await data<{ points: Array<{ date: string; value: number }> }>(`/repositories/${id}/series?metric=${metric}`); return result.points },
  async refresh(id, depth) {
    const result = await data<Record<string, unknown>>(`/repositories/${id}/refresh`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ depth, force: false }) })
    return { taskId: String(result.task_id), repositoryId: id, depth, status: String(result.status) as TaskStatus, phase: null, progressPercent: null, progressKind: 'unknown', message: result.reused ? '已复用进行中的任务' : '排队中', createdAt: new Date().toISOString(), etaSeconds: null, modules: [] }
  },
  async remove(id) { await request(`/library/repositories/${id}`, { method: 'DELETE' }) },
  async compare(ids, depth) {
    const result = await data<Record<string, unknown>>('/comparisons', { method: 'POST', body: JSON.stringify({ repository_ids: ids, depth }) })
    const basis = result.comparison_basis as Record<string, unknown>
    const rows = result.repositories as Record<string, unknown>[]
    return { repositories: rows.map((row) => {
      const source = row.source as Record<string, unknown> | undefined
      const sourceDate = (key: string) => typeof source?.[key] === 'string' ? source[key] as string : null
      return { repositoryId: Number(row.repository_id), fullName: String(row.full_name), metrics: metrics(row.metrics as Record<string, unknown>)!, coverage: String(row.coverage ?? 'unknown') as Coverage, source: source ? { profileCollectedAt: sourceDate('profile_collected_at'), analysisCollectedAt: sourceDate('analysis_collected_at'), analysisDepth: String(source.analysis_depth) as Depth, windowStart: sourceDate('window_start'), windowEnd: sourceDate('window_end') } : undefined }
    }), basis: { depth: String(basis.depth) as Depth, metricWindow: String(basis.metric_window ?? ''), sameProjectType: Boolean(basis.same_project_type), warnings: Array.isArray(basis.warnings) ? basis.warnings.map(String) : [] } }
  },
  async exportComparison(ids, depth) { const params = new URLSearchParams({ repository_ids: ids.join(','), depth }); return csv(`/exports/comparison.csv?${params}`) },
  async exportCsv(scope, datasetId) { const params = new URLSearchParams({ scope }); if (datasetId) params.set('dataset_id', datasetId); return csv(`/exports/repositories.csv?${params}`) },
  async listTasks(status) { const params = new URLSearchParams({ per_page: '100' }); if (status && !['all', 'active', 'done', 'problem'].includes(status)) params.set('status', status); const result = await data<{ items: Record<string, unknown>[] }>(`/tasks?${params}`); const tasks = result.items.map(mapTask); return status === 'active' ? tasks.filter((task) => task.status === 'queued' || task.status === 'running') : status === 'done' ? tasks.filter((task) => task.status === 'succeeded') : status === 'problem' ? tasks.filter((task) => task.status === 'partial' || task.status === 'failed') : tasks },
  async retryTask(taskId) { const result = await data<Record<string, unknown>>(`/tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({}) }); return { taskId: String(result.task_id), repositoryId: 0, depth: 'basic', status: 'queued', phase: null, progressPercent: null, progressKind: 'unknown', message: '重新排队中', createdAt: new Date().toISOString(), etaSeconds: null, modules: [], retryOf: String(result.retry_of) } },
  async listDatasets() { const result = await data<{ items: Record<string, unknown>[] }>('/datasets'); return result.items.map((row) => ({ datasetId: String(row.dataset_id), name: String(row.name), type: String(row.type) as Dataset['type'], sampleSize: Number(row.sample_size), frozenAt: typeof row.frozen_at === 'string' ? row.frozen_at : null, rulesVersion: typeof row.rules_version === 'string' ? row.rules_version : null })) },
  async researchStatistics(datasetId, groupBy, language) {
    const params = new URLSearchParams({ dataset_id: datasetId, group_by: groupBy }); if (language) params.set('language', language)
    const result = await data<Record<string, unknown>>(`/research/statistics?${params}`)
    const summary = result.summary as ResearchResult['summary']; const groups = result.groups as Array<Record<string, unknown>>; const correlations = result.correlations as Array<Record<string, unknown>>
    return { datasetId, groupBy, validSampleSize: Number(result.valid_sample_size ?? 0), summary, groups: groups.map((row) => ({ group: String(row.group), n: Number(row.n), starsMedian: numberOrNull(row.stars_median), forksMedian: numberOrNull(row.forks_median), recentlyPushed90dPct: numberOrNull(row.recently_pushed_90d_pct) })), correlations: correlations.map((row) => ({ x: String(row.x), y: String(row.y), method: String(row.method), n: Number(row.n), coefficient: numberOrNull(row.coefficient), pValue: numberOrNull(row.p_value), note: typeof row.note === 'string' ? row.note : null })) }
  },
  async researchQuality(datasetId) {
    const result = await data<Record<string, unknown>>(`/research/data-quality?dataset_id=${encodeURIComponent(datasetId)}`)
    return { datasetId, recordsTotal: Number(result.records_total ?? 0), recordsAnalyzable: Number(result.records_analyzable ?? 0), missingFields: (result.missing_fields as Array<Record<string, unknown>>).map((row) => ({ field: String(row.field), count: Number(row.count), rate: numberOrNull(row.rate) })), excludedByReason: (result.excluded_by_reason as Array<Record<string, unknown>>).map((row) => ({ reason: String(row.reason), count: Number(row.count) })), staleCount: Number(result.stale_count ?? 0), rulesVersion: typeof result.sampling_rules_version === 'string' ? result.sampling_rules_version : null, coverageNotes: Array.isArray(result.coverage_notes) ? result.coverage_notes.map(String) : [] } as DataQuality
  },
}
