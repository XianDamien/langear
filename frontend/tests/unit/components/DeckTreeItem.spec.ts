import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import type { Deck } from '@/types/domain'

const lesson: Deck = {
  id: '18', name: 'Lesson one', description: '', type: 'lesson',
  totalCards: 4, newCards: 2, reviewCards: 1, completedCards: 1,
}

describe('course tree entry points', () => {
  it('keeps library lessons browsable without opening study or review', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: { deck: lesson, mode: 'library', selectedLessonIdSet: new Set<number>() },
    })
    expect(wrapper.text()).not.toContain('开始')
    expect(wrapper.findAll('button').map(button => button.text())).not.toContain('复习')
    await wrapper.get('.truncate').trigger('click')
    expect(wrapper.emitted('selectLesson')).toBeUndefined()
    expect(wrapper.emitted('playDeck')).toBeUndefined()
    expect(wrapper.find('button[aria-label="Lesson one 设置"]').exists()).toBe(false)
    await wrapper.findAll('button').find(button => button.text() === '加入')!.trigger('click')
    expect(wrapper.emitted('toggleDeckSelection')).toEqual([['18']])
  })

  it('keeps the existing start action in my courses', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: { deck: lesson, mode: 'my-courses', selectedLessonIdSet: new Set([18]) },
    })
    await wrapper.findAll('button').find(button => button.text() === '开始')!.trigger('click')
    expect(wrapper.emitted('selectLesson')).toEqual([['18']])
    await wrapper.get('button[aria-label="Lesson one 设置"]').trigger('click')
    expect(wrapper.emitted('editDeckSettings')).toEqual([['18']])
    expect(wrapper.emitted('selectLesson')).toHaveLength(1)
  })

  it('expands the library hierarchy without exposing nested study actions', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: {
        deck: { ...lesson, id: '1', name: 'Book', type: 'source', children: [lesson] },
        mode: 'library', selectedLessonIdSet: new Set<number>(), depth: 0,
      },
    })
    const nested = wrapper.findComponent(DeckTreeItem)
    await nested.get('.truncate').trigger('click')
    expect(wrapper.emitted('selectLesson')).toBeUndefined()
    expect(wrapper.emitted('playDeck')).toBeUndefined()
    expect(wrapper.findAll('button').some(button => /^(复习|开始)$/.test(button.text()))).toBe(false)
  })
})
