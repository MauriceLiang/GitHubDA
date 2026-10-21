import type {
  AuthorContribution, CommitActivityPage, CommitEvent, ComparisonBundle, ComparisonEntry, Granularity, HistogramResult,
  IssueOnlineDetail, IssueRecord, IssueRecordDetail, IssueRecordPage, Metric, PullRequestActivityDetail, PullRequestActivityRecord, PullRequestActivityPage, PullRequestOnlineDetail, PullRequestRecord, ReleaseDetails, ReleaseRecord, RepositoryAnalysis, RepositorySummary,
  ResearchDataset, TaskItem, TimePoint, TimeSeriesResult, TimeWindow,
} from './types'
import type { RepositoryDataSource } from './repositoryDataSource'
import { addDays, addWeeks, iso, REPOSITORIES, repoSeed, type RepoSeed } from '@/mocks/catalog'

/** End of the demo dataset (collection timestamp). */
const DATASET_END = '2025-03-31'
const END = new Date(DATASET_END).getTime()
const DAY = 24 * 3600 * 1000

const seriesColor = ['#E2683C', '#CE3F7C', '#2E8FCB', '#E5A03A', '#3B5BDB']

function buckets(seed: RepoSeed, window: TimeWindow) {
  const end = seed.lastAnalyzedAt ?? DATASET_END
  const from = new Date(end).getTime() - window * DAY
  const rows = seed.weeklyCommits.map((value, i) => ({ date: addWeeks(seed.firstWeek, i), value }))
  return rows.filter((r) => new Date(r.date).getTime() >= from)
}

function coverageFor(seed: RepoSeed, window: TimeWindow) {
  const days = seed.weeklyCommits.length * 7
  if (seed.coverage.state === 'missing') return seed.coverage
  if (window > days) {
    return {
      state: 'partial' as const,
      label: '窗口覆盖不足',
      detail: `${window} 天窗口仅采集到 ${days} 天，图表只展示已采集范围`,
    }
  }
  return seed.coverage
}

function windowRange(seed: RepoSeed, window: TimeWindow) {
  const end = seed.lastAnalyzedAt ?? DATASET_END
  return { start: iso(new Date(new Date(end).getTime() - window * DAY)), end }
}

/** Turn weekly totals into daily points whose sum per week equals the total. */
function dailyPoints(seed: RepoSeed, window: TimeWindow): TimePoint[] {
  const weights = [0.1, 0.17, 0.15, 0.14, 0.13, 0.11, 0.2]
  const out: TimePoint[] = []
  buckets(seed, window).forEach((b, wi) => {
    const raw = weights.map((w, di) => Math.max(0, Math.round(b.value * w * (1 + (((wi * 7 + di) % 5) - 2) * 0.04))))
    const diff = b.value - raw.reduce((a, c) => a + c, 0)
    raw[6] = Math.max(0, raw[6] + diff)
    raw.forEach((v, di) => out.push({ date: addDays(b.date, di), value: v }))
  })
  return out
}

function weeklyPoints(seed: RepoSeed, window: TimeWindow, factor = 1): TimePoint[] {
  return buckets(seed, window).map((b) => ({ date: b.date, value: Math.round(b.value * factor) }))
}

function timeSeries(
  seed: RepoSeed, window: TimeWindow, granularity: Granularity, opts: {
    key: string; label: string; factor?: number; unit: string; sampleSize: number; coverage: RepoSeed['coverage']; limitation?: string
  },
): TimeSeriesResult {
  const points = opts.factor && opts.factor !== 1
    ? weeklyPoints(seed, window, opts.factor)
    : granularity === 'day'
      ? dailyPoints(seed, window)
      : weeklyPoints(seed, window)
  return {
    series: [{ key: opts.key, label: opts.label, points }],
    unit: opts.unit,
    granularity,
    window: windowRange(seed, window),
    sampleSize: opts.sampleSize,
    coverage: opts.coverage,
    collectedAt: `${seed.lastAnalyzedAt ?? DATASET_END} 02:14 UTC`,
    limitation: opts.limitation,
  }
}

