/**
 * Demo dataset for the prototype. All numbers are synthetic but internally
 * consistent (weekly totals = sum of daily buckets, KPIs = sums / medians of
 * the same records). Repositories use the `demo-labs/*` namespace so nobody
 * mistakes them for real projects.
 *
 * TODO(API-INTEGRATION): this file must not be shipped to production.
 */
import type {
  AuthorContribution, Coverage, ReleaseRecord, RepositoryStatus, ScenarioKey,
} from '@/services/types'

export interface RepoSeed {
  id: string
  fullName: string
  description: string
  language: string
  stars: number
  license: string
  topics: string[]
  status: RepositoryStatus
  scenario: ScenarioKey
  lastAnalyzedAt: string | null
  weeklyCommits: number[]
  /** First week start (ISO). Later repos (small samples) start later. */
  firstWeek: string
  authors: AuthorContribution[]
  issueFactor: number
  prFactor: number
  issueP50: number
  issueP75: number
  prP50: number
  prP90: number
  /** Median sample sizes for the 90-day window (scaled for other windows). */
  issueSample: number
  prSample: number
  releases: ReleaseRecord[]
  coverage: Coverage
  issueCoverage: Coverage
  observations: string[]
  activityDelta: number | null
}

const WEEK = 7 * 24 * 3600 * 1000
export const iso = (d: Date) => d.toISOString().slice(0, 10)
export const addDays = (date: string, days: number) => iso(new Date(new Date(date).getTime() + days * 24 * 3600 * 1000))
export const addWeeks = (date: string, weeks: number) => iso(new Date(new Date(date).getTime() + weeks * WEEK))

const authors = (rows: [string, number, boolean][], anonymous = 0): AuthorContribution[] => [
  ...rows.map(([author, commits, isBot]) => ({ author, commits, isBot })),
  ...(anonymous ? [{ author: `${anonymous} 位匿名作者`, commits: 0, isBot: false, anonymous: true }] : []),
]

const release = (tag: string, publishedAt: string, days: number | null, note: string, prerelease = false): ReleaseRecord => ({
  tag, publishedAt, intervalDays: days, note, prerelease,
})

const complete: Coverage = { state: 'complete', label: '采集完整' }

