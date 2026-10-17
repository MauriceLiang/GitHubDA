import { afterEach, describe, expect, it, vi } from 'vitest'
import { httpService } from './http'

afterEach(() => vi.unstubAllGlobals())

describe('HTTP service', () => {
  it('does not send the UI all-filter as an API task status', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: 'csrf-token' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { items: [] } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(httpService.listTasks('all')).resolves.toEqual([])
    expect(fetchMock.mock.calls[1][0]).toBe('/api/browser/v1/tasks?per_page=100')
  })

  it('treats a successful 204 delete as success without parsing JSON', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: 'csrf-token' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(httpService.remove(321)).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[1][0]).toBe('/api/browser/v1/library/repositories/321')
    expect(fetchMock.mock.calls[1][1].headers.get('X-CSRF-Token')).toBe('csrf-token')
  })
})
