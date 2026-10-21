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
  it('offers sentence selection, preview and whole-course import for library decks', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: { deck: lesson, mode: 'library' },
    })
    expect(wrapper.text()).not.toContain('开始')
    await wrapper.get('.truncate').trigger('click')
    expect(wrapper.emitted('playDeck')).toBeUndefined()
    expect(wrapper.find('button[aria-label="Lesson one 设置"]').exists()).toBe(false)
    // Library leaves offer sentence selection, card preview and whole-course import.
    const selectButton = wrapper.get('button[aria-label="选择 Lesson one 的句子"]')
    expect(selectButton.exists()).toBe(true)
    await selectButton.trigger('click')
    expect(wrapper.emitted('selectCards')).toEqual([[lesson.id]])
    expect(wrapper.emitted('toggleMembership')).toBeUndefined()
    await wrapper.get('button[aria-label="查看 Lesson one 的卡片"]').trigger('click')
    expect(wrapper.emitted('previewDeck')).toEqual([[lesson.id]])
    await wrapper.findAll('button').find(button => button.text() === '加入')!.trigger('click')
    expect(wrapper.emitted('toggleMembership')).toEqual([[lesson.id]])
  })

  it('offers an idempotent refresh once the copy is already in my courses', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: { deck: { ...lesson, inMyCourses: true }, mode: 'library' },
    })
    const joined = wrapper.findAll('button').find(button => button.text() === '已加入')!
    expect(joined.attributes('title')).toContain('重新同步')
    await joined.trigger('click')
    expect(wrapper.emitted('toggleMembership')).toEqual([[lesson.id]])
  })

  it('starts review, opens settings and removes a Library copy from my courses', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: { deck: { ...lesson, inMyCourses: true, source: 'library' }, mode: 'my-courses' },
    })
    await wrapper.findAll('button').find(button => button.text() === '开始')!.trigger('click')
    expect(wrapper.emitted('playDeck')).toEqual([[lesson.id]])
    await wrapper.get('button[aria-label="Lesson one 设置"]').trigger('click')
    expect(wrapper.emitted('editDeckSettings')).toEqual([[lesson.id]])
    expect(wrapper.emitted('playDeck')).toHaveLength(1)
    await wrapper.get('button[aria-label="删除 Lesson one 的个人副本"]').trigger('click')
    expect(wrapper.emitted('removeDeck')).toEqual([[lesson.id]])
  })

  it('hides the copy delete action for learner-authored courses', () => {
    const wrapper = mount(DeckTreeItem, {
      props: { deck: { ...lesson, inMyCourses: true }, mode: 'my-courses' },
    })
    expect(wrapper.find('button[aria-label="删除 Lesson one 的个人副本"]').exists()).toBe(false)
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
    expect(wrapper.find('button[aria-label="选择 Book 的句子"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="选择 Lesson one 的句子"]').exists()).toBe(true)
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

  it('disables deleting a copy while a removal is pending', async () => {
    const wrapper = mount(DeckTreeItem, {
      props: {
        deck: { ...lesson, inMyCourses: true, source: 'library' },
        mode: 'my-courses',
        selectionDisabled: true,
      },
    })
    const remove = wrapper.get('button[aria-label="删除 Lesson one 的个人副本"]')
    expect(remove.attributes('disabled')).toBeDefined()
    await remove.trigger('click')
    expect(wrapper.emitted('removeDeck')).toBeUndefined()
  })
})