function histogram(seed: RepoSeed, window: TimeWindow, kind: 'issue' | 'pr'): HistogramResult {
  const ratio = buckets(seed, window).length / Math.max(1, seed.weeklyCommits.length)
  const baseSample = kind === 'issue' ? seed.issueSample : seed.prSample
  const sample = Math.round(baseSample * (window === 90 ? 1 : ratio))
  const p50 = kind === 'issue' ? seed.issueP50 : seed.prP50
  const p75 = kind === 'issue' ? seed.issueP75 : seed.prP50 * 1.9
  const p90 = kind === 'issue' ? seed.issueP75 * 1.7 : seed.prP90
  const weights = kind === 'issue' ? [0.22, 0.29, 0.25, 0.14, 0.07, 0.03] : [0.38, 0.28, 0.17, 0.1, 0.05, 0.02]
  const labels = kind === 'issue'
    ? ['0–1 天', '1–3 天', '3–7 天', '7–14 天', '14–30 天', '30 天+']
    : ['<1 天', '1–3 天', '3–7 天', '7–14 天', '14–30 天', '30 天+']
  const counts = weights.map((w) => Math.round(sample * w))
  const total = counts.reduce((a, c) => a + c, 0)
  if (total > 0) counts[1] += sample - total
  return {
    unit: kind === 'issue' ? '个 Issue' : '个 PR',
    buckets: labels.map((label, i) => ({ label, count: Math.max(0, counts[i]) })),
    percentiles: {
      p50: sample ? p50 : null,
      p75: sample ? Number(p75.toFixed(1)) : null,
      p90: sample ? Number(p90.toFixed(1)) : null,
    },
    sampleSize: sample,
    coverage: kind === 'issue' ? seed.issueCoverage : seed.coverage,
    note: sample < 10 ? '样本数不足 10，分布仅作参考' : undefined,
  }
}

function metrics(seed: RepoSeed, window: TimeWindow): RepositoryAnalysis['metrics'] {
  const commits = buckets(seed, window).reduce((a, c) => a + c.value, 0)
  const authors = seed.authors.filter((a) => !a.isBot && !a.anonymous).length
  const issueSample = Math.round(seed.issueSample * (window === 90 ? 1 : buckets(seed, window).length / Math.max(1, seed.weeklyCommits.length)))
  const prSample = Math.round(seed.prSample * (window === 90 ? 1 : buckets(seed, window).length / Math.max(1, seed.weeklyCommits.length)))
  const list: Metric[] = [
    { id: 'M01', label: '提交数', value: commits, unit: '次', note: '去重 Commit SHA · 默认分支', sampleSize: commits },
    { id: 'M03', label: '活跃作者', value: seed.authors.length ? authors : null, unit: '人', note: `可识别身份${seed.authors.some((a) => a.anonymous) ? '，另有匿名作者' : ''}` },
    { id: 'M06', label: 'Issue 关闭耗时中位数', value: issueSample ? seed.issueP50 : null, unit: '天', note: `n=${issueSample} · P90 ${(seed.issueP75 * 1.7).toFixed(1)} 天`, sampleSize: issueSample },
    { id: 'M10', label: 'PR 合并耗时中位数', value: prSample ? seed.prP50 : null, unit: '天', note: `n=${prSample} · P90 ${seed.prP90} 天`, sampleSize: prSample },
  ]
  return {
    metrics: list,
    window: windowRange(seed, window),
    collectedAt: `${seed.lastAnalyzedAt ?? DATASET_END} 02:14 UTC`,
    coverage: coverageFor(seed, window),
  }
}

function issuesSeries(seed: RepoSeed, window: TimeWindow, granularity: Granularity): TimeSeriesResult {
  const factor = seed.issueFactor
  const created = weeklyPoints(seed, window).map((p, i) => ({ date: p.date, value: Math.round((p.value ?? 0) * factor * (1 + ((i % 3) - 1) * 0.12)) }))
  const closed = created.map((p, i) => ({ date: p.date, value: Math.max(0, Math.round(p.value * 0.92 * (i === created.length - 1 ? 0.7 : 1))) }))
  const total = created.reduce((a, c) => a + c.value, 0) + closed.reduce((a, c) => a + c.value, 0)
  return {
    series: [
      { key: 'created', label: '新增', points: created },
      { key: 'closed', label: '关闭', points: closed },
    ],
    unit: '个 Issue',
    granularity,
    window: windowRange(seed, window),
    sampleSize: total,
    coverage: seed.issueCoverage,
    collectedAt: `${seed.lastAnalyzedAt ?? DATASET_END} 02:14 UTC`,
    limitation: seed.issueCoverage.state === 'partial' ? seed.issueCoverage.detail : undefined,
  }
}

