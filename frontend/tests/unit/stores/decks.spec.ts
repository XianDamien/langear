import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDecksStore } from '@/stores/decks'
import { fetchDeckTree, type DeckTreeNode } from '@/services/content'

vi.mock('@/services/content', () => ({
  fetchDeckTree: vi.fn(),
  createDeck: vi.fn(),
  setDeckMembership: vi.fn(),
  resourceError: (error: unknown) => String(error),
}))

function stats(cards: number) {
  return {
    total_cards: cards,
    note_count: cards,
    selected_cards: 0,
    new_cards: cards,
    learning_cards: 0,
    review_cards: 0,
    completed_cards: 0,
    due_cards: 0,
  }
}

function node(
  id: string,
  name: string,
  joined: boolean,
  children: DeckTreeNode[] = [],
  cards = 1,
): DeckTreeNode {
  return {
    id,
    name,
    parent_id: null,
    kind: 'standard',
    deck_guid: null,
    in_my_courses: joined,
    stats: stats(cards),
    children,
  }
}

describe('myCoursesTree', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('keeps joined branches and their ancestors in hierarchy', async () => {
    const tree = [
      node('course-a', 'Course A', true, [
        node('unit-a', 'Unit A', false, [node('lesson-a', 'Lesson A', false, [], 5)], 5),
      ]),
      node('course-b', 'Course B', false, [
        node('unit-b', 'Unit B', false, [
          node('lesson-b1', 'Lesson B1', true, [], 5),
          node('lesson-b2', 'Lesson B2', false, [], 3),
        ], 8),
      ]),
      node('course-c', 'Course C', false, [node('lesson-c', 'Lesson C', false)]),
    ]
    vi.mocked(fetchDeckTree).mockResolvedValue({ decks: [], tree })

    const store = useDecksStore()
    await store.load()

    expect(store.myCoursesTree.map(deck => deck.name)).toEqual(['Course A', 'Course B'])
    // A joined parent includes all descendants even when they are not individually joined.
    expect(store.myCoursesTree[0].children.map(deck => deck.name)).toEqual(['Unit A'])
    expect(store.myCoursesTree[0].children[0].children.map(deck => deck.name)).toEqual(['Lesson A'])
    // An unjoined ancestor only keeps the joined branch and inherits its stats.
    expect(store.myCoursesTree[1].children.map(deck => deck.name)).toEqual(['Unit B'])
    expect(store.myCoursesTree[1].children[0].children.map(deck => deck.name)).toEqual(['Lesson B1'])
    expect(store.myCoursesTree[1].totalCards).toBe(5)
  })

  it('keeps the full library tree independent of membership', async () => {
    const tree = [
      node('course-a', 'Course A', false, [node('lesson-a', 'Lesson A', false)]),
    ]
    vi.mocked(fetchDeckTree).mockResolvedValue({ decks: [], tree })

    const store = useDecksStore()
    await store.load()

    expect(store.myCoursesTree).toEqual([])
    expect(store.libraryTree.map(deck => deck.name)).toEqual(['Course A'])
  })
})
