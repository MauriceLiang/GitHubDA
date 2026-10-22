import type {
  CollectionSettings, CommitActivityPage, ComparisonBundle, ComparisonMode, Granularity, ReleaseDetails, RepositoryAnalysis, RepositorySummary,
  FeaturedDatasetImportResult, FeaturedDatasetStatus, IssueOnlineDetail, IssueRecordDetail, IssueRecordPage, PullRequestActivityDetail, PullRequestActivityPage, PullRequestOnlineDetail, ResearchDataset, TaskItem, TimeWindow,
} from './types'

/**
 * The single data boundary of the app.
 *
 * Pages/charts never import data fixtures directly; real and explicit mock
 * modes both implement this interface.
 */
export interface RepositoryDataSource {
  getCollectionSettings(): Promise<CollectionSettings>
  saveCollectionSettings(settings: CollectionSettings): Promise<CollectionSettings>

  listRepositories(): Promise<RepositorySummary[]>
  getFeaturedDatasetStatus(): Promise<FeaturedDatasetStatus>
  importFeaturedDataset(): Promise<FeaturedDatasetImportResult>
  exportFeaturedDataset(): Promise<Blob>
  /** Percent change in commits across two complete four-week windows; null when unavailable or the baseline is zero. */
  getActivityChangePercent(id: string): Promise<number | null>
  searchRepositories(query: string): Promise<(RepositorySummary & { alreadyInLibrary: boolean })[]>
  addRepository(input: string): Promise<{ repositoryId: string; taskId: string | null; existing: boolean }>
  removeRepository(id: string): Promise<void>
  clearRepositoryData(ids: string[], options?: { removeFromLibrary?: boolean }): Promise<void>
  refreshRepository(id: string, options: { scopeKind: 'quick' | 'window'; windowDays: TimeWindow }): Promise<string>

  /**
   * Full analysis bundle for one repository.
   *
   * The browser gateway returns aggregated insight data; unavailable detail
   * fields remain null and are never inferred from totals.
   */
  getAnalysis(id: string, window: TimeWindow, granularity: Granularity): Promise<RepositoryAnalysis>
  getCommitActivity(id: string, page: number, perPage: number, search: string, weekStart?: string): Promise<CommitActivityPage>
  getIssueRecords(id: string, page: number, perPage: number, search: string): Promise<IssueRecordPage>
  getIssueDetail(id: string, issueNumber: number): Promise<IssueRecordDetail>
  getIssueOnlineDetail(id: string, issueNumber: number): Promise<IssueOnlineDetail>
  exportIssueRecords(id: string, search: string): Promise<Blob>
  getPullRequestRecords(id: string, page: number, perPage: number, search: string): Promise<PullRequestActivityPage>
  getPullRequestDetail(id: string, pullNumber: number): Promise<PullRequestActivityDetail>
  getPullRequestOnlineDetail(id: string, pullNumber: number): Promise<PullRequestOnlineDetail>
  exportPullRequestRecords(id: string, search: string): Promise<Blob>
  getReleaseDetails(repositoryId: string, releaseId: string): Promise<ReleaseDetails>

  /** Compare 2–5 repositories using a shared period or each repository's own complete period. */
  getComparison(ids: string[], window: TimeWindow, mode: ComparisonMode): Promise<ComparisonBundle>

  getResearchDataset(id?: string): Promise<ResearchDataset>

  listTasks(): Promise<TaskItem[]>
  retryTask(id: string): Promise<string>
  exportInsights(id: string, windowDays: TimeWindow): Promise<Blob>
  exportComparison(ids: string[], mode: ComparisonMode): Promise<Blob>
  exportRepositories(scope: 'library' | 'research', datasetId?: string): Promise<Blob>
}
