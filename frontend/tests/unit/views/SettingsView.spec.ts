import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { mountWithApp } from '../../helpers/mountWithApp'
import SettingsView from '@/views/SettingsView.vue'
import { useSettingsStore } from '@/stores/settings'

async function render(settings: Record<string, unknown> = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/settings', component: SettingsView }] })
  await router.push('/settings?deck_id=17')
  const wrapper = mountWithApp(SettingsView, {
    pinia: { initialState: { settings: {
      deckId: 17, deckTitle: 'Lesson 1', dailyNewLimit: 20, dailyReviewLimit: 200,
      newCardGatherOrder: null, newCardSortOrder: null,
      effectiveNewCardGatherOrder: 'random_cards', effectiveNewCardSortOrder: 'order_gathered',
      ...settings,
    } } },
    global: { plugins: [router] },
  })
  return { wrapper, store: useSettingsStore() }
}

describe('deck new-card order settings', () => {
  it('keeps inherited order on unrelated saves and explicitly selects textbook order', async () => {
    const { wrapper, store } = await render()
    expect(store.load).toHaveBeenCalledWith(17)
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
