import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CardPickerModal from '@/components/library/CardPickerModal.vue'
import { fetchAllLibraryCards, fetchLibrarySelection, importLibraryDeck } from '@/services/content'
import type { DeckView } from '@/stores/decks'

vi.mock('@/services/content', async importOriginal => {
  const actual = await importOriginal<typeof import('@/services/content')>()
  return {
    ...actual,
    fetchAllLibraryCards: vi.fn(),
    fetchLibrarySelection: vi.fn(),
    importLibraryDeck: vi.fn(),
  }
})

const deck: DeckView = {
  id: '01900000-0000-7000-8000-000000000018',
  name: 'Shared lesson',
  origin: 'core',
  type: 'lesson',
  inMyCourses: false,
  sentenceCount: 2,
  totalCards: 2,
  newCards: 0,
  reviewCards: 0,
  completedCards: 0,
  dueCards: 0,
  children: [],
}

function card(id: string, noteGuid: string, english: string) {
  return {
    id,
    note_id: id,
    note_guid: noteGuid,
    deck_id: deck.id,
    card_template_key: 'sentence_translation',
    card_schedule_revision: 0,
    front: { chinese: '你好。' },
    back: { english },
  }
}

const dialog = {
  props: ['modelValue'],
  template: '<section v-if="modelValue"><slot /></section>',
}

function mountModal() {
  return mount(CardPickerModal, {
    global: { stubs: { 'el-dialog': dialog } },
  })
}

describe('shared library sentence picker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(fetchAllLibraryCards).mockResolvedValue([
      card('first', 'note-one', 'One.'),
      card('second', 'note-two', 'Two.'),
    ])
    vi.mocked(fetchLibrarySelection).mockResolvedValue({
      data: { note_guids: null, joined: false },
    })
    vi.mocked(importLibraryDeck).mockResolvedValue({ data: {} } as never)
  })

  it('pre-checks every sentence and imports only the remaining selection', async () => {
    const wrapper = mountModal()
    ;(wrapper.vm as unknown as { show: (value: DeckView) => void }).show(deck)
    await flushPromises()

    expect(wrapper.text()).toContain('One.')
    expect(wrapper.text()).toContain('Two.')
    const boxes = wrapper.findAll('input[type="checkbox"]')
    expect(boxes).toHaveLength(2)
    expect((boxes[0]!.element as HTMLInputElement).checked).toBe(true)
    expect((boxes[1]!.element as HTMLInputElement).checked).toBe(true)

    await boxes[1]!.setValue(false)
    await wrapper.findAll('button').find(button => button.text().includes('加入所选内容'))!.trigger('click')
    await flushPromises()

    expect(importLibraryDeck).toHaveBeenCalledWith(deck.id, ['note-one'])
    expect(wrapper.emitted('saved')).toHaveLength(1)
    wrapper.unmount()
  })

  it('restores an existing selection and supports importing everything', async () => {
    vi.mocked(fetchLibrarySelection).mockResolvedValue({
      data: { note_guids: ['note-two'], joined: true },
    })
    const wrapper = mountModal()
    ;(wrapper.vm as unknown as { show: (value: DeckView) => void }).show(deck)
    await flushPromises()

    const boxes = wrapper.findAll('input[type="checkbox"]')
    expect((boxes[0]!.element as HTMLInputElement).checked).toBe(false)
    expect((boxes[1]!.element as HTMLInputElement).checked).toBe(true)

    await wrapper.findAll('button').find(button => button.text() === '整组加入')!.trigger('click')
    await flushPromises()
    expect(importLibraryDeck).toHaveBeenCalledWith(deck.id, null)
    wrapper.unmount()
  })

  it('disables saving when nothing is selected but still allows the whole course', async () => {
    vi.mocked(fetchLibrarySelection).mockResolvedValue({
      data: { note_guids: [], joined: false },
    })
    const wrapper = mountModal()
    ;(wrapper.vm as unknown as { show: (value: DeckView) => void }).show(deck)
    await flushPromises()

    const save = wrapper.findAll('button').find(button => button.text().includes('加入所选内容'))!
    expect(save.attributes('disabled')).toBeDefined()
    const whole = wrapper.findAll('button').find(button => button.text() === '整组加入')!
    expect(whole.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
})