function prSeries(seed: RepoSeed, window: TimeWindow, granularity: Granularity): TimeSeriesResult {
  const created = weeklyPoints(seed, window).map((p, i) => ({ date: p.date, value: Math.round((p.value ?? 0) * seed.prFactor * (1 + ((i % 4) - 1.5) * 0.08)) }))
  const merged = created.map((p, i) => ({ date: p.date, value: Math.max(0, Math.round(p.value * 0.84 * (i === created.length - 1 ? 0.62 : 1))) }))
  const total = created.reduce((a, c) => a + c.value, 0) + merged.reduce((a, c) => a + c.value, 0)
  return {
    series: [
      { key: 'opened', label: '新建', points: created },
      { key: 'merged', label: '合并', points: merged },
    ],
    unit: '个 PR',
    granularity,
    window: windowRange(seed, window),
    sampleSize: total,
    coverage: seed.coverage,
    collectedAt: `${seed.lastAnalyzedAt ?? DATASET_END} 02:14 UTC`,
  }
}

function releasesOf(seed: RepoSeed): ReleaseRecord[] {
  return [...seed.releases].sort((a, b) => +new Date(a.publishedAt) - +new Date(b.publishedAt))
}

function observationsOf(seed: RepoSeed) {
  return seed.observations.map((text, i) => ({ id: `obs-${seed.id}-${i}`, text, evidence: '主要数据 · 演示统计窗口' }))
}

function summaryOf(seed: RepoSeed): RepositorySummary {
  return {
    id: seed.id,
    fullName: seed.fullName,
    description: seed.description,
    language: seed.language,
    stars: seed.stars,
    license: seed.license,
    topics: seed.topics,
    status: seed.status,
    lastAnalyzedAt: seed.lastAnalyzedAt,
    activityDelta: seed.activityDelta,
    scenario: seed.scenario,
  }
}

function demoPullRequestRecords(seed: RepoSeed): PullRequestActivityDetail[] {
  const rows: [number, string, string, string, PullRequestActivityRecord['state'], number, boolean][] = [
    [299, 'docs: 补充指标定义', '2025-03-04', '2025-03-10', 'merged', 2, false],
    [296, 'perf: 聚合查询缓存', '2025-03-08', '2025-03-13', 'merged', 5, false],
    [293, 'fix: 处理分页边界条件', '2025-03-15', '2025-03-20', 'closed', 3, true],
    [288, 'feat: 增加活动趋势筛选', '2025-03-18', '2025-03-19', 'merged', 1, false],
  ]
  return rows.map(([number, title, createdAt, terminalAt, state, commentsCount, draft]) => ({
    number,
    title,
    createdAt: `${createdAt}T09:00:00Z`,
    closedAt: `${terminalAt}T12:00:00Z`,
    mergedAt: state === 'merged' ? `${terminalAt}T12:00:00Z` : null,
    durationDays: state === 'merged' ? (new Date(`${terminalAt}T12:00:00Z`).getTime() - new Date(`${createdAt}T09:00:00Z`).getTime()) / DAY : null,
    state,
    draft,
    commentsCount,
    url: `https://github.com/${seed.fullName}/pull/${number}`,
    body: `## 改动说明\n\n这是用于界面预览的示例 Pull Request。\n\n- 目的：${title}\n- 状态：${state === 'merged' ? '已合并' : '关闭未合并'}\n\n演示内容不代表真实 GitHub 数据。`,
  }))
}

const sha = (n: number) => ((n * 2654435761) % 0xfffffff).toString(16).padStart(7, '0').slice(0, 7)
const COMMIT_TITLES = ['feat: 周聚合改为事件日期', 'fix: 排除 PR 类型的 Issue', 'chore: 升级解析依赖', 'docs: 补充指标定义', 'refactor: 统一时间口径', 'test: 增加部分采集用例', 'perf: 聚合查询缓存']

export class MockRepositoryDataSource implements RepositoryDataSource {
  private githubMaxPages = 10

  async getCollectionSettings() {
    return { githubMaxPages: this.githubMaxPages }
  }

  async saveCollectionSettings(settings: { githubMaxPages: number }) {
    this.githubMaxPages = settings.githubMaxPages
    return { githubMaxPages: this.githubMaxPages }
  }

