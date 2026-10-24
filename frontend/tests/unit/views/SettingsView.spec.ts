import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { mountWithApp } from '../../helpers/mountWithApp'
import SettingsView from '@/views/SettingsView.vue'
import { useSettingsStore } from '@/stores/settings'

const deckId = '01900000-0000-7000-8000-000000000017'

async function render(settings: Record<string, unknown> = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/settings', component: SettingsView }] })
  await router.push(`/settings?deck_id=${deckId}`)
  const wrapper = mountWithApp(SettingsView, {
    pinia: { initialState: { settings: {
      deckId, deckTitle: 'Lesson 1', dailyNewLimit: 9999, dailyReviewLimit: 200,
      newCardGatherOrder: null, newCardSortOrder: null,
      effectiveNewCardGatherOrder: 'random_cards', effectiveNewCardSortOrder: 'order_gathered',
      ...settings,
    } } },
    global: { plugins: [router] },
  })
  return { wrapper, store: useSettingsStore() }
}

async function renderCollection(settings: Record<string, unknown> = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/settings', component: SettingsView }] })
  await router.push('/settings')
  const wrapper = mountWithApp(SettingsView, {
    pinia: { initialState: { settings: {
      dailyNewLimit: 9999, dailyReviewLimit: 200, desiredRetention: 0.9, learningSteps: '15', relearningSteps: '15',
      maximumInterval: 36500, defaultDeckScope: '',
      ...settings,
    } } },
    global: { plugins: [router] },
  })
  return { wrapper, store: useSettingsStore() }
}

describe('account new-card quota settings', () => {
  it('shows and saves the account-level new-card quota', async () => {
    const { wrapper, store } = await renderCollection()
    expect(store.load).toHaveBeenCalledWith(undefined)
    expect(wrapper.get<HTMLInputElement>('#daily-new-limit').element.value).toBe('9999')
    expect(wrapper.get<HTMLInputElement>('#daily-review-limit').element.value).toBe('200')
    await wrapper.get('#daily-new-limit').setValue('12000')
    await wrapper.get('form').trigger('submit')
    expect(store.dailyNewLimit).toBe(12000)
    expect(store.save).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})

describe('deck new-card order settings', () => {
  it('keeps inherited order on unrelated saves and explicitly selects textbook order', async () => {
    const { wrapper, store } = await render()
    expect(store.load).toHaveBeenCalledWith(deckId)
    expect(wrapper.get<HTMLSelectElement>('#new-card-order').element.value).toBe('inherit')
    expect(wrapper.text()).toContain('当前生效：随机')
    expect(wrapper.find('#learning-steps').exists()).toBe(false)
    await wrapper.get('form').trigger('submit')
    expect(store.newCardGatherOrder).toBeNull()
    await wrapper.get('#new-card-order').setValue('source')
    expect(store.newCardGatherOrder).toBe('lowest_position')
    expect(store.newCardSortOrder).toBe('order_gathered')
    await wrapper.get('form').trigger('submit')
    expect(store.save).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('preserves custom order until the learner chooses a replacement', async () => {
    const { wrapper, store } = await render({ newCardGatherOrder: 'highest_position', newCardSortOrder: 'template' })
    expect(wrapper.get<HTMLSelectElement>('#new-card-order').element.value).toBe('custom')
    await wrapper.get('form').trigger('submit')
    expect(store.newCardGatherOrder).toBe('highest_position')
    expect(store.newCardSortOrder).toBe('template')
    await wrapper.get('#new-card-order').setValue('random')
    expect(store.newCardGatherOrder).toBe('random_cards')
    expect(store.newCardSortOrder).toBe('order_gathered')
    await wrapper.get('#new-card-order').setValue('inherit')
    expect(store.newCardGatherOrder).toBeNull()
    expect(store.newCardSortOrder).toBeNull()
    wrapper.unmount()
  })
})
