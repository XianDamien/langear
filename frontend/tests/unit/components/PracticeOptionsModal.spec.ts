import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PracticeOptionsModal from '@/components/review/PracticeOptionsModal.vue'
import { fetchPracticeOptions } from '@/services/review'

vi.mock('@/services/review', () => ({ fetchPracticeOptions: vi.fn() }))

const options = [
  { key: 'sentence_retelling', count: 3 },
  { key: 'sentence_translation', count: 2 },
  { key: 'sentence_dictation', count: 1 },
] as Awaited<ReturnType<typeof fetchPracticeOptions>>

function mountModal(props: Record<string, unknown> = {}) {
  return mount(PracticeOptionsModal, {
    props: { open: true, deckId: 'deck-1', deckName: 'Lesson', ...props },
  })
}

describe('practice options', () => {
  beforeEach(() => {
    vi.mocked(fetchPracticeOptions).mockResolvedValue(options)
  })

  it('selects the first available practice type and starts a round', async () => {
    const wrapper = mountModal()
    await flushPromises()

    expect(wrapper.get('[data-testid="practice-option-sentence_retelling"]').attributes('aria-pressed')).toBe('true')
    await wrapper.get('[data-testid="practice-option-sentence_translation"]').trigger('click')
    await wrapper.get('[data-testid="practice-confirm"]').trigger('click')

    expect(wrapper.emitted('confirm')?.[0]?.[0]).toEqual({
      templates: ['sentence_retelling', 'sentence_translation'],
      limit: 10,
    })
  })

  it('restores an existing selection and round size', async () => {
    const wrapper = mountModal({
      initialTemplates: ['sentence_dictation'],
      initialLimit: 20,
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="practice-option-sentence_dictation"]').attributes('aria-pressed')).toBe('true')
    await wrapper.get('[data-testid="practice-confirm"]').trigger('click')

    expect(wrapper.emitted('confirm')?.[0]?.[0]).toEqual({
      templates: ['sentence_dictation'],
      limit: 20,
    })
  })
})
