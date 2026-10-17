import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import type { Deck } from '@/types/domain'

const lesson: Deck = {
  id: '18', name: 'Lesson one', description: '', type: 'lesson',
  totalCards: 4, newCards: 2, reviewCards: 1, completedCards: 1,
}

describe('course tree entry points', () => {
  it('keeps library leaf decks on the page and allows joining', async () => {
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

  it('expands library groups without opening practice from nested leaves', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: {
        deck: { ...lesson, id: '1', name: 'Book', type: 'source', children: [lesson] },
        mode: 'library', selectedLessonIdSet: new Set<number>(), depth: 0,
      },
    })
    await wrapper.findAll('.truncate')[1]!.trigger('click')
    expect(wrapper.emitted('selectLesson')).toBeUndefined()
    await wrapper.findAll('.truncate')[0]!.trigger('click')
    expect(wrapper.findAll('.truncate')).toHaveLength(1)
    await wrapper.get('.truncate').trigger('click')
    expect(wrapper.findAll('.truncate')).toHaveLength(2)
    expect(wrapper.emitted('playDeck')).toBeUndefined()
    expect(wrapper.findAll('button').some(button => /^(复习|开始)$/.test(button.text()))).toBe(false)
  })
})


describe('core deck component reuse', () => {
  it('uses UUID membership without opening review from library', async () => {
    const id = '01900000-0000-7000-8000-000000000001'
    const wrapper = mount(DeckTreeItem, {
      props: { deck: { ...lesson, id, origin: 'core', type: 'source' }, mode: 'library', selectedLessonIdSet: new Set<number>(), selectedCoreDeckIds: new Set([id]) },
    })
    expect(wrapper.text()).toContain('4 张卡片')
    expect(wrapper.text()).not.toContain('复习 1')
    const joined = wrapper.findAll('button').find(button => button.text() === '已加入')!
    await joined.trigger('click')
    expect(wrapper.emitted('toggleDeckSelection')).toEqual([[id]])
    expect(wrapper.emitted('selectLesson')).toBeUndefined()
    await wrapper.get('.truncate').trigger('click')
    expect(wrapper.emitted('selectLesson')).toBeUndefined()
    expect(wrapper.emitted('playDeck')).toBeUndefined()
    await wrapper.setProps({ selectionDisabled: true })
    expect(joined.attributes('disabled')).toBeDefined()
  })
})