  async searchRepositories(query: string) {
    const normalized = query.trim().toLowerCase()
    return REPOSITORIES.filter((seed) => seed.fullName.toLowerCase().includes(normalized))
      .map((seed) => ({ ...summaryOf(seed), alreadyInLibrary: true }))
  }

  async addRepository(input: string) {
    const repo = REPOSITORIES.find((seed) => seed.fullName.toLowerCase() === input.trim().toLowerCase())
    if (!repo) throw new Error('演示模式只支持打开内置示例仓库')
    return { repositoryId: repo.id, taskId: null, existing: true }
  }

  async removeRepository(): Promise<void> {
    throw new Error('演示模式不支持修改仓库库')
  }

  async refreshRepository(): Promise<string> { return 'mock-task' }

  async listRepositories(): Promise<RepositorySummary[]> {
    return REPOSITORIES.map(summaryOf)
  }

  async getAnalysis(id: string, window: TimeWindow, granularity: Granularity): Promise<RepositoryAnalysis> {
    const seed = repoSeed(id) ?? REPOSITORIES[0]
    const commits = buckets(seed, window).reduce((a, c) => a + c.value, 0)
    const prSample = Math.round(seed.prSample * (window === 90 ? 1 : buckets(seed, window).length / Math.max(1, seed.weeklyCommits.length)))
    return {
      repository: summaryOf(seed),
      metrics: metrics(seed, window),
      commits: timeSeries(seed, window, granularity, {
        key: 'commits', label: '提交数', unit: '次', sampleSize: commits, coverage: coverageFor(seed, window),
        limitation: '最后一周为未完成当周',
      }),
      dailyCommits: {
        series: [{ key: 'daily', label: '每日提交数', points: dailyPoints(seed, window) }],
        unit: '次', granularity: 'day', window: windowRange(seed, window), sampleSize: commits,
        coverage: coverageFor(seed, window), collectedAt: `${seed.lastAnalyzedAt ?? DATASET_END} 02:14 UTC`,
      },
      issues: issuesSeries(seed, window, granularity),
      issueDuration: histogram(seed, window, 'issue'),
      openIssueAges: seed.issueCoverage.state === 'complete'
        ? [{ label: '0–7 天', count: 96 }, { label: '8–30 天', count: 154 }, { label: '31–90 天', count: 118 }, { label: '90 天以上', count: 44 }]
        : null,
      pullRequests: prSeries(seed, window, granularity),
      prDuration: histogram(seed, window, 'pr'),
      longOpenPrs: ([
        { number: 312, title: 'feat: 周提交趋势支持按日聚合', createdAt: '2025-02-18', mergedAt: null, durationDays: 41, state: 'open', comments: 6 },
        { number: 308, title: 'fix: 排除 PR 类型的 Issue', createdAt: '2025-02-25', mergedAt: null, durationDays: 34, state: 'open', comments: 4 },
        { number: 301, title: 'refactor: 统一事件时间口径', createdAt: '2025-03-01', mergedAt: null, durationDays: 30, state: 'open', comments: 9 },
      ] as PullRequestRecord[]).slice(0, prSample > 20 ? 3 : 1),
      releases: releasesOf(seed),
      releaseIntervals: releasesOf(seed).filter((r) => !r.prerelease && r.intervalDays)
        .map((r) => ({ tag: r.tag, days: r.intervalDays as number })),
      authors: seed.authors,
      coverage: coverageFor(seed, window),
      collectedAt: `${seed.lastAnalyzedAt ?? DATASET_END} 02:14 UTC`,
      observations: observationsOf(seed),
    }
  }

  async getReleaseDetails(repositoryId: string, releaseId: string): Promise<ReleaseDetails> {
    const seed = repoSeed(repositoryId) ?? REPOSITORIES[0]
    const release = seed.releases.find((item) => item.tag === releaseId)
    if (!release) throw new Error('未找到该示例 Release')
    return { name: release.tag, body: release.note }
  }

