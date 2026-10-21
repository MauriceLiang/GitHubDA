/**
 * Front-end data model for GitHubDA.
 *
 * These types describe what the UI needs. API payloads are adapted in
 * httpRepositoryDataSource.ts; unavailable backend values stay null.
 */

export type TimeWindow = 30 | 90 | 180
export type Granularity = 'day' | 'week'

/** Demonstration scenarios required by the brief (see docs/DATA_MODELS.md). */
export type ScenarioKey = 'active' | 'quiet' | 'small' | 'partial' | 'empty' | 'failed'

export type RepositoryStatus = 'ready' | 'partial' | 'running' | 'idle' | 'failed'

/** Never render "unknown" as zero — see CoverageNote. */
export interface Coverage {
  state: 'complete' | 'partial' | 'missing'
  label: string
  detail?: string
}

export interface TimePoint {
  /** ISO date, the bucket start (UTC). */
  date: string
  value: number | null
  /** Count observed in this bucket when value is withheld for incomplete coverage. */
  observedValue?: number | null
}

export interface NamedSeries {
  key: string
  label: string
  points: TimePoint[]
}

export interface TimeSeriesResult {
  series: NamedSeries[]
  unit: string
  granularity: Granularity
  window: { start: string | null; end: string | null }
  /** Number of raw records behind the series (not the number of buckets). */
  sampleSize: number | null
  coverage: Coverage
  collectedAt: string | null
  /** Human readable caveat, e.g. "当周尚未完整". */
  limitation?: string
}

export interface Metric {
  id: string
  label: string
  /** null means "unavailable"; the UI renders — with the note. */
  value: number | null
  unit: string
  note: string
  sampleSize?: number
}

export interface MetricSet {
  metrics: Metric[]
  window: { start: string | null; end: string | null }
  collectedAt: string | null
  coverage: Coverage
}

export interface HistogramBucket {
  label: string
  count: number
}

export interface HistogramResult {
  unit: string
  buckets: HistogramBucket[]
  percentiles: { p50: number | null; p75: number | null; p90: number | null }
  sampleSize: number
  coverage: Coverage
  note?: string
}

export interface RepositorySummary {
  /** Backend repository ID used in routes. */
  id: string
  fullName: string
  description: string | null
  language: string | null
  stars: number | null
  /** Repository profile values from the latest GitHub snapshot. */
  forks?: number | null
  license: string | null
  topics: string[]
  createdAt?: string | null
  pushedAt?: string | null
  archived?: boolean | null
  sizeKb?: number | null
  /** GitHub's open_issues_count includes both Issues and pull requests. */
  openIssuesAndPrCount?: number | null
  status: RepositoryStatus
  lastAnalyzedAt: string | null
  /** % change of last 4 complete weeks vs previous 4; null when not comparable. */
  activityDelta: number | null
  scenario?: ScenarioKey
  htmlUrl?: string
  alreadyInLibrary?: boolean
}

export interface CommitEvent {
  sha: string
  title: string
  author: string
  isBot: boolean
  anonymous?: boolean
  date: string
  url?: string
}

export interface CommitActivityPage {
  items: CommitEvent[]
  page: number
  perPage: number
  total: number
  available: boolean
  coverage: Coverage
  note: string
  windowStart: string | null
  windowEnd: string | null
  commitCount: number
  authorCount: number
  dailyCounts: { date: string; count: number }[]
  authors: AuthorContribution[]
}

export interface IssueRecord {
  number: number
  title: string
  createdAt: string | null
  closedAt: string
  durationDays: number | null
  state: 'closed'
  url?: string
}

export interface IssueRecordDetail extends IssueRecord {
  body: string | null
  commentsCount: number
}

export interface IssueComment {
  author: string
  body: string
  createdAt: string | null
}

export interface IssueOnlineDetail {
  number: number
  title: string
  createdAt: string | null
  closedAt: string | null
  url?: string
  body: string | null
  state: 'open' | 'closed'
  author: string | null
  labels: string[]
  updatedAt: string | null
  source: 'github' | 'mock'
  commentsCount: number
  comments: IssueComment[]
  commentsComplete: boolean
  commentsError: string | null
}

export interface IssueRecordPage {
  items: IssueRecord[]
  page: number
  perPage: number
  total: number
  available: boolean
  coverage: Coverage
  note: string
  windowStart: string | null
  windowEnd: string | null
}

