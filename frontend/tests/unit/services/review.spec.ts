import { describe, expect, it, vi } from 'vitest'
import { reviewKey, uploadReviewAudio } from '@/services/review'
import { coreHttp, externalHttp } from '@/services/coreApi'

vi.mock('@/services/coreApi', async importOriginal => ({
  ...(await importOriginal<typeof import('@/services/coreApi')>()),
  coreHttp: { post: vi.fn() },
  externalHttp: { put: vi.fn() },
}))

describe('review recording upload', () => {
  it('creates a server-owned grant, uploads without application auth, then confirms', async () => {
    vi.mocked(coreHttp.post)
      .mockResolvedValueOnce({
        data: {
          media_asset_id: 'asset',
          upload_url: 'https://oss.invalid/object',
          headers: { 'Content-Type': 'audio/webm', 'x-oss-forbid-overwrite': 'true' },
        },
      })
      .mockResolvedValueOnce({ data: { uploaded: true } })
    const put = vi.mocked(externalHttp.put).mockResolvedValue({ status: 200 })
    const blob = new Blob(['recording'], { type: 'audio/webm' })
    expect(await uploadReviewAudio(blob, vi.fn())).toBe('asset')
    expect(put).toHaveBeenCalledWith(
      'https://oss.invalid/object',
      blob,
      expect.objectContaining({
        headers: { 'Content-Type': 'audio/webm', 'x-oss-forbid-overwrite': 'true' },
      }),
    )
    expect(coreHttp.post).toHaveBeenLastCalledWith('/media-assets/asset/confirm-upload')
  })

  it('does not confirm an upload that failed', async () => {
    vi.mocked(coreHttp.post).mockResolvedValue({
      data: { media_asset_id: 'asset', upload_url: 'https://oss.invalid/object', headers: {} },
    })
    vi.mocked(externalHttp.put).mockRejectedValue(new Error('offline'))
    await expect(uploadReviewAudio(new Blob(['audio']), vi.fn())).rejects.toThrow('offline')
    expect(coreHttp.post).toHaveBeenCalledTimes(1)
  })

  it('uses UUIDv7 keys accepted by the backend', () => {
    expect(reviewKey()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(new Set(Array.from({ length: 100 }, reviewKey)).size).toBe(100)
  })
})