  async getWeekCommits(id: string, weekStart: string): Promise<CommitEvent[]> {
    const seed = repoSeed(id) ?? REPOSITORIES[0]
    const seedNum = (new Date(weekStart).getTime() / DAY) % 97 + 11
    return Array.from({ length: 6 }, (_, i) => ({
      sha: sha(Math.round(seedNum) * 131 + i * 17),
      title: COMMIT_TITLES[(Math.round(seedNum) + i) % COMMIT_TITLES.length],
      author: seed.authors.filter((a) => !a.anonymous)[(Math.round(seedNum) + i) % Math.max(1, seed.authors.filter((a) => !a.anonymous).length)]?.author ?? 'anonymous',
      isBot: i === 4,
      date: `${addDays(weekStart, i % 7)} ${String(9 + i).padStart(2, '0')}:${String((i * 13) % 60).padStart(2, '0')} UTC`,
      url: `https://github.com/${seed.fullName}/commit/${sha(Math.round(seedNum) * 131 + i * 17)}`,
    }))
  }

  async getCommitActivity(id: string, page: number, perPage: number, search: string, weekStart?: string): Promise<CommitActivityPage> {
    const seed = repoSeed(id) ?? REPOSITORIES[0]
    const available = seed.coverage.state !== 'missing'
    const weeks = weekStart ? [weekStart] : buckets(seed, 90).map((bucket) => bucket.date)
    const items = available ? (await Promise.all(weeks.map((week) => this.getWeekCommits(id, week)))).flat() : []
    items.sort((a, b) => b.date.localeCompare(a.date) || b.sha.localeCompare(a.sha))
    const normalizedSearch = search.trim().toLocaleLowerCase()
    const filtered = items.filter((item) => !normalizedSearch || item.title.toLocaleLowerCase().includes(normalizedSearch) || item.author.toLocaleLowerCase().includes(normalizedSearch) || item.sha.toLocaleLowerCase().includes(normalizedSearch))
    const daily = new Map<string, number>()
    const authors = new Map<string, AuthorContribution>()
    items.forEach((item) => {
      const date = item.date.slice(0, 10)
      daily.set(date, (daily.get(date) ?? 0) + 1)
      const author = authors.get(item.author) ?? { author: item.author, commits: 0, isBot: item.isBot, anonymous: item.anonymous }
      author.commits += 1
      authors.set(item.author, author)
    })
    const window = weekStart
      ? { start: weekStart, end: addDays(weekStart, 7) }
      : windowRange(seed, 90)
    return {
      items: filtered.slice((page - 1) * perPage, page * perPage),
      page,
      perPage,
      total: filtered.length,
      available,
      coverage: seed.coverage,
      note: '演示模式：列表由示例数据生成，用于预览页面交互，不代表真实 GitHub 归档。',
      windowStart: window.start,
      windowEnd: window.end,
      commitCount: items.length,
      authorCount: authors.size,
      dailyCounts: [...daily.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, count]) => ({ date, count })),
      authors: [...authors.values()].sort((a, b) => b.commits - a.commits || a.author.localeCompare(b.author)).slice(0, 20),
    }
  }

  async getClosedIssues(id: string): Promise<IssueRecord[]> {
    const seed = repoSeed(id) ?? REPOSITORIES[0]
    const titles = ['时间窗口切换后主图未重绘', 'Issue 关闭耗时缺少 P90 标注', '分页截断时未提示部分数据', '作者身份解析失败导致重复计数', 'Release 时间轴按等距排列', '导出 CSV 缺少时区列']
    return titles.map((title, i) => {
      const createdAt = addDays('2025-03-24', -i * 6)
      const closedAt = addDays(createdAt, Math.max(1, Math.round(seed.issueP50 * (0.4 + i * 0.35))))
      return {
        number: 482 - i, title, createdAt, closedAt,
        durationDays: Math.round((new Date(closedAt).getTime() - new Date(createdAt).getTime()) / DAY),
        state: 'closed' as const,
        url: `https://github.com/${seed.fullName}/issues/${482 - i}`,
      }
    })
  }

  async getIssueRecords(id: string, page: number, perPage: number, search: string): Promise<IssueRecordPage> {
    const seed = repoSeed(id) ?? REPOSITORIES[0]
    const available = seed.issueCoverage.state !== 'missing'
    const query = search.trim().toLocaleLowerCase()
    const records = available ? await this.getClosedIssues(id) : []
    const filtered = query
      ? records.filter((record) => String(record.number).includes(query) || record.title.toLocaleLowerCase().includes(query))
      : records
    const window = windowRange(seed, 90)
    return {
      items: filtered.slice((page - 1) * perPage, page * perPage),
      page,
      perPage,
      total: filtered.length,
      available,
      coverage: seed.issueCoverage,
      note: available ? '演示数据仅用于界面预览；真实仓库记录来自本次采集窗口。' : '当前示例没有可展示的 Issue 逐条数据。',
      windowStart: window.start,
      windowEnd: window.end,
    }
  }

  async getIssueDetail(id: string, issueNumber: number): Promise<IssueRecordDetail> {
    const issue = (await this.getClosedIssues(id)).find((record) => record.number === issueNumber)
    if (!issue) throw new Error('未找到该示例 Issue')
    return { ...issue, body: `## 问题说明\n\n这是用于界面预览的示例 Issue 描述。\n\n- 现象：${issue.title}\n- 状态：已关闭\n\n演示数据仅用于预览。`, commentsCount: 1 }
  }

  async getIssueOnlineDetail(id: string, issueNumber: number): Promise<IssueOnlineDetail> {
    const issue = (await this.getClosedIssues(id)).find((record) => record.number === issueNumber)
    if (!issue) throw new Error('未找到该示例 Issue')
    return {
      ...issue,
      body: `## 问题说明\n\n这是用于界面预览的示例 Issue 描述。\n\n- 现象：${issue.title}\n- 状态：已关闭\n\n演示数据仅用于预览。`,
      author: 'demo-user',
      labels: ['bug', 'needs-info'],
      updatedAt: issue.closedAt,
      source: 'mock',
      commentsCount: 1,
      comments: [{ author: 'demo-bot', createdAt: '2025-03-25T08:00:00Z', body: '## 处理记录\n\n该问题已修复，请在最新版本中验证。此评论为界面预览示例。' }],
      commentsComplete: true,
      commentsError: null,
    }
  }

  async exportIssueRecords(id: string, search: string): Promise<Blob> {
    const seed = repoSeed(id) ?? REPOSITORIES[0]
    if (seed.issueCoverage.state === 'missing') throw new Error('当前示例没有可导出的 Issue 逐条数据')
    const query = search.trim().toLocaleLowerCase()
    const records = (await this.getClosedIssues(id)).filter((record) => !query || String(record.number).includes(query) || record.title.toLocaleLowerCase().includes(query))
    const cells = [
      ['issue_number', 'title', 'created_at', 'closed_at', 'duration_days', 'url'],
      ...records.map((record) => [record.number, record.title, record.createdAt, record.closedAt, record.durationDays, record.url ?? '']),
    ]
    const escape = (value: string | number | null) => {
      const text = value === null ? '' : String(value)
      const safe = /^[=+@\t\r-]/.test(text) ? `'${text}` : text
      return `"${safe.replaceAll('"', '""')}"`
    }
    return new Blob(['\ufeff', cells.map((row) => row.map(escape).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
  }

  async getPullRequestRecords(id: string, page: number, perPage: number, search: string): Promise<PullRequestActivityPage> {
    const seed = repoSeed(id) ?? REPOSITORIES[0]
    const available = seed.coverage.state !== 'missing'
    const query = search.trim().toLocaleLowerCase()
    const filtered = (available ? demoPullRequestRecords(seed) : []).filter((record) =>
      !query || String(record.number).includes(query) || record.title.toLocaleLowerCase().includes(query),
    )
    const window = windowRange(seed, 90)
    return {
      items: filtered.slice((page - 1) * perPage, page * perPage).map(({ body: _body, ...record }) => record),
      page,
      perPage,
      total: filtered.length,
      available,
      coverage: seed.coverage,
      note: available
        ? '演示数据仅用于界面预览；列表模拟本次采集窗口中的已合并与关闭未合并 PR。'
        : '当前示例没有可展示的 Pull Request 逐条数据。',
      windowStart: window.start,
      windowEnd: window.end,
    }
  }

  async getPullRequestDetail(id: string, pullNumber: number): Promise<PullRequestActivityDetail> {
    const seed = repoSeed(id) ?? REPOSITORIES[0]
    const record = demoPullRequestRecords(seed).find((item) => item.number === pullNumber)
    if (!record) throw new Error('未找到该示例 Pull Request')
    return record
  }

  async getPullRequestOnlineDetail(id: string, pullNumber: number): Promise<PullRequestOnlineDetail> {
    const record = await this.getPullRequestDetail(id, pullNumber)
    return {
      number: record.number,
      title: record.title,
      body: record.body,
      state: record.state,
      author: 'demo-contributor',
      labels: record.draft ? ['draft'] : ['enhancement'],
      createdAt: record.createdAt,
      closedAt: record.closedAt,
      mergedAt: record.mergedAt,
      updatedAt: record.closedAt,
      url: record.url,
      commentsCount: record.commentsCount,
      comments: record.commentsCount ? [{ author: 'demo-reviewer', body: '演示评论：该改动已完成检查。', createdAt: record.closedAt }] : [],
      commentsComplete: true,
      commentsError: null,
    }
  }

  async exportPullRequestRecords(id: string, search: string): Promise<Blob> {
    const seed = repoSeed(id) ?? REPOSITORIES[0]
    if (seed.coverage.state === 'missing') throw new Error('当前示例没有可导出的 Pull Request 逐条数据')
    const query = search.trim().toLocaleLowerCase()
    const records = demoPullRequestRecords(seed).filter((record) =>
      !query || String(record.number).includes(query) || record.title.toLocaleLowerCase().includes(query),
    )
    const cells = [
      ['pull_number', 'title', 'state', 'created_at', 'closed_at', 'merged_at', 'merge_duration_days', 'draft', 'comments_count', 'url'],
      ...records.map((record) => [record.number, record.title, record.state, record.createdAt ?? '', record.closedAt ?? '', record.mergedAt ?? '', record.durationDays, record.draft, record.commentsCount, record.url ?? '']),
    ]
    const escape = (value: string | number | boolean | null) => {
      const text = value === null ? '' : String(value)
      const safe = /^[=+@\t\r-]/.test(text) ? `'${text}` : text
      return `"${safe.replaceAll('"', '""')}"`
    }
    return new Blob(['\ufeff', cells.map((row) => row.map(escape).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
  }

  async getPullRequests(id: string): Promise<PullRequestRecord[]> {
    const seed = repoSeed(id) ?? REPOSITORIES[0]
    const rows: [number, string, string, number, number, PullRequestRecord['state']][] = [
      [312, 'feat: 周提交趋势支持按日聚合', '2025-02-18', 41, 6, 'open'],
      [308, 'fix: 排除 PR 类型的 Issue', '2025-02-25', 34, 4, 'open'],
      [299, 'docs: 补充指标定义', '2025-03-04', 6, 2, 'merged'],
      [296, 'perf: 聚合查询缓存', '2025-03-08', 5, 5, 'merged'],
    ]
    return rows.map(([number, title, createdAt, days, comments, state]) => ({
      number, title, createdAt,
      mergedAt: state === 'merged' ? addDays(createdAt, days) : null,
      durationDays: state === 'merged' ? days : days,
      state, comments,
      url: `https://github.com/${seed.fullName}/pull/${number}`,
    }))
  }

  async getComparison(ids: string[], window: TimeWindow): Promise<ComparisonBundle> {
    const entries: ComparisonEntry[] = ids.map((id, i) => {
      const seed = repoSeed(id) ?? REPOSITORIES[0]
      const points = weeklyPoints(seed, window)
      const isPartial = seed.coverage.state !== 'complete'
      return {
        id,
        label: seed.fullName,
        color: seriesColor[i % seriesColor.length],
        points: isPartial ? points : points,
        coverage: coverageFor(seed, window),
        collectedAt: `${seed.lastAnalyzedAt ?? DATASET_END}`,
        issueP50: seed.issueSample >= 10 ? seed.issueP50 : null,
        issueSample: seed.issueSample,
        prP50: seed.prSample >= 10 ? seed.prP50 : null,
        prSample: seed.prSample,
        releaseMedianDays: seed.releases.find((release) => release.intervalDays !== null)?.intervalDays ?? null,
      }
    })
    return {
      window: { start: iso(new Date(END - window * DAY)), end: DATASET_END },
      entries,
      notes: [
        '各仓库采集时间与覆盖状态不同，差异可能来自采集而非项目本身。',
        '缺乏有效样本的指标显示为「—」，不参与排名。',
      ],
    }
  }

  async getResearchDataset(id = 'research-2025q1'): Promise<ResearchDataset> {
    const groups = [
      { label: 'TypeScript', count: 28, medianCloseDays: 4.2, p25: 2.1, p75: 8.4 },
      { label: 'JavaScript', count: 19, medianCloseDays: 5.6, p25: 2.8, p75: 11.2 },
      { label: 'Python', count: 16, medianCloseDays: 6.8, p25: 3.4, p75: 11.6 },
      { label: 'Go', count: 12, medianCloseDays: 2.9, p25: 1.6, p75: 5.4 },
      { label: 'Rust', count: 7, medianCloseDays: 3.1, p25: 2.0, p75: 6.2 },
      { label: '其他', count: 4, medianCloseDays: 7.4, p25: 4.1, p75: 13.0 },
    ]
    const points = Array.from({ length: 40 }, (_, i) => {
      const issueCloseDays = 1 + ((i * 17) % 120) / 10
      const raw = 0.5 + issueCloseDays * 0.2 + ((((i * 53) % 50) / 10) - 2.5)
      return {
        repository: `sample-${String(i + 1).padStart(2, '0')}`,
        issueCloseDays,
        prMergeDays: Number(Math.max(0.4, Math.min(7.6, raw)).toFixed(1)),
        group: ['TypeScript', 'JavaScript', '其他'][i % 3],
      }
    })
    return {
      id,
      name: 'research-2025q1',
      exploratory: true,
      samplingSource: 'GitHub 搜索 · language:typescript/python/go，stars 1000–50000',
      samplingRule: '排除镜像与归档仓库，每语言最多 30 个；优先保留至少 1 次正式发布的仓库',
      frozenAt: '2025-02-28',
      eventWindow: { start: '2024-12-01', end: '2025-02-28' },
      repositoryCount: 86,
      eventCount: 24318,
      missingRate: 6.4,
      issueMedianDays: 4.1,
      issueSample: 1842,
      prMedianDays: 2.6,
      prSample: 918,
      groups,
      scatter: {
        points,
        spearman: 0.21,
        sampleSize: 84,
        pValue: 0.06,
        note: '样本内弱正相关，不表示因果',
      },
      quality: [
        { field: 'merged_at', missingRate: 8.1, collected: true },
        { field: 'closed_at', missingRate: 5.2, collected: true },
        { field: 'release 关联', missingRate: 12.4, collected: true },
        { field: '作者身份', missingRate: 3.4, collected: true },
        { field: 'license', missingRate: 0.8, collected: true },
        { field: 'first_response', missingRate: 38.6, collected: false },
      ],
      limitations: [
        '仅覆盖 stars 1000–50000 且 2025 年 1–2 月有活动的仓库，不代表 GitHub 全体。',
        'first_response 尚未采集，相关性分析未包含该字段。',
        'Issue 关闭耗时只统计有关闭时间的记录，重新打开只计最后一次关闭。',
      ],
    }
  }

  async listTasks(): Promise<TaskItem[]> {
    return [
      { id: 't1', repository: 'demo-labs/queue-demo', module: 'commits', status: 'running', stage: '分页拉取 · 已处理 1,200 / 6,800 条', processed: 1200, total: 6800, updatedAt: '刚刚' },
      { id: 't2', repository: 'demo-labs/docs-site', module: 'issues', status: 'queued', stage: '等待前序任务', processed: 0, total: 2400, updatedAt: '刚刚' },
      { id: 't3', repository: 'demo-labs/sparse-kit', module: 'pullRequests', status: 'partial', stage: '已获取 412 条，第 4 页后截断', processed: 412, total: 610, updatedAt: '14 分钟前' },
      { id: 't4', repository: 'demo-labs/empty-lite', module: 'releases', status: 'failed', stage: 'GitHub API 速率限制，已采集 3,200 条后暂停', processed: 3200, total: 6300, updatedAt: '32 分钟前', error: 'GitHub API 速率限制' },
      { id: 't5', repository: 'demo-labs/steady-core', module: 'commits', status: 'done', stage: '已完成', processed: 1304, total: 1304, updatedAt: '今天 02:14' },
      { id: 't6', repository: 'demo-labs/tiny-lab', module: 'issues', status: 'analyzing', stage: '统计分位数 · 3 / 7 条', processed: 3, total: 7, updatedAt: '刚刚' },
    ]
  }

  async retryTask(): Promise<string> { return 'mock-task-retry' }
  async exportInsights(): Promise<Blob> { return new Blob(['demo export'], { type: 'text/csv' }) }
  async exportComparison(): Promise<Blob> { return new Blob(['demo export'], { type: 'text/csv' }) }
  async exportRepositories(): Promise<Blob> { return new Blob(['demo export'], { type: 'text/csv' }) }
}

export type { AuthorContribution }
