import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { flushPromises } from '@vue/test-utils'
import { mountWithApp } from '../../helpers/mountWithApp'
import MyCoursesView from '@/views/MyCoursesView.vue'
import LibraryView from '@/views/LibraryView.vue'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import { isUuid } from '@/services/api/settings'
import {
  deleteDeck,
  fetchDeletePreview,
  fetchLibraryDeckTree,
  importLibraryDeck,
  type DeletePreview,
  type LibraryImportResult,
} from '@/services/content'

vi.mock('@/components/library/LibraryContentEditor.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/services/content', async importOriginal => {
  const actual = await importOriginal<typeof import('@/services/content')>()
  return {
    ...actual,
    fetchLibraryDeckTree: vi.fn(),
    importLibraryDeck: vi.fn(),
    fetchDeletePreview: vi.fn(),
    deleteDeck: vi.fn(),
  }
})

const joinedId = '01900000-0000-7000-8000-000000000001'
const otherId = '01900000-0000-7000-8000-000000000002'
const copiedId = '01900000-0000-7000-8000-000000000003'

const stats = {
  total_cards: 4, selected_cards: 4, new_cards: 4, learning_cards: 0,
  review_cards: 0, completed_cards: 0, due_cards: 4,
}

const libraryStats = {
  total_cards: 4, note_count: 4,
}

function row(id: string, name: string, joined: boolean) {
  return {
    id, name, parent_id: null, kind: 'standard' as const, in_my_courses: joined,
    depth: 0, path: [id], stats,
  }
}

function node(id: string, name: string, joined: boolean) {
  return { ...row(id, name, joined), children: [] }
}

function libraryNode(id: string, name: string, joined: boolean) {
  return {
    ...row(id, name, joined),
    stats: libraryStats,
    source_metadata: { source: 'library' },
    children: [],
  }
}

function importResult(overrides: Partial<LibraryImportResult> = {}): LibraryImportResult {
  return {
    imported: true,
    deck_id: copiedId,
    deck_ids: [copiedId],
    selection: null,
    created: { decks: 1, notes: 4, cards: 4 },
    existing: { decks: 0, notes: 0, cards: 0 },
    skipped_cards: [],
    warnings: [],
    ...overrides,
  }
}

function preview(
  overrides: Partial<DeletePreview['impact']> = {},
  token = 'signed.token',
): DeletePreview {
  return {
    impact: {
      decks_deleted: 2,
      notes_deleted: 4,
      cards_deleted: 6,
      attempts_deleted: 3,
      media_references_deleted: 0,
      cards_returned: 0,
      ...overrides,
    },
    confirmation_token: token,
  }
}

function libraryCopyRow() {
  return {
    ...row(copiedId, '共享课程', true),
    source_metadata: { source: 'library' },
  }
}

function libraryCopyState() {
  return {
    decks: {
      rows: [libraryCopyRow()],
      tree: [{ ...libraryCopyRow(), children: [] }],
      cardsByDeck: {},
      loading: false,
      saving: false,
      error: null,
    },
  }
}

const rows = [row(joinedId, '我的牌组', true), row(otherId, '公共牌组', false)]
const tree = [node(joinedId, '我的牌组', true), node(otherId, '公共牌组', false)]

beforeEach(() => {
  vi.mocked(fetchLibraryDeckTree).mockResolvedValue({
    tree: [libraryNode(otherId, '公共牌组', false)],
    decks: [],
  })
  vi.mocked(importLibraryDeck).mockResolvedValue({ data: importResult() })
  vi.mocked(fetchDeletePreview).mockResolvedValue({ data: preview() })
  vi.mocked(deleteDeck).mockResolvedValue({
    data: { deleted: true, impact: preview().impact },
  })
})

