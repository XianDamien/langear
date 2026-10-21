import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  createDeck as createDeckRequest,
  fetchDeckTree,
  resourceError,
  setDeckMembership,
  type DeckTreeNode,
  type DeckTreeRow,
  type ResourceCard,
} from '@/services/content'

export type DeckNodeType = 'source' | 'unit' | 'lesson'

export interface DeckView {
  id: string
  name: string
  origin: 'core'
  type: DeckNodeType
  deckGuid?: string | null
  inMyCourses: boolean
  totalCards: number
  newCards: number
  reviewCards: number
  completedCards: number
  dueCards: number
  children: DeckView[]
}

function viewType(children: DeckTreeNode[]): DeckNodeType {
  if (!children.length) return 'lesson'
  return 'source'
}

function toView(node: DeckTreeNode): DeckView {
  return {
    id: node.id,
    name: node.name,
    origin: 'core',
    type: viewType(node.children),
    deckGuid: node.deck_guid,
    inMyCourses: node.in_my_courses,
    totalCards: node.stats.total_cards,
    newCards: node.stats.new_cards,
    reviewCards: node.stats.review_cards + node.stats.learning_cards,
    completedCards: node.stats.completed_cards,
    dueCards: node.stats.due_cards,
    children: node.children.map(toView),
  }
}

function toFlatView(row: DeckTreeRow): DeckView {
  return {
    id: row.id,
    name: row.name,
    origin: 'core',
    type: 'lesson',
    deckGuid: row.deck_guid,
    inMyCourses: row.in_my_courses,
    totalCards: row.stats.total_cards,
    newCards: row.stats.new_cards,
    reviewCards: row.stats.review_cards + row.stats.learning_cards,
    completedCards: row.stats.completed_cards,
    dueCards: row.stats.due_cards,
    children: [],
  }
}

function pruneToJoined(nodes: DeckTreeNode[], inherited = false): DeckView[] {
  return nodes.flatMap(node => {
    const joined = inherited || node.in_my_courses
    const children = pruneToJoined(node.children, joined)
    if (!joined && !children.length) return []

    const view = toView(node)
    view.inMyCourses = joined
    view.children = children
    if (!node.in_my_courses && children.length) {
      view.totalCards = children.reduce((sum, child) => sum + child.totalCards, 0)
      view.newCards = children.reduce((sum, child) => sum + child.newCards, 0)
      view.reviewCards = children.reduce((sum, child) => sum + child.reviewCards, 0)
      view.completedCards = children.reduce((sum, child) => sum + child.completedCards, 0)
      view.dueCards = children.reduce((sum, child) => sum + child.dueCards, 0)
    }
    return [view]
  })
}

export const useDecksStore = defineStore('decks', () => {
  const rows = ref<DeckTreeRow[]>([])
  const tree = ref<DeckTreeNode[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)
  const cardsByDeck = ref<Record<string, ResourceCard[]>>({})

  const libraryTree = computed(() => tree.value.map(toView))
  const joinedRows = computed(() => rows.value.filter(row => row.in_my_courses))
  const myCourses = computed(() => joinedRows.value.map(toFlatView))
  const myCoursesTree = computed(() => pruneToJoined(tree.value))
  const joinedIds = computed(() => new Set(joinedRows.value.map(row => row.id)))

  function deckPath(deckId: string): string {
    const row = rows.value.find(item => item.id === deckId)
    if (!row) return ''
    const byId = new Map(rows.value.map(item => [item.id, item]))
    return (row.path || [deckId])
      .map(id => byId.get(id)?.name)
      .filter(Boolean)
      .join(' / ')
  }

  function replaceRow(updated: { id: string; in_my_courses: boolean }) {
    rows.value = rows.value.map(row =>
      row.id === updated.id ? { ...row, in_my_courses: updated.in_my_courses } : row,
    )
    const patch = (nodes: DeckTreeNode[]): DeckTreeNode[] =>
      nodes.map(node => ({
        ...node,
        in_my_courses: node.id === updated.id ? updated.in_my_courses : node.in_my_courses,
        children: patch(node.children),
      }))
    tree.value = patch(tree.value)
  }

  async function load(force = true) {
    if (!force && rows.value.length) return
    loading.value = true
    error.value = null
    try {
      const data = await fetchDeckTree()
      rows.value = data.decks
      tree.value = data.tree
    } catch (cause) {
      error.value = resourceError(cause)
      throw cause
    } finally {
      loading.value = false
    }
  }

  async function createDeck(name: string, parentId?: string | null) {
    saving.value = true
    try {
      const { data } = await createDeckRequest(name, parentId)
      await load()
      return data
    } finally {
      saving.value = false
    }
  }

  async function toggleMembership(deckId: string) {
    if (saving.value) return
    saving.value = true
    try {
      const joined = !joinedIds.value.has(deckId)
      const { data } = await setDeckMembership(deckId, joined)
      replaceRow(data)
      return data.in_my_courses
    } finally {
      saving.value = false
    }
  }

  function setDeckCards(deckId: string, cards: ResourceCard[]) {
    cardsByDeck.value = { ...cardsByDeck.value, [deckId]: cards }
  }

  return {
    rows,
    tree,
    loading,
    saving,
    error,
    cardsByDeck,
    libraryTree,
    joinedRows,
    myCourses,
    myCoursesTree,
    joinedIds,
    deckPath,
    load,
    createDeck,
    toggleMembership,
    setDeckCards,
  }
})
