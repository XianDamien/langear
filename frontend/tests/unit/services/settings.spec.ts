import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchSettings, saveSettings } from '@/services/api/settings'

const { get, put } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('@/services/coreApi', async importOriginal => ({
  ...(await importOriginal<typeof import('@/services/coreApi')>()),
  coreHttp: { get, put },
}))

const deckScope = [
  '01900000-0000-7000-8000-000000000001',
  '01900000-0000-7000-8000-000000000002',
]

const collection = {
  desired_retention: 0.92,
  new_limit: 9999,
  learning_steps: [1, 15],
  relearning_steps: [10],
  maximum_review_interval: 1000,
  default_deck_scope: deckScope,
}
const frontend = {
  dailyNewLimit: 9999,
  desiredRetention: 0.92,
  learningSteps: '1,15',
  relearningSteps: '10',
  maximumInterval: 1000,
  defaultDeckScope: deckScope.join(','),
}

const deckId = '01900000-0000-7000-8000-000000000018'
const deckSettings = {
  deck_id: deckId,
  deck_title: 'Lesson',
  scheduling_enabled: true,
  new_card_order_overrides: { new_card_gather_order: null, new_card_sort_order: null },
  daily_new_limit: 3,
  daily_review_limit: 7,
  desired_retention: 0.92,
  maximum_interval: 1000,
  learning_steps: [1, 15],
  relearning_steps: [10],
  new_card_gather_order: 'lowest_position',
  new_card_sort_order: 'order_gathered',
}

describe('core settings API contract', () => {
  beforeEach(() => {
    get.mockResolvedValue({ data: collection })
    put.mockResolvedValue({ data: collection })
  })

  it('loads and saves Collection settings through /settings', async () => {
    expect((await fetchSettings()).data).toEqual(frontend)
    expect(get).toHaveBeenCalledWith('/settings')
    expect((await saveSettings(frontend)).data).toEqual(frontend)
    expect(put).toHaveBeenCalledWith('/settings', collection)
  })

  it('allows empty steps and deck scope', async () => {
    await saveSettings({ ...frontend, learningSteps: '', relearningSteps: '', defaultDeckScope: '' })
    expect(put).toHaveBeenCalledWith('/settings', {
      ...collection, learning_steps: [], relearning_steps: [], default_deck_scope: [],
    })
  })

  it('loads and saves a deck without touching account defaults', async () => {
    get.mockResolvedValue({ data: deckSettings })
    put.mockResolvedValue({ data: deckSettings })
    const { data } = await fetchSettings(deckId)
    expect(get).toHaveBeenCalledWith(`/decks/${deckId}/settings`)
    expect(data).toMatchObject({
      deckId,
      deckTitle: 'Lesson',
      dailyNewLimit: 3,
      newCardGatherOrder: null,
      effectiveNewCardGatherOrder: 'lowest_position',
    })
    await saveSettings(data)
    expect(put).toHaveBeenCalledWith(`/decks/${deckId}/settings`, expect.objectContaining({
      daily_new_limit: 3,
      daily_review_limit: 7,
      desired_retention: 0.92,
      learning_steps: [1, 15],
      relearning_steps: [10],
      maximum_interval: 1000,
    }))
  })

  it('sends explicit order overrides and preserves inheritance', async () => {
    get.mockResolvedValue({ data: deckSettings })
    put.mockResolvedValue({ data: deckSettings })
    const { data } = await fetchSettings(deckId)
    await saveSettings({ ...data, newCardGatherOrder: null, newCardSortOrder: null })
    expect(put).toHaveBeenLastCalledWith(`/decks/${deckId}/settings`, expect.objectContaining({
      new_card_gather_order: null,
      new_card_sort_order: null,
    }))
  })

  it('does not send deck order fields to Collection settings', async () => {
    await saveSettings({ ...frontend, newCardGatherOrder: 'lowest_position', newCardSortOrder: 'order_gathered' })
    expect(put).toHaveBeenCalledWith('/settings', collection)
  })

  it('rejects settings returned for a different deck', async () => {
    get.mockResolvedValueOnce({ data: { ...deckSettings, deck_id: '01900000-0000-7000-8000-000000000019' } })
    await expect(fetchSettings(deckId)).rejects.toThrow('牌组设置未正确返回')
  })

  it('rejects malformed UUIDs without falling back to account settings', async () => {
    await expect(fetchSettings('invalid')).rejects.toThrow('无效的牌组')
    expect(get).not.toHaveBeenCalled()
  })

  it.each([-1, 10001, 1.5, undefined])('rejects invalid deck limits %s', async dailyNewLimit => {
    await expect(saveSettings({ ...frontend, deckId, dailyNewLimit, dailyReviewLimit: 7 })).rejects.toThrow()
    expect(put).not.toHaveBeenCalled()
  })

  it.each([-1, 10001, 1.5, undefined])('rejects invalid collection new limit %s', async dailyNewLimit => {
    await expect(saveSettings({ ...frontend, dailyNewLimit })).rejects.toThrow()
    expect(put).not.toHaveBeenCalled()
  })

  it.each(['abc', '1,wrong', '0', '-2', '1.5', '1,,2'])('rejects invalid list %s before sending', async value => {
    await expect(saveSettings({ ...frontend, learningSteps: value })).rejects.toThrow()
    expect(put).not.toHaveBeenCalled()
  })

  it.each(['abc', deckScope[0] + ',invalid'])('rejects invalid deck scope %s before sending', async value => {
    await expect(saveSettings({ ...frontend, defaultDeckScope: value })).rejects.toThrow()
    expect(put).not.toHaveBeenCalled()
  })

  it.each([0, 1, -0.5, Number.NaN])('rejects invalid retention %s', async desiredRetention => {
    await expect(saveSettings({ ...frontend, desiredRetention })).rejects.toThrow()
    expect(put).not.toHaveBeenCalled()
  })
})
