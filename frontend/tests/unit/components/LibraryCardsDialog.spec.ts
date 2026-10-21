import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import LibraryCardsDialog from '@/components/library/LibraryCardsDialog.vue'
import { fetchLibraryCards } from '@/services/content'
import type { DeckView } from '@/stores/decks'

vi.mock('@/services/content', async importOriginal => {
  const actual = await importOriginal<typeof import('@/services/content')>()
  return { ...actual, fetchLibraryCards: vi.fn() }
})

const deck: DeckView = {
  id: '01900000-0000-7000-8000-000000000018',
  name: 'Shared lesson',
  origin: 'core',
  type: 'lesson',
  inMyCourses: false,
  sentenceCount: 31,
  totalCards: 31,
  newCards: 0,
  reviewCards: 0,
  completedCards: 0,
  dueCards: 0,
  children: [],
}

function card(id: string, english: string) {
  return {
    id,
    note_id: id,
    deck_id: deck.id,
    card_template_key: 'sentence_translation',
    card_schedule_revision: 0,
    front: { chinese: '你好。' },
    back: { english },
  }
}

describe('shared library card preview', () => {
  it('shows card text and pages through the whole subtree', async () => {
    vi.mocked(fetchLibraryCards)
      .mockResolvedValueOnce({ data: { cards: [card('first', 'Hello.')], total: 31, limit: 30, offset: 0, scope: 'subtree' } })
      .mockResolvedValueOnce({ data: { cards: [card('last', 'Goodbye.')], total: 31, limit: 30, offset: 30, scope: 'subtree' } })
    const wrapper = mount(LibraryCardsDialog, {
      global: { stubs: { 'el-dialog': { props: ['modelValue'], template: '<section v-if="modelValue"><slot /></section>' } } },
    })
    ;(wrapper.vm as unknown as { show: (value: DeckView) => void }).show(deck)
    await flushPromises()
    expect(fetchLibraryCards).toHaveBeenCalledWith(deck.id, { includeDescendants: true, limit: 30, offset: 0 })
    expect(wrapper.text()).toContain('Hello.')
    expect(wrapper.text()).toContain('你好。')

    await wrapper.get('button[aria-label="下一页"]').trigger('click')
    await flushPromises()
    expect(fetchLibraryCards).toHaveBeenCalledWith(deck.id, { includeDescendants: true, limit: 30, offset: 30 })
    expect(wrapper.text()).toContain('Goodbye.')
    expect(wrapper.text()).not.toContain('Hello.')
    wrapper.unmount()
  })
})
