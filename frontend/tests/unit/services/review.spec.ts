import { describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { reviewKey, uploadReviewAudio } from '@/services/review'
import { libraryContent } from '@/services/libraryContent'
vi.mock('@/services/libraryContent', () => ({ libraryContent: { post: vi.fn() } }))
describe('review recording upload', () => {
  it('creates a server-owned grant, uploads without application auth, then confirms', async () => {
    vi.mocked(libraryContent.post).mockResolvedValueOnce({ data: { media_asset_id: 'asset', upload_url: 'https://oss.invalid/object', headers: { 'Content-Type': 'audio/webm', 'x-oss-forbid-overwrite': 'true' } } }).mockResolvedValueOnce({ data: { uploaded: true } })
    const put = vi.spyOn(axios, 'put').mockResolvedValue({ status: 200 })
    const blob = new Blob(['recording'], { type: 'audio/webm' })
    expect(await uploadReviewAudio(blob, vi.fn())).toBe('asset')
    expect(put).toHaveBeenCalledWith('https://oss.invalid/object', blob, expect.objectContaining({ headers: { 'Content-Type': 'audio/webm', 'x-oss-forbid-overwrite': 'true' } }))
    expect(libraryContent.post).toHaveBeenLastCalledWith('/media-assets/asset/confirm-upload')
  })
  it('does not confirm an upload that failed', async () => {
    vi.mocked(libraryContent.post).mockResolvedValue({ data: { media_asset_id: 'asset', upload_url: 'https://oss.invalid/object', headers: {} } })
    vi.spyOn(axios, 'put').mockRejectedValue(new Error('offline'))
    await expect(uploadReviewAudio(new Blob(['audio']), vi.fn())).rejects.toThrow('offline')
    expect(libraryContent.post).toHaveBeenCalledTimes(1)
  })
  it('uses UUIDv7 keys accepted by the backend', () => {
    expect(reviewKey()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(new Set(Array.from({ length: 100 }, reviewKey)).size).toBe(100)
  })
})
