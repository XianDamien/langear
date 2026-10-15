import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchSettings, saveSettings } from '@/services/api/settings'

const { get, put } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('@/services/http', () => ({ default: { get, put } }))

const backend = {
  desired_retention: 0.92, learning_steps: [1, 15], relearning_steps: [10],
  maximum_interval: 1000, default_source_scope: [1, 2],
}
const frontend = {
  desiredRetention: 0.92, learningSteps: '1,15', relearningSteps: '10',
  maximumInterval: 1000, defaultSourceScope: '1,2',
}

describe('existing settings API contract', () => {
  beforeEach(() => {
    get.mockResolvedValue({ data: backend })
    put.mockResolvedValue({ data: backend })
  })

  it('loads the fields actually returned by production', async () => {
    expect((await fetchSettings()).data).toEqual(frontend)
    expect(get).toHaveBeenCalledWith('/settings')
  })

  it('saves supported settings without obsolete daily-limit fields', async () => {
    expect((await saveSettings(frontend)).data).toEqual(frontend)
    expect(put).toHaveBeenCalledWith('/settings', backend)
  })

  it('allows empty steps and source scope', async () => {
    await saveSettings({ ...frontend, learningSteps: '', relearningSteps: '', defaultSourceScope: '' })
    expect(put).toHaveBeenCalledWith('/settings', {
      ...backend, learning_steps: [], relearning_steps: [], default_source_scope: [],
    })
  })

  it('loads and saves only the selected deck without changing account defaults', async () => {
    const scoped = { ...backend, deck_id: 18, deck_title: 'Lesson', daily_new_limit: 3, daily_review_limit: 7 }
    get.mockResolvedValue({ data: scoped })
    put.mockResolvedValue({ data: scoped })
    const { data } = await fetchSettings(18)
    expect(get).toHaveBeenCalledWith('/settings?deck_id=18')
    expect(data).toMatchObject({ deckId: 18, deckTitle: 'Lesson', dailyNewLimit: 3 })
    await saveSettings(data)
    expect(put).toHaveBeenCalledWith('/settings?deck_id=18', {
      desired_retention: 0.92, learning_steps: [1, 15], relearning_steps: [10],
      maximum_interval: 1000, daily_new_limit: 3, daily_review_limit: 7,
    })
  })

  it.each([0, -1, 1.5, Number.NaN])('rejects invalid deck %s', async id => {
    await expect(fetchSettings(id)).rejects.toThrow('无效的课程')
    expect(get).not.toHaveBeenCalled()
  })

  it.each([-1, 10001, 1.5, undefined])('rejects invalid deck limits %s', async dailyNewLimit => {
    await expect(saveSettings({ ...frontend, deckId: 18, dailyNewLimit, dailyReviewLimit: 7 })).rejects.toThrow()
    expect(put).not.toHaveBeenCalled()
  })

  it.each(['abc', '1,wrong', '0', '-2', '1.5', '1,,2'])('rejects invalid list %s before sending', async value => {
    await expect(saveSettings({ ...frontend, learningSteps: value })).rejects.toThrow()
    expect(put).not.toHaveBeenCalled()
  })

  it.each([0, 1, -0.5, Number.NaN])('rejects invalid retention %s', async desiredRetention => {
    await expect(saveSettings({ ...frontend, desiredRetention })).rejects.toThrow()
    expect(put).not.toHaveBeenCalled()
  })
})
