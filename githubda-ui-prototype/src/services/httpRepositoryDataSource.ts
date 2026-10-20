import type {
  CollectionSettings, ComparisonBundle, ComparisonEntry, Coverage, Granularity, HistogramResult, ReleaseDetails, ReleaseRecord,
  Metric, Observation, RepositoryAnalysis, RepositoryStatus, RepositorySummary,
  ResearchDataset, ResearchGroup, ResearchScatterPoint, TaskItem, TaskStatus, TimePoint, TimeWindow,
} from './types'
import type { RepositoryDataSource } from './repositoryDataSource'

interface Envelope<T> { data: T; meta?: Record<string, unknown> }
interface ApiError { error?: { code?: string; message?: string }; request_id?: string }

let csrfToken: string | null = null
let sessionRequest: Promise<void> | null = null

async function openSession() {
  if (!sessionRequest) {
    sessionRequest = fetch('/api/browser/session', {
      credentials: 'same-origin',
      headers: { 'X-GDA-Request': 'browser' },
    }).then(async (response) => {
      if (!response.ok) throw new Error('无法建立本机浏览器会话，请确认后端已启动并刷新页面')
      const body = await response.json() as { csrf_token?: string }
      if (!body.csrf_token) throw new Error('后端未返回浏览器请求校验令牌')
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
    const body = await response.json().catch(() => ({})) as ApiError
    const message = body.error?.message ?? `请求失败（${response.status}）`
    throw new Error(body.request_id ? `${message}（请求编号 ${body.request_id}）` : message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function data<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request<Envelope<T>>(path, init)).data
}

async function csv(path: string): Promise<Blob> {
  await openSession()
  const response = await fetch(`/api/browser/v1${path}`, {
    credentials: 'same-origin',
    headers: { 'X-GDA-Request': 'browser' },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as ApiError
    throw new Error(body.error?.message ?? `导出失败（${response.status}）`)
  }
  return response.blob()
}

function object(value: unknown): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, any> : {}
}
function array(value: unknown): Record<string, any>[] {
  return Array.isArray(value) ? value.map(object) : []
}
function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
function textOrNull(value: unknown): string | null { return typeof value === 'string' && value ? value : null }
function shortDate(value: unknown): string | null { return textOrNull(value)?.slice(0, 10) ?? null }
function qualityReason(value: unknown): string | undefined {
  if (typeof value !== 'string' || !value) return undefined
  const messages: Record<string, string> = {
    GITHUB_MAX_PAGES: '已达到单次采集页数上限，当前结果可能不完整',
    GITHUB_RATE_LIMITED: 'GitHub 请求暂时受限，请稍后重新采集',
    GITHUB_TIMEOUT: 'GitHub 响应超时，当前结果可能不完整',
    GITHUB_UPSTREAM_ERROR: 'GitHub 暂时无法提供完整数据',
  }
  return messages[value] ?? value
}
function repositoryId(id: string): number {
  const parsed = Number(id)
  if (!Number.isSafeInteger(parsed) || parsed <= 0) throw new Error('仓库编号无效，请从仓库列表重新打开')
  return parsed
}
function mapStatus(value: unknown): RepositoryStatus {
  switch (value) {
    case 'completed': return 'ready'
    case 'partial': return 'partial'
    case 'queued': case 'processing': return 'running'
    case 'failed': return 'failed'
    default: return 'idle'
  }
}
function mapRepository(value: Record<string, any>, extras: Record<string, any> = {}): RepositorySummary {
  const raw = object(value.repository ?? value)
  const fullName = String(raw.full_name ?? value.full_name ?? '')
  return {
    id: String(raw.repository_id ?? value.repository_id ?? ''),
    fullName,
    description: textOrNull(raw.description),
    language: textOrNull(raw.language),
    stars: numberOrNull(raw.stars),
    forks: numberOrNull(raw.forks),
    license: textOrNull(value.license_spdx),
    topics: Array.isArray(value.topics) ? value.topics.map(String) : [],
    createdAt: shortDate(raw.created_at),
    pushedAt: shortDate(raw.pushed_at),
    archived: typeof raw.archived === 'boolean' ? raw.archived : null,
    sizeKb: numberOrNull(value.size_kb),
    openIssuesAndPrCount: numberOrNull(value.open_issues_and_pr_count),
    status: mapStatus(raw.analysis_status),
    lastAnalyzedAt: shortDate(raw.last_successful_collection_at),
    activityDelta: null,
    htmlUrl: textOrNull(value.html_url) ?? `https://github.com/${fullName}`,
    ...extras,
  }
}
function mapCoverage(quality: Record<string, any> | undefined, label: string): Coverage {
  if (!quality || quality.coverage === 'not_collected' || quality.status === 'missing' || quality.status === 'failed') {
    return { state: 'missing', label: '未采集', detail: qualityReason(quality?.reason) ?? `${label}暂无可用分析结果` }
  }
  if (quality.coverage === 'partial' || quality.status === 'partial' || quality.status === 'insufficient_samples') {
    return { state: 'partial', label: quality.status === 'insufficient_samples' ? '样本不足' : '部分覆盖', detail: qualityReason(quality.reason) }
  }
  if (quality.limit_reached === true) {
    return { state: 'complete', label: '按设置完成', detail: qualityReason(quality.reason) }
  }
  return { state: 'complete', label: '完整覆盖' }
}
function mapPoints(value: unknown, window: TimeWindow): TimePoint[] {
  const points = array(value).map((item) => ({
    date: String(item.start ?? '').slice(0, 10),
    value: numberOrNull(item.value),
    observedValue: numberOrNull(item.observed_events),
  }))
  if (!points.length) return points
  const end = Date.parse(`${points[points.length - 1].date}T00:00:00Z`)
  if (!Number.isFinite(end)) return points
  const cutoff = end - window * 86_400_000
  return points.filter((point) => Date.parse(`${point.date}T00:00:00Z`) >= cutoff)
}
function durationHistogram(metric: Record<string, any> | undefined, label: string): HistogramResult {
  const quality = object(metric?.quality)
  return {
    unit: '天',
    buckets: array(metric?.histogram).map((bucket) => ({ label: String(bucket.label ?? ''), count: Number(bucket.count ?? 0) })),
    percentiles: {
      p50: numberOrNull(metric?.median_hours) === null ? null : Number(((metric?.median_hours ?? 0) / 24).toFixed(1)),
      p75: numberOrNull(metric?.p75_hours) === null ? null : Number(((metric?.p75_hours ?? 0) / 24).toFixed(1)),
      p90: numberOrNull(metric?.p90_hours) === null ? null : Number(((metric?.p90_hours ?? 0) / 24).toFixed(1)),
    },
    sampleSize: Number(quality.valid_samples ?? 0),
    coverage: mapCoverage(quality, label),
    note: qualityReason(quality.reason),
  }
}
function buildObservations(commit: Record<string, any>, issue: Record<string, any>, pull: Record<string, any>, release: Record<string, any>, limitations: unknown): Observation[] {
  const observations: Observation[] = []
  const commitQuality = object(commit.quality)
  const recent = numberOrNull(commit.recent_4w)
  const previous = numberOrNull(commit.previous_4w)
  const change = numberOrNull(commit.change_rate_pct)
  if (commitQuality.status === 'ready' && recent !== null && previous !== null) {
    const comparison = change === null
      ? `前 4 周为 ${previous.toLocaleString('en-US')} 次；基期为零，不计算变化率`
      : `较前 4 周${change >= 0 ? '增加' : '减少'} ${Math.abs(change).toFixed(1)}%（${previous.toLocaleString('en-US')} → ${recent.toLocaleString('en-US')} 次）`
    observations.push({
      id: 'commit-trend',
      text: `近 4 个完整周有 ${recent.toLocaleString('en-US')} 次提交，${comparison}。`,
      evidence: '主要数据 · 8 个完整自然周对比',
    })
  }

  const addDurationObservation = (metric: Record<string, any>, label: string, id: string) => {
    const quality = object(metric.quality)
    const sampleSize = numberOrNull(quality.valid_samples) ?? 0
    const medianHours = numberOrNull(metric.median_hours)
    const p90Hours = numberOrNull(metric.p90_hours)
    if (!['ready', 'partial'].includes(String(quality.status)) || sampleSize < 10 || medianHours === null) return
    const partialNote = quality.coverage === 'partial' ? '（仅已观察样本，覆盖不完整）' : ''
    const p90 = p90Hours === null ? '' : `，P90 ${Number((p90Hours / 24).toFixed(1))} 天`
    observations.push({
      id,
      text: `${label}耗时中位数 ${Number((medianHours / 24).toFixed(1))} 天${p90}（有效样本 n=${sampleSize.toLocaleString('en-US')}）${partialNote}。`,
      evidence: `主要数据 · ${label} · 有效样本 n≥10`,
    })
  }
  addDurationObservation(issue, 'Issue 关闭', 'issue-duration')
  addDurationObservation(pull, 'PR 合并', 'pr-duration')

  const releaseQuality = object(release.quality)
  const releaseCount = numberOrNull(release.release_count) ?? numberOrNull(releaseQuality.valid_samples)
  const medianInterval = numberOrNull(release.median_interval_days)
  if (['ready', 'partial'].includes(String(releaseQuality.status)) && releaseCount !== null && releaseCount >= 2 && medianInterval !== null) {
    const partialNote = releaseQuality.coverage === 'partial' ? '（仅已观察样本，覆盖不完整）' : ''
    observations.push({
      id: 'release-cadence',
      text: `近 365 天有 ${releaseCount.toLocaleString('en-US')} 次正式 Release，中位发布间隔 ${Number(medianInterval.toFixed(1))} 天${partialNote}。`,
      evidence: '主要数据 · 至少 2 次正式 Release',
    })
  }

  const limitationItems = Array.isArray(limitations)
    ? limitations.map((text, index) => ({ id: `limitation-${index}`, text: String(text), evidence: '分析限制' }))
    : []
  return [...observations, ...limitationItems]
}
function summaryMetric(id: string, label: string, value: number | null, unit: string, note: string, sampleSize?: number): Metric {
  return { id, label, value, unit, note, sampleSize }
}
function statusFromInsights(status: unknown): RepositoryStatus | null {
  if (status === 'ready') return 'ready'
  if (status === 'partial') return 'partial'
  if (status === 'failed') return 'failed'
  return null
}

export class HttpRepositoryDataSource implements RepositoryDataSource {
  async getCollectionSettings(): Promise<CollectionSettings> {
    const settings = await data<{ github_max_pages: number }>('/settings')
    return { githubMaxPages: settings.github_max_pages }
  }

  async saveCollectionSettings(settings: CollectionSettings): Promise<CollectionSettings> {
    const saved = await data<{ github_max_pages: number }>('/settings', {
      method: 'POST',
      body: JSON.stringify({ github_max_pages: settings.githubMaxPages }),
    })
    return { githubMaxPages: saved.github_max_pages }
  }

  async listRepositories(): Promise<RepositorySummary[]> {
    const result = await data<{ items: Record<string, any>[] }>('/library/repositories?sort=last_collected&order=desc&per_page=100')
    return result.items.map((item) => mapRepository(item))
  }

  async searchRepositories(query: string): Promise<(RepositorySummary & { alreadyInLibrary: boolean })[]> {
    const params = new URLSearchParams({ q: query.trim(), per_page: '20' })
    const result = await data<{ items: Record<string, any>[] }>(`/github/search?${params}`)
    return result.items.map((item) => ({ ...mapRepository(item), alreadyInLibrary: Boolean(item.already_in_library) }))
  }

  async addRepository(input: string): Promise<{ repositoryId: string; taskId: string | null; existing: boolean }> {
    const resolved = await data<Record<string, any>>('/github/resolve', { method: 'POST', body: JSON.stringify({ input }) })
    const id = Number(resolved.repository_id)
    if (resolved.already_in_library) {
      const refreshed = await data<Record<string, any>>(`/repositories/${id}/refresh`, {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ depth: 'deep', force: false }),
      })
      return { repositoryId: String(id), taskId: textOrNull(refreshed.task_id), existing: true }
    }
    const added = await data<Record<string, any>>('/library/repositories', {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ full_name: resolved.full_name, auto_analyze: true, depth: 'deep' }),
    })
    return { repositoryId: String(added.repository_id), taskId: textOrNull(added.task_id), existing: false }
  }

  async removeRepository(id: string): Promise<void> {
    await request(`/library/repositories/${repositoryId(id)}`, { method: 'DELETE' })
  }

  async refreshRepository(id: string): Promise<string> {
    const result = await data<Record<string, any>>(`/repositories/${repositoryId(id)}/refresh`, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ depth: 'deep', force: false }),
    })
    return String(result.task_id)
  }

  async getAnalysis(id: string, window: TimeWindow, _granularity: Granularity): Promise<RepositoryAnalysis> {
    const numericId = repositoryId(id)
    const [detail, analysis, result] = await Promise.all([
      data<Record<string, any>>(`/repositories/${numericId}`),
      data<Record<string, any>>(`/repositories/${numericId}/analysis?depth=deep`),
      data<Record<string, any>>(`/repositories/${numericId}/insights`),
    ])
    const repository = mapRepository(detail)
    const insightMap = object(result.insights)
    const commit = object(insightMap.commit_activity)
    const issue = object(insightMap.issue_resolution)
    const pull = object(insightMap.pr_merges)
    const release = object(insightMap.release_cadence)
    const commitQuality = object(commit.quality)
    const issueQuality = object(issue.quality)
    const pullQuality = object(pull.quality)
    const releaseQuality = object(release.quality)
    const start = shortDate(result.window_start ?? object(analysis.source_metadata).window_start)
    const end = shortDate(result.window_end ?? object(analysis.source_metadata).window_end)
    const collectedAt = textOrNull(result.analyzed_at ?? object(analysis.source_metadata).collected_at)
    const weeklyCommits = mapPoints(commit.weekly, window)
    const weeklyIssues = mapPoints(issue.weekly, window)
    const weeklyPulls = mapPoints(pull.weekly, window)
    const commitsCoverage = mapCoverage(commitQuality, 'Commit')
    const issueCoverage = mapCoverage(issueQuality, 'Issue')
    const pullCoverage = mapCoverage(pullQuality, 'PR')
    const releaseCoverage = mapCoverage(releaseQuality, 'Release')
    const coverages = [commitsCoverage, issueCoverage, pullCoverage, releaseCoverage]
    const pageLimitReached = [commitQuality, issueQuality, pullQuality, releaseQuality].some((quality) => quality.limit_reached === true)
    const coverage: Coverage = coverages.every((item) => item.state === 'complete')
      ? { state: 'complete', label: pageLimitReached ? '按设置完成' : '完整覆盖', detail: pageLimitReached ? '至少一个活动接口达到用户设置的页数上限，未请求后续页。' : undefined }
      : coverages.every((item) => item.state === 'missing')
        ? { state: 'missing', label: '未采集', detail: result.limitations?.[0] }
        : { state: 'partial', label: '部分覆盖', detail: coverages.filter((item) => item.state !== 'complete').map((item) => item.label).join(' · ') }

    repository.status = statusFromInsights(result.status) ?? repository.status
    const change = numberOrNull(commit.change_rate_pct)
    repository.activityDelta = commitQuality.status === 'ready' ? change : null

    const commitsTotal = commitQuality.status === 'ready' && weeklyCommits.length && weeklyCommits.every((point) => point.value !== null)
      ? weeklyCommits.reduce((sum, point) => sum + (point.value ?? 0), 0)
      : null
    const issueDuration = durationHistogram(issue, 'Issue')
    const prDuration = durationHistogram(pull, 'PR')
    const releaseIntervals = array(release.timeline).slice(1).map((item, index) => ({
      tag: String(item.id ?? ''),
      days: Number(release.intervals_days?.[index] ?? 0),
    })).filter((item) => Number.isFinite(item.days) && item.days >= 0)
    const releases: ReleaseRecord[] = array(release.timeline).map((item) => ({
      tag: String(item.id ?? ''),
      identifierType: 'release_id',
      publishedAt: String(item.published_at ?? '').slice(0, 10),
      prerelease: false,
      intervalDays: null,
      note: '正式发布记录',
    }))
    for (let index = 1; index < releases.length; index += 1) {
      releases[index].intervalDays = releaseIntervals[index - 1]?.days ?? null
    }
    const metricWindow = { start, end }
    const metrics = {
      metrics: [
        summaryMetric('M01', '完整周 Commit 数', commitsTotal, '次', commitsCoverage.detail ?? '默认分支 · UTC 自然周', numberOrNull(commitQuality.valid_samples) ?? undefined),
        summaryMetric('M06', 'Issue 关闭耗时中位数', issueDuration.percentiles.p50, '天', qualityReason(issueQuality.reason) ?? 'closed_at − created_at', issueDuration.sampleSize),
        summaryMetric('M10', 'PR 合并耗时中位数', prDuration.percentiles.p50, '天', qualityReason(pullQuality.reason) ?? 'merged_at − created_at', prDuration.sampleSize),
        summaryMetric('M12', '正式发布中位间隔', numberOrNull(release.median_interval_days), '天', qualityReason(releaseQuality.reason) ?? '相邻正式 Release', numberOrNull(releaseQuality.valid_samples) ?? undefined),
      ],
      window: metricWindow,
      collectedAt,
      coverage,
    }
    const makeSeries = (key: string, label: string, points: TimePoint[], unit: string, quality: Record<string, any>, itemCoverage: Coverage) => ({
      series: [{ key, label, points }],
      unit,
      granularity: 'week' as const,
      window: metricWindow,
      sampleSize: numberOrNull(quality.valid_samples),
      coverage: itemCoverage,
      collectedAt,
      limitation: qualityReason(quality.reason),
    })
    const observations = buildObservations(commit, issue, pull, release, result.limitations)
    return {
      repository,
      metrics,
      commits: makeSeries('commits', 'Commit 数', weeklyCommits, '次', commitQuality, commitsCoverage),
      dailyCommits: { ...makeSeries('daily', '每日 Commit 数', [], '次', commitQuality, { state: 'missing', label: '未提供日级序列' }), granularity: 'day', limitation: '当前后端只提供自然周聚合，未生成每日分布。' },
      issues: makeSeries('closed', 'Issue 关闭数', weeklyIssues, '个 Issue', issueQuality, issueCoverage),
      issueDuration,
      openIssueAges: null,
      pullRequests: makeSeries('merged', 'PR 合并数', weeklyPulls, '个 PR', pullQuality, pullCoverage),
      prDuration,
      longOpenPrs: [],
      releases,
      releaseIntervals,
      authors: [],
      coverage,
      collectedAt,
      observations,
    }
  }

  async getReleaseDetails(repositoryIdValue: string, releaseId: string): Promise<ReleaseDetails> {
    const detail = await data<Record<string, unknown>>(`/repositories/${repositoryId(repositoryIdValue)}/releases/${encodeURIComponent(releaseId)}`)
    return {
      name: textOrNull(detail.name),
      body: typeof detail.body === 'string' && detail.body ? detail.body : null,
    }
  }

  async getComparison(ids: string[], _window: TimeWindow): Promise<ComparisonBundle> {
    const repositoryIds = ids.map(repositoryId)
    const result = await data<Record<string, any>>('/comparisons/insights', {
      method: 'POST',
      body: JSON.stringify({ repository_ids: repositoryIds, depth: 'deep' }),
    })
    const colors = ['#E2683C', '#CE3F7C', '#2E8FCB', '#E5A03A', '#3B5BDB']
    const entries: ComparisonEntry[] = array(result.repositories).map((row, index) => {
      const metrics = object(row.metrics)
      const commitMetric = object(metrics.commits_weekly_mean)
      const issueMetric = object(metrics.issue_median_hours)
      const prMetric = object(metrics.pr_median_hours)
      const releaseMetric = object(metrics.release_interval_days)
      const points = array(row.weekly_commits).map((point) => ({ date: String(point.start ?? '').slice(0, 10), value: numberOrNull(point.value) }))
      const qualityStatus = String(commitMetric.quality ?? 'missing')
      return {
        id: String(row.repository_id),
        label: String(row.full_name ?? ''),
        color: colors[index % colors.length],
        points,
        coverage: qualityStatus === 'ready' ? { state: 'complete', label: '完整覆盖' } : qualityStatus === 'missing' ? { state: 'missing', label: '未采集' } : { state: 'partial', label: qualityStatus === 'insufficient_samples' ? '样本不足' : '部分覆盖' },
        collectedAt: shortDate(row.analyzed_at) ?? '—',
        issueP50: numberOrNull(issueMetric.value) === null ? null : Number((issueMetric.value / 24).toFixed(1)),
        issueSample: Number(issueMetric.valid_samples ?? 0),
        prP50: numberOrNull(prMetric.value) === null ? null : Number((prMetric.value / 24).toFixed(1)),
        prSample: Number(prMetric.valid_samples ?? 0),
        releaseMedianDays: numberOrNull(releaseMetric.value),
      }
    })
    const points = entries.flatMap((entry) => entry.points)
    const dates = points.map((point) => point.date).sort()
    return {
      window: { start: dates[0] ?? '—', end: dates[dates.length - 1] ?? '—' },
      entries,
      notes: Array.isArray(result.warnings) ? result.warnings.map(String) : [],
    }
  }

  async getResearchDataset(id?: string): Promise<ResearchDataset> {
    const datasets = await data<{ items: Record<string, any>[] }>('/datasets')
    const research = datasets.items.filter((item) => item.type === 'research')
    const selected = research.find((item) => item.dataset_id === id) ?? research[0]
    if (!selected) throw new Error('当前没有可分析的研究数据集')
    const datasetId = String(selected.dataset_id)
    const [insights, quality] = await Promise.all([
      data<Record<string, any>>(`/research/insights?dataset_id=${encodeURIComponent(datasetId)}`),
      data<Record<string, any>>(`/research/data-quality?dataset_id=${encodeURIComponent(datasetId)}`),
    ])
    const rows = array(insights.rows)
    const groups: ResearchGroup[] = array(insights.groups).map((group) => {
      const metric = object(object(group.metrics).issue_median_hours)
      return {
        label: String(group.language ?? '未知'),
        count: Number(group.n ?? 0),
        medianCloseDays: numberOrNull(metric.median) === null ? null : Number((metric.median / 24).toFixed(1)),
        p25: null,
        p75: null,
      }
    })
    const scatter: ResearchScatterPoint[] = rows.flatMap((row) => {
      const values = object(row.values)
      const issue = numberOrNull(values.issue_median_hours)
      const pr = numberOrNull(values.pr_median_hours)
      if (issue === null || pr === null) return []
      return [{ repository: String(row.full_name), issueCloseDays: issue / 24, prMergeDays: pr / 24, group: String(row.language ?? '未知') }]
    })
    const correlation = object(insights.correlation)
    const summary = object(insights.summary)
    const issueSummary = object(summary.issue_median_hours)
    const prSummary = object(summary.pr_median_hours)
    const windows = new Set(rows.filter((row) => row.window_start && row.window_end).map((row) => `${row.window_start}|${row.window_end}`))
    const uniqueWindow = windows.size === 1 ? [...windows][0].split('|') : [null, null]
    return {
      id: datasetId,
      name: String(selected.name ?? datasetId),
      exploratory: false,
      samplingSource: '项目研究数据集',
      samplingRule: selected.rules_version ? `规则版本 ${selected.rules_version}` : '后端未记录采样规则说明',
      frozenAt: shortDate(selected.frozen_at),
      eventWindow: { start: shortDate(uniqueWindow[0]), end: shortDate(uniqueWindow[1]) },
      repositoryCount: Number(insights.sample_size ?? selected.sample_size ?? 0),
      eventCount: null,
      missingRate: numberOrNull(issueSummary.missing_rate) === null ? null : Number((issueSummary.missing_rate * 100).toFixed(1)),
      issueMedianDays: numberOrNull(issueSummary.median) === null ? null : Number((issueSummary.median / 24).toFixed(1)),
      issueSample: Number(issueSummary.count ?? 0),
      prMedianDays: numberOrNull(prSummary.median) === null ? null : Number((prSummary.median / 24).toFixed(1)),
      prSample: Number(prSummary.count ?? 0),
      groups,
      scatter: {
        points: scatter,
        spearman: numberOrNull(correlation.coefficient),
        sampleSize: Number(correlation.n ?? scatter.length),
        pValue: numberOrNull(correlation.p_value),
        note: String(correlation.note ?? '仅在有效配对样本中计算'),
      },
      quality: array(quality.missing_fields).map((field) => ({
        field: String(field.field ?? ''),
        missingRate: numberOrNull(field.rate) === null ? 0 : Number((field.rate * 100).toFixed(1)),
        collected: numberOrNull(field.rate) !== null,
      })),
      limitations: Array.isArray(insights.limitations) ? insights.limitations.map(String) : [],
    }
  }

  async listTasks(): Promise<TaskItem[]> {
    const result = await data<{ items: Record<string, any>[] }>('/tasks?per_page=100')
    const repositories = await this.listRepositories()
    const names = new Map(repositories.map((repo) => [Number(repo.id), repo.fullName]))
    return result.items.map((task) => {
      const error = object(task.error)
      const currentModule = String(task.current_module ?? task.type ?? 'repository')
      const status = task.status === 'succeeded' ? 'done' : String(task.status) as TaskStatus
      return {
        id: String(task.task_id),
        repositoryId: Number(task.repository_id),
        repository: names.get(Number(task.repository_id)) ?? `仓库 #${task.repository_id}`,
        module: currentModule,
        status,
        stage: textOrNull(task.message) ?? textOrNull(task.phase) ?? '等待 Worker 更新状态',
        progressPercent: numberOrNull(task.progress_percent),
        progressKind: task.progress_kind === 'stages' ? 'stages' : 'unknown',
        updatedAt: shortDate(task.progress_updated_at ?? task.finished_at ?? task.started_at ?? task.created_at) ?? '—',
        error: textOrNull(error.message) ?? undefined,
      }
    })
  }

  async retryTask(id: string): Promise<string> {
    const result = await data<Record<string, any>>(`/tasks/${encodeURIComponent(id)}/retry`, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    })
    return String(result.task_id)
  }

  exportInsights(id: string): Promise<Blob> {
    return csv(`/repositories/${repositoryId(id)}/insights/export.csv`)
  }

  exportComparison(ids: string[]): Promise<Blob> {
    const params = new URLSearchParams({ repository_ids: ids.map(repositoryId).join(','), depth: 'deep' })
    return csv(`/exports/comparison.csv?${params}`)
  }

  exportRepositories(scope: 'library' | 'research', datasetId?: string): Promise<Blob> {
    const params = new URLSearchParams({ scope })
    if (datasetId) params.set('dataset_id', datasetId)
    return csv(`/exports/repositories.csv?${params}`)
  }
}