export interface PullRequestActivityRecord {
  number: number
  title: string
  createdAt: string | null
  closedAt: string | null
  mergedAt: string | null
  durationDays: number | null
  state: 'closed' | 'merged'
  draft: boolean
  commentsCount: number
  url?: string
}

export interface PullRequestActivityDetail extends PullRequestActivityRecord {
  body: string | null
}

export interface PullRequestOnlineDetail {
  number: number
  title: string
  body: string | null
  state: 'open' | 'closed' | 'merged'
  author: string | null
  labels: string[]
  createdAt: string | null
  closedAt: string | null
  mergedAt: string | null
  updatedAt: string | null
  url?: string
  commentsCount: number
  comments: IssueComment[]
  commentsComplete: boolean
  commentsError: string | null
}

export interface PullRequestActivityPage {
  items: PullRequestActivityRecord[]
  page: number
  perPage: number
  total: number
  available: boolean
  coverage: Coverage
  note: string
  windowStart: string | null
  windowEnd: string | null
}

export interface PullRequestRecord {
  number: number
  title: string
  createdAt: string
  mergedAt: string | null
  durationDays: number | null
  state: 'open' | 'merged' | 'closed'
  comments: number
  url?: string
}

export interface ReleaseRecord {
  tag: string
  identifierType?: 'tag' | 'release_id'
  publishedAt: string
  prerelease: boolean
  intervalDays: number | null
  note: string
  url?: string
}

export interface ReleaseDetails {
  name: string | null
  body: string | null
}

export interface AuthorContribution {
  author: string
  commits: number
  isBot: boolean
  anonymous?: boolean
}

export interface Observation {
  id: string
  text: string
  evidence: string
}

export interface RepositoryAnalysis {
  repository: RepositorySummary
  metrics: MetricSet
  /** Weekly commit series (main chart). */
  commits: TimeSeriesResult
  /** Daily series used by the calendar heatmap (independent of granularity). */
  dailyCommits: TimeSeriesResult
  issues: TimeSeriesResult
  issueDuration: HistogramResult
  /** null when the open-issue set was not fully collected. */
  openIssueAges: { label: string; count: number }[] | null
  pullRequests: TimeSeriesResult
  prDuration: HistogramResult
  longOpenPrs: PullRequestRecord[]
  releases: ReleaseRecord[]
  releaseIntervals: { tag: string; days: number }[]
  authors: AuthorContribution[]
  coverage: Coverage
  collectedAt: string | null
  observations: Observation[]
}

export interface ComparisonEntry {
  id: string
  label: string
  color: string
  points: TimePoint[]
  coverage: Coverage
  collectedAt: string
  issueP50: number | null
  issueSample: number
  prP50: number | null
  prSample: number
  releaseMedianDays: number | null
}

export interface ComparisonBundle {
  window: { start: string; end: string }
  entries: ComparisonEntry[]
  notes: string[]
}

export interface ResearchGroup {
  label: string
  count: number
  medianCloseDays: number | null
  p25: number | null
  p75: number | null
}

export interface ResearchScatterPoint {
  repository: string
  issueCloseDays: number
  prMergeDays: number
  group: string
}

export interface ResearchDataset {
  id: string
  name: string
  exploratory: boolean
  samplingSource: string
  samplingRule: string
  frozenAt: string | null
  eventWindow: { start: string | null; end: string | null }
  repositoryCount: number
  eventCount: number | null
  missingRate: number | null
  issueMedianDays: number | null
  issueSample: number
  prMedianDays: number | null
  prSample: number
  groups: ResearchGroup[]
  scatter: {
    points: ResearchScatterPoint[]
    spearman: number | null
    sampleSize: number
    pValue: number | null
    note: string
  }
  quality: { field: string; missingRate: number; collected: boolean }[]
  limitations: string[]
}

export type TaskStatus = 'queued' | 'running' | 'analyzing' | 'done' | 'partial' | 'failed' | 'cancelled'

export interface TaskItem {
  id: string
  repository: string
  repositoryId?: number
  module: string
  status: TaskStatus
  stage: string
  progressPercent?: number | null
  progressKind?: 'stages' | 'unknown'
  processed?: number
  total?: number
  updatedAt: string
  error?: string
}

export interface CollectionSettings {
  githubMaxPages: number
}

export interface DefinitionEntry {
  metricId: string
  title: string
  definition: string
  source: string
  limitation: string
}
