import { describe, expect, it, vi } from 'vitest'
import { fetchMyCourseCards, updateMyCourseCards, fetchMyCourseLessons, updateMyCourseLessons } from '@/services/api/decks'
import { reviewHttp } from '@/services/review'
import http from '@/services/http'
vi.mock('@/services/review', () => ({ reviewHttp: { get: vi.fn(), put: vi.fn() } }))
vi.mock('@/services/http', () => ({ default: { get: vi.fn(), put: vi.fn() } }))

describe('legacy picker shares Review storage', () => {
  it('routes course membership and card selections exclusively to Review', async () => {
    await fetchMyCourseLessons()
    await updateMyCourseLessons([42])
    await fetchMyCourseCards('42')
    await updateMyCourseCards('42', [])
    await updateMyCourseCards('42', null)
    expect(reviewHttp.get).toHaveBeenCalledWith('/review/legacy-lessons')
    expect(reviewHttp.put).toHaveBeenCalledWith('/review/legacy-lessons', { lesson_ids: [42] })
    expect(reviewHttp.get).toHaveBeenCalledWith('/review/legacy-lessons/42/study-selection')
    expect(reviewHttp.put).toHaveBeenCalledWith('/review/legacy-lessons/42/study-selection', { card_ids: [] })
    expect(reviewHttp.put).toHaveBeenCalledWith('/review/legacy-lessons/42/study-selection', { card_ids: null })
    expect(http.get).not.toHaveBeenCalled()
    expect(http.put).not.toHaveBeenCalled()
  })
})
