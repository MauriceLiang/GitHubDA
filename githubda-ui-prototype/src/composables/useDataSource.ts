import type { RepositoryDataSource } from '@/services/repositoryDataSource'
import { MockRepositoryDataSource } from '@/services/mockRepositoryDataSource'
import { HttpRepositoryDataSource } from '@/services/httpRepositoryDataSource'

let instance: RepositoryDataSource | null = null

/**
 * Single access point for page data.
 *
 * Mock data is opt-in. Normal development and production use the local
 * browser gateway; the internal API key never enters the browser bundle.
 */
export function useDataSource(): RepositoryDataSource {
  if (!instance) {
    instance = import.meta.env.VITE_DATA_MODE === 'mock'
      ? new MockRepositoryDataSource()
      : new HttpRepositoryDataSource()
  }
  return instance
}
