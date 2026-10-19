import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchSettings, saveSettings } from '@/services/api/settings'

const { get, put, coreGet, corePut } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), coreGet: vi.fn(), corePut: vi.fn() }))
vi.mock('@/services/libraryContent', () => ({ libraryContent: { get: coreGet, put: corePut } }))
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
    const id = '01900000-0000-7000-8000-000000000018'
    coreGet.mockImplementation(async (path: string) => ({ data: path === '/review/legacy-lessons/18' ? { deck_id: id } : { ...scoped, deck_id: id } }))
    corePut.mockResolvedValue({ data: { ...scoped, deck_id: id } })
    const { data } = await fetchSettings(18)
    expect(coreGet).toHaveBeenCalledWith('/review/legacy-lessons/18')
    expect(coreGet).toHaveBeenCalledWith('/decks/01900000-0000-7000-8000-000000000018/settings')
    expect(get).not.toHaveBeenCalled()
    expect(data).toMatchObject({ deckId: 18, deckTitle: 'Lesson', dailyNewLimit: 3 })
    await saveSettings(data)
    expect(corePut).toHaveBeenCalledWith('/decks/01900000-0000-7000-8000-000000000018/settings', {
      desired_retention: 0.92, learning_steps: [1, 15], relearning_steps: [10],
      maximum_interval: 1000, daily_new_limit: 3, daily_review_limit: 7,
    })
  })

  it('loads and saves UUID deck preferences through the content API only', async () => {
    const id = '01900000-0000-7000-8000-000000000001'
    const scoped = { ...backend, deck_id: id, deck_title: '自建词汇', daily_new_limit: 7, daily_review_limit: 45, scheduling_enabled: false }
    coreGet.mockResolvedValue({ data: scoped })
    corePut.mockResolvedValue({ data: scoped })
    const { data } = await fetchSettings(id)
    expect(coreGet).toHaveBeenCalledWith(`/decks/${id}/settings`)
    expect(data.schedulingEnabled).toBe(false)
    await saveSettings(data)
    expect(corePut).toHaveBeenCalledWith(`/decks/${id}/settings`, expect.objectContaining({ daily_new_limit: 7 }))
    expect(get).not.toHaveBeenCalled()
    expect(put).not.toHaveBeenCalled()
  })

  it('maps effective order separately and saves inheritance to the resolved legacy deck', async () => {
    const id = '01900000-0000-7000-8000-000000000017'
    const scoped = {
      ...backend, deck_id: id, daily_new_limit: 3, daily_review_limit: 7,
      new_card_gather_order: 'lowest_position', new_card_sort_order: 'order_gathered',
      new_card_order_overrides: { new_card_gather_order: null, new_card_sort_order: null },
    }
    coreGet.mockImplementation(async (path: string) => ({ data: path === '/review/legacy-lessons/17' ? { deck_id: id } : scoped }))
    corePut.mockResolvedValue({ data: scoped })
    const { data } = await fetchSettings(17)
    expect(data).toMatchObject({ deckId: 17, newCardGatherOrder: null, newCardSortOrder: null, effectiveNewCardGatherOrder: 'lowest_position' })
    await saveSettings(data)
    expect(corePut).toHaveBeenLastCalledWith(`/decks/${id}/settings`, expect.objectContaining({ new_card_gather_order: null, new_card_sort_order: null }))
    await saveSettings({ ...data, newCardGatherOrder: 'lowest_position', newCardSortOrder: 'order_gathered' })
    expect(corePut).toHaveBeenLastCalledWith(`/decks/${id}/settings`, expect.objectContaining({ new_card_gather_order: 'lowest_position', new_card_sort_order: 'order_gathered' }))
    expect(put).not.toHaveBeenCalled()
  })

  it('does not send order fields to legacy account settings', async () => {
    await saveSettings({ ...frontend, newCardGatherOrder: 'lowest_position', newCardSortOrder: 'order_gathered' })
    expect(put).toHaveBeenCalledWith('/settings', backend)
  })

  it('rejects settings returned for a different imported deck' , async () => {
    coreGet.mockResolvedValueOnce({ data: { deck_id: '01900000-0000-7000-8000-000000000018' } })
      .mockResolvedValueOnce({ data: { ...backend, deck_id: '01900000-0000-7000-8000-000000000019' } })
    await expect(fetchSettings(18)).rejects.toThrow('牌组设置未正确返回')
  })

  it('fails closed when an old lesson has not been imported', async () => {
    coreGet.mockRejectedValueOnce(new Error('not imported'))
    await expect(fetchSettings(42)).rejects.toThrow('not imported')
    expect(get).not.toHaveBeenCalled()
    expect(put).not.toHaveBeenCalled()
  })

  it('rejects malformed UUIDs without falling back to account settings', async () => {
    await expect(fetchSettings('invalid')).rejects.toThrow('无效的牌组')
    expect(get).not.toHaveBeenCalled()
    expect(coreGet).not.toHaveBeenCalled()
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
