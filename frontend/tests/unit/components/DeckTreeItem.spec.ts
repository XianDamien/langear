import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import type { DeckView } from '@/stores/decks'

const lesson: DeckView = {
  id: '01900000-0000-7000-8000-000000000018',
  name: 'Lesson one',
  origin: 'core',
  type: 'lesson',
  inMyCourses: false,
  totalCards: 4,
  newCards: 2,
  reviewCards: 1,
  completedCards: 1,
  dueCards: 3,
  children: [],
}

describe('core deck tree entry points', () => {
  it('keeps library leaf decks on the page and allows joining or selecting cards', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: { deck: lesson, mode: 'library' },
    })
    expect(wrapper.text()).not.toContain('开始')
    await wrapper.get('.truncate').trigger('click')
    expect(wrapper.emitted('playDeck')).toBeUndefined()
    expect(wrapper.find('button[aria-label="Lesson one 设置"]').exists()).toBe(false)
    await wrapper.findAll('button').find(button => button.text() === '加入')!.trigger('click')
    expect(wrapper.emitted('toggleMembership')).toEqual([[lesson.id]])
    await wrapper.get('button[aria-label="Lesson one 选择卡片"]').trigger('click')
    expect(wrapper.emitted('selectCards')).toEqual([[lesson.id]])
  })

  it('starts review and opens settings from my courses', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: { deck: { ...lesson, inMyCourses: true }, mode: 'my-courses' },
    })
    await wrapper.findAll('button').find(button => button.text() === '开始')!.trigger('click')
    expect(wrapper.emitted('playDeck')).toEqual([[lesson.id]])
    await wrapper.get('button[aria-label="Lesson one 设置"]').trigger('click')
    expect(wrapper.emitted('editDeckSettings')).toEqual([[lesson.id]])
    expect(wrapper.emitted('playDeck')).toHaveLength(1)
  })

  it('expands library groups without opening practice from nested leaves', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: {
        deck: { ...lesson, name: 'Book', type: 'source', children: [lesson] },
        mode: 'library',
        depth: 0,
      },
    })
    expect(wrapper.findAll('.truncate')).toHaveLength(2)
    await wrapper.findAll('.truncate')[0]!.trigger('click')
    expect(wrapper.findAll('.truncate')).toHaveLength(1)
    await wrapper.get('.truncate').trigger('click')
    expect(wrapper.findAll('.truncate')).toHaveLength(2)
    expect(wrapper.emitted('playDeck')).toBeUndefined()
  })

  it('shows joined state and honors the disabled prop', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: { deck: { ...lesson, inMyCourses: true }, mode: 'library', selectionDisabled: true },
    })
    const joined = wrapper.findAll('button').find(button => button.text() === '已加入')!
    expect(joined.attributes('disabled')).toBeDefined()
    await joined.trigger('click')
    expect(wrapper.emitted('toggleMembership')).toBeUndefined()
  })
})