export const REPOSITORIES: RepoSeed[] = [
  {
    id: 'steady-core',
    fullName: 'demo-labs/steady-core',
    description: '事件采集与时间序列聚合的示例仓库，用于演示不同数据密度下的分析界面。',
    language: 'TypeScript',
    stars: 1284,
    license: 'MIT',
    topics: ['time-series', 'analytics', 'demo'],
    status: 'ready',
    scenario: 'active',
    lastAnalyzedAt: '2025-03-31',
    weeklyCommits: [86, 104, 92, 118, 84, 104, 118, 124, 114, 68, 84, 112, 96],
    firstWeek: '2025-01-06',
    authors: authors([['mlchen', 512, false], ['ryan-ops', 318, false], ['dependabot[bot]', 214, true], ['elaine-w', 168, false], ['kenji', 96, false], ['sara-k', 74, false], ['ci-bot', 52, true]], 4),
    issueFactor: 0.164,
    prFactor: 0.109,
    issueP50: 3.4,
    issueP75: 7.1,
    prP50: 1.8,
    prP90: 6.1,
    issueSample: 198,
    prSample: 96,
    releases: [
      release('v2.0.0', '2024-04-18', null, '重写事件采集管线'),
      release('v2.1.0', '2024-06-24', 67, '新增 Issue 耗时分布'),
      release('v2.1.1', '2024-08-05', 42, '修复分页截断'),
      release('v2.2.0', '2024-10-29', 85, '支持 Release 时间轴'),
      release('v2.3.0', '2025-01-14', 77, '比较页同口径校验'),
      release('v2.4.1', '2025-03-18', 63, '导出与数据质量表'),
      release('v2.4.0-rc.1', '2025-02-20', null, '预发布', true),
      release('v2.4.1-rc.1', '2025-03-04', null, '预发布', true),
    ],
    coverage: { state: 'partial', label: '4 个模块中 3 个完整', detail: 'PR 数据部分截断' },
    issueCoverage: complete,
    observations: [
      '近 4 个完整周共记录 378 次提交，较前 4 周（430 次）减少 12%，下降集中在 03-10 至 03-16 当周（68 次）。',
      '窗口内 Issue 关闭耗时中位数 3.4 天（n=198），其中 12 条记录缺少关闭时间，未计入中位数。',
    ],
    activityDelta: -12,
  },
  {
    id: 'grid-lite',
    fullName: 'demo-labs/grid-lite',
    description: '发布节奏稳定的可视化组件集合，Issue 收敛较快。',
    language: 'TypeScript',
    stars: 891,
    license: 'Apache-2.0',
    topics: ['charts', 'components'],
    status: 'ready',
    scenario: 'active',
    lastAnalyzedAt: '2025-03-28',
    weeklyCommits: [58, 64, 51, 70, 62, 66, 72, 58, 63, 55, 60, 62, 59],
    firstWeek: '2025-01-06',
    authors: authors([['hugo-l', 296, false], ['mia', 218, false], ['renovate[bot]', 132, true], ['tao', 108, false], ['lin', 64, false]], 2),
    issueFactor: 0.13,
    prFactor: 0.105,
    issueP50: 2.6,
    issueP75: 5.4,
    prP50: 2.4,
    prP90: 5.9,
    issueSample: 143,
    prSample: 78,
    releases: [
      release('v1.4.0', '2024-05-07', null, '新增柱状图组件'),
      release('v1.5.0', '2024-07-09', 63, '主题令牌'),
      release('v1.6.0', '2024-09-06', 59, '虚拟滚动表格'),
      release('v1.7.0', '2024-11-06', 61, '深色主题'),
      release('v1.8.0', '2025-01-16', 71, '导出能力'),
      release('v1.9.0', '2025-03-18', 61, '日历热力图'),
    ],
    coverage: complete,
    issueCoverage: complete,
    observations: [
      '近 4 个完整周 244 次提交，较前 4 周（243 次）基本持平（+0.4%）。',
      'Issue 关闭耗时中位数 2.6 天（n=143），低于同窗口的对照仓库。',
    ],
    activityDelta: 0,
  },
  {
    id: 'sparse-kit',
    fullName: 'demo-labs/sparse-kit',
    description: '活动稀疏、发布不规律的小型工具库，Issue 数据部分截断。',
    language: 'JavaScript',
    stars: 342,
    license: 'MIT',
    topics: ['utils'],
    status: 'partial',
    scenario: 'partial',
    lastAnalyzedAt: '2025-03-24',
    weeklyCommits: [4, 0, 2, 0, 1, 3, 0, 0, 2, 1, 0, 0, 0],
    firstWeek: '2025-01-06',
    authors: authors([['jules', 6, false], ['dependabot[bot]', 5, true], ['anonymous identity', 2, false]], 3),
    issueFactor: 0.2,
    prFactor: 0.1,
    issueP50: 5.2,
    issueP75: 11.4,
    prP50: 4.1,
    prP90: 9.8,
    issueSample: 38,
    prSample: 22,
    releases: [
      release('v0.9.0', '2024-06-11', null, '小幅重构'),
      release('v0.9.1', '2025-01-08', 211, '依赖升级'),
    ],
    coverage: { state: 'partial', label: '部分数据', detail: '仅采集到 03-24；Issue 第 4 页后截断' },
    issueCoverage: { state: 'partial', label: '部分数据', detail: '仅获取 38 条，无法计算全量积压' },
    observations: ['活动极稀疏：12 个完整周中有 6 周没有提交，样本不足以判断趋势。'],
    activityDelta: null,
  },
  {
    id: 'tiny-lab',
    fullName: 'demo-labs/tiny-lab',
    description: '新仓库，仅 5 周事件，样本量小。',
    language: 'Go',
    stars: 38,
    license: 'MIT',
    topics: ['cli'],
    status: 'ready',
    scenario: 'small',
    lastAnalyzedAt: '2025-03-31',
    weeklyCommits: [2, 1, 0, 3, 1],
    firstWeek: '2025-03-03',
    authors: authors([['kai', 5, false], ['ops-bot', 1, true]], 1),
    issueFactor: 0.4,
    prFactor: 0.2,
    issueP50: 6.0,
    issueP75: 9.0,
    prP50: 3.2,
    prP90: 7.4,
    issueSample: 3,
    prSample: 1,
    releases: [release('v0.1.0', '2025-03-27', null, '首次可用版本')],
    coverage: { state: 'partial', label: '样本较少', detail: '仅 5 周、7 条提交事件' },
    issueCoverage: { state: 'partial', label: '样本较少', detail: 'n=3' },
    observations: ['n=7：仅列出原始记录，不绘制趋势线，也不生成增长结论。'],
    activityDelta: null,
  },
  {
    id: 'docs-site',
    fullName: 'demo-labs/docs-site',
    description: '以文档提交为主，活动集中在周末。',
    language: 'MDX',
    stars: 408,
    license: 'CC-BY-4.0',
    topics: ['docs'],
    status: 'ready',
    scenario: 'quiet',
    lastAnalyzedAt: '2025-03-30',
    weeklyCommits: [12, 8, 15, 9, 11, 7, 14, 10, 13, 6, 9, 12, 8],
    firstWeek: '2025-01-06',
    authors: authors([['writer', 48, false], ['review-bot', 18, true], ['guest', 21, false]], 2),
    issueFactor: 0.08,
    prFactor: 0.09,
    issueP50: 4.7,
    issueP75: 9.2,
    prP50: 2.9,
    prP90: 7.7,
    issueSample: 107,
    prSample: 41,
    releases: [release('v1.0.0', '2024-09-12', null, '文档站上线'), release('v1.1.0', '2025-02-11', 152, '新增 API 章节')],
    coverage: complete,
    issueCoverage: complete,
    observations: ['提交集中在周末，工作日几乎无活动；n=107。'],
    activityDelta: 3,
  },
  {
    id: 'empty-lite',
    fullName: 'demo-labs/empty-lite',
    description: '新建仓库，暂无可分析事件。',
    language: 'Rust',
    stars: 12,
    license: 'MIT',
    topics: [],
    status: 'idle',
    scenario: 'empty',
    lastAnalyzedAt: null,
    weeklyCommits: [],
    firstWeek: '2025-03-24',
    authors: [],
    issueFactor: 0,
    prFactor: 0,
    issueP50: 0,
    issueP75: 0,
    prP50: 0,
    prP90: 0,
    issueSample: 0,
    prSample: 0,
    releases: [],
    coverage: { state: 'missing', label: '尚未分析', detail: '还没有采集任何模块' },
    issueCoverage: { state: 'missing', label: '尚未分析' },
    observations: [],
    activityDelta: null,
  },
  {
    id: 'queue-demo',
    fullName: 'demo-labs/queue-demo',
    description: '采集失败的示例：GitHub API 速率限制。',
    language: 'Go',
    stars: 176,
    license: 'MIT',
    topics: ['queue'],
    status: 'failed',
    scenario: 'failed',
    lastAnalyzedAt: null,
    weeklyCommits: [],
    firstWeek: '2025-03-24',
    authors: [],
    issueFactor: 0,
    prFactor: 0,
    issueP50: 0,
    issueP75: 0,
    prP50: 0,
    prP90: 0,
    issueSample: 0,
    prSample: 0,
    releases: [],
    coverage: { state: 'missing', label: '采集失败', detail: 'GitHub API 速率限制，已采集 3,200 条后暂停' },
    issueCoverage: { state: 'missing', label: '采集失败' },
    observations: [],
    activityDelta: null,
  },
]

export const repoSeed = (id: string) => REPOSITORIES.find((r) => r.id === id)
