import type {
  CollectionSettings, CommitActivityPage, ComparisonBundle, Granularity, ReleaseDetails, RepositoryAnalysis, RepositorySummary,
  IssueOnlineDetail, IssueRecordDetail, IssueRecordPage, PullRequestActivityDetail, PullRequestActivityPage, PullRequestOnlineDetail, ResearchDataset, TaskItem, TimeWindow,
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
  searchRepositories(query: string): Promise<(RepositorySummary & { alreadyInLibrary: boolean })[]>
  addRepository(input: string): Promise<{ repositoryId: string; taskId: string | null; existing: boolean }>
  removeRepository(id: string): Promise<void>
  refreshRepository(id: string): Promise<string>

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

  /** 2–5 repositories compared with a shared window and definitions. */
  getComparison(ids: string[], window: TimeWindow): Promise<ComparisonBundle>

  getResearchDataset(id?: string): Promise<ResearchDataset>

  listTasks(): Promise<TaskItem[]>
  retryTask(id: string): Promise<string>
  exportInsights(id: string): Promise<Blob>
  exportComparison(ids: string[]): Promise<Blob>
  exportRepositories(scope: 'library' | 'research', datasetId?: string): Promise<Blob>
}
