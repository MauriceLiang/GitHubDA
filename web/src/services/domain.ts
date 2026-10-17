export type Depth = 'basic' | 'deep'
export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'partial' | 'failed' | 'cancelled'
export type AnalysisStatus = 'not_started' | 'queued' | 'processing' | 'completed' | 'partial' | 'failed'
export type DataStatus = 'missing' | 'fresh' | 'stale'
export type Coverage = 'complete' | 'partial' | 'not_collected' | 'unknown'

export interface Metrics {
  stars: number | null
  forks: number | null
  commits90d: number | null
  issuesClosed90d: number | null
  prsMerged90d: number | null
  releases365d: number | null
  ageDays: number | null
  daysSincePush: number | null
}

export interface Repository {
  repositoryId: number
  fullName: string
  htmlUrl: string
  description: string | null
  language: string | null
  stars: number | null
  forks: number | null
  archived: boolean
  analysisStatus: AnalysisStatus
  dataStatus: DataStatus
  lastCollectedAt: string | null
  alreadyInLibrary?: boolean
  topics?: string[]
  license?: string | null
  metadata?: { coverage: Coverage; collectedAt: string | null; notes: string[] } | null
  metrics?: Metrics | null
  trend?: Array<{ date: string; value: number }>
}

export interface RepositoryAnalysis {
  status: AnalysisStatus
  metrics: Metrics | null
  coverage: Coverage
  limitations: string[]
  source: { collectedAt: string | null; windowStart: string | null; windowEnd: string | null } | null
}

export interface TaskModule {
  name: string
  status: string
  coverage: Coverage
}

export interface Task {
  taskId: string
  repositoryId: number
  depth: Depth
  status: TaskStatus
  phase: string | null
  progressPercent: number | null
  progressKind: 'stages' | 'unknown'
  message: string | null
  createdAt: string
  etaSeconds: number | null
  modules: TaskModule[]
  retryOf?: string | null
}

export interface Overview {
  total: number
  analyzed: number
  active: number
  latestCollection: string | null
  recentRepositories: Repository[]
  recentTasks: Task[]
}

export interface Dataset {
  datasetId: string
  name: string
  type: 'research' | 'library' | 'featured'
  sampleSize: number
  frozenAt: string | null
  rulesVersion: string | null
}

export interface ResearchResult {
  datasetId: string
  groupBy: string
  validSampleSize: number
  summary: Record<string, { count: number; mean: number | null; median: number | null; std: number | null }>
  groups: Array<{ group: string; n: number; starsMedian: number | null; forksMedian: number | null; recentlyPushed90dPct: number | null }>
  correlations: Array<{ x: string; y: string; method: string; n: number; coefficient: number | null; pValue: number | null; note: string | null }>
}

export interface DataQuality {
  datasetId: string
  recordsTotal: number
  recordsAnalyzable: number
  missingFields: Array<{ field: string; count: number; rate: number | null }>
  excludedByReason: Array<{ reason: string; count: number }>
  staleCount: number
  rulesVersion: string | null
  coverageNotes: string[]
}

export interface Comparison {
  repositories: Array<{ repositoryId: number; fullName: string; metrics: Metrics; coverage: Coverage; source?: { profileCollectedAt: string | null; analysisCollectedAt: string | null; analysisDepth: Depth; windowStart: string | null; windowEnd: string | null } }>
  basis: { depth: Depth; metricWindow: string; sameProjectType: boolean; warnings: string[] }
}

export interface RepositoryFilters {
  query?: string
  language?: string
  status?: string
  sort?: 'name' | 'stars' | 'last_collected'
  order?: 'asc' | 'desc'
}

export interface RepositoryService {
  overview(): Promise<Overview>
  listRepositories(filters?: RepositoryFilters): Promise<Repository[]>
  searchRepositories(query: string, language?: string): Promise<Repository[]>
  addAndAnalyze(input: string): Promise<{ repositoryId: number; taskId: string | null; existing: boolean }>
  repositoryDetail(repositoryId: number): Promise<Repository>
  repositoryAnalysis(repositoryId: number, depth: Depth): Promise<RepositoryAnalysis>
  repositorySeries(repositoryId: number, metric: 'stars' | 'forks'): Promise<Array<{ date: string; value: number }>>
  refresh(repositoryId: number, depth: Depth): Promise<Task>
  remove(repositoryId: number): Promise<void>
  compare(repositoryIds: number[], depth: Depth): Promise<Comparison>
  exportCsv(scope: 'library' | 'research', datasetId?: string): Promise<Blob>
  exportComparison(repositoryIds: number[], depth: Depth): Promise<Blob>
  listTasks(status?: string): Promise<Task[]>
  retryTask(taskId: string): Promise<Task>
  listDatasets(): Promise<Dataset[]>
  researchStatistics(datasetId: string, groupBy: 'language' | 'star_tier' | 'age_tier', language?: string): Promise<ResearchResult>
  researchQuality(datasetId: string): Promise<DataQuality>
  resetMock?(): void
}