async function mountCoursePage(
  component: typeof MyCoursesView | typeof LibraryView,
  path: string,
  initialState: Record<string, unknown> = {},
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/my-courses', component: MyCoursesView },
      { path: '/library', component: LibraryView },
      { path: '/review/:deckId', name: 'DeckReview', component: { template: '<div />' } },
      { path: '/settings', name: 'Settings', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  const wrapper = mountWithApp(component, {
    pinia: {
      initialState: {
        decks: { rows, tree, cardsByDeck: {}, loading: false, saving: false, error: null },
        ...initialState,
      },
    },
    global: { plugins: [router] },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('personal course settings navigation', () => {
  it('starts a joined core deck at its UUID review route', async () => {
    const { wrapper, router } = await mountCoursePage(MyCoursesView, '/my-courses')
    const row = wrapper.findAllComponents(DeckTreeItem).find(item => item.props('deck').id === joinedId)!
    await row.findAll('button').find(button => button.text() === '开始')!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe(`/review/${joinedId}`)
    wrapper.unmount()
  })

  it('opens settings with the selected UUID deck', async () => {
    const { wrapper, router } = await mountCoursePage(MyCoursesView, '/my-courses')
    await wrapper.get('button[aria-label="我的牌组 设置"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(`/settings?deck_id=${joinedId}`)
    wrapper.unmount()
  })

  it('imports the library course without starting practice', async () => {
    const { wrapper, router } = await mountCoursePage(LibraryView, '/library')
    expect(wrapper.findAll('button[aria-label$=" 设置"]')).toHaveLength(0)
    expect(wrapper.findAll('button').some(button => /^(复习|开始)$/.test(button.text()))).toBe(false)
    const publicRow = wrapper.findAllComponents(DeckTreeItem).find(item => item.props('deck').id === otherId)!
    await publicRow.findAll('button').find(button => button.text() === '加入')!.trigger('click')
    await flushPromises()
    expect(importLibraryDeck).toHaveBeenCalledWith(otherId)
    expect(router.currentRoute.value.path).toBe('/library')
    wrapper.unmount()
  })

  it('shows the created and existing card counts after an import', async () => {
    vi.mocked(importLibraryDeck).mockResolvedValue({
      data: importResult({ created: { decks: 0, notes: 0, cards: 2 }, existing: { decks: 1, notes: 4, cards: 4 } }),
    })
    const { wrapper } = await mountCoursePage(LibraryView, '/library')
    const publicRow = wrapper.findAllComponents(DeckTreeItem).find(item => item.props('deck').id === otherId)!
    await publicRow.findAll('button').find(button => button.text() === '加入')!.trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('新增 2 张卡片')
    wrapper.unmount()
  })

  it('previews the copy deletion and cancels without deleting', async () => {
    const { wrapper } = await mountCoursePage(MyCoursesView, '/my-courses', libraryCopyState())
    expect(wrapper.findComponent(DeckTreeItem).props('deck').source).toBe('library')
    await wrapper.get('button[aria-label="删除 共享课程 的个人副本"]').trigger('click')
    await flushPromises()
    expect(fetchDeletePreview).toHaveBeenCalledWith(copiedId)
    expect(wrapper.get('[role="dialog"]').text()).toContain('6 张卡片')
    const cancel = wrapper.findAll('button').find(button => button.text() === '取消')!
    await cancel.trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(deleteDeck).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('deletes the copy after confirmation', async () => {
    const { wrapper } = await mountCoursePage(MyCoursesView, '/my-courses', libraryCopyState())
    await wrapper.get('button[aria-label="删除 共享课程 的个人副本"]').trigger('click')
    await flushPromises()
    const confirm = wrapper.findAll('button').find(button => button.text() === '删除副本')!
    await confirm.trigger('click')
    await flushPromises()
    expect(deleteDeck).toHaveBeenCalledWith(copiedId, 'signed.token')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('refreshes a stale deletion preview instead of retrying the old token', async () => {
    vi.mocked(deleteDeck).mockRejectedValueOnce({
      response: { data: { error: { code: 'DELETION_IMPACT_CHANGED', message: 'stale' } } },
    })
    vi.mocked(fetchDeletePreview)
      .mockResolvedValueOnce({ data: preview({ cards_deleted: 6 }) })
      .mockResolvedValueOnce({ data: preview({ cards_deleted: 8 }, 'fresh.token') })
    const { wrapper } = await mountCoursePage(MyCoursesView, '/my-courses', libraryCopyState())
    await wrapper.get('button[aria-label="删除 共享课程 的个人副本"]').trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '删除副本')!.trigger('click')
    await flushPromises()
    expect(fetchDeletePreview).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[role="alert"]').text()).toContain('已刷新影响范围')
    expect(wrapper.get('[role="dialog"]').text()).toContain('8 张卡片')
    // The dialog stays open with the refreshed scope so the learner can decide.
    expect(wrapper.findAll('button').some(button => button.text() === '删除副本')).toBe(true)
    wrapper.unmount()
  })

  it('redirects old numeric deck settings links without creating a UUID', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{
        path: '/decks/:deckId/settings',
        name: 'DeckSettings',
        redirect: to => ({
          name: 'Settings',
          query: isUuid(String(to.params.deckId)) ? { deck_id: String(to.params.deckId) } : {},
        }),
      }, { path: '/settings', name: 'Settings', component: { template: '<div />' } }],
    })
    await router.push('/decks/18/settings')
    expect(router.currentRoute.value.fullPath).toBe('/settings')
    await router.push(`/decks/${joinedId}/settings`)
    expect(router.currentRoute.value.fullPath).toBe(`/settings?deck_id=${joinedId}`)
  })
})
