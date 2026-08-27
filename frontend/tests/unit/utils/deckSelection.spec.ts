import { describe, expect, it } from 'vitest'
import type { UserDeckSummary } from '@/types/api'
import type { Deck } from '@/types/domain'
import {
  buildLessonSelectionItems,
  buildSelectedTree,
  compressLessonSelectionToOriginDeckIds,
  expandUserDecksToLessonIds,
  findDeckContext,
  findFirstSelectedLessonId,
  getNodeSelectionStatus,
} from '@/utils/deckSelection'

const sampleTree: Deck[] = [
  {
    id: '1',
    name: 'Source A',
    description: '',
    totalCards: 9,
    newCards: 3,
    reviewCards: 2,
    completedCards: 4,
    type: 'source',
    children: [
      {
        id: '11',
        name: 'Unit A',
        description: '',
        totalCards: 9,
        newCards: 3,
        reviewCards: 2,
        completedCards: 4,
        type: 'unit',
        parentId: '1',
        children: [
          {
            id: '101',
            name: 'Lesson 101',
            description: '',
            totalCards: 4,
            newCards: 1,
            reviewCards: 1,
            completedCards: 2,
            type: 'lesson',
            parentId: '11',
          },
          {
            id: '102',
            name: 'Lesson 102',
            description: '',
            totalCards: 5,
            newCards: 2,
            reviewCards: 1,
            completedCards: 2,
            type: 'lesson',
            parentId: '11',
          },
        ],
      },
    ],
  },
]

describe('deckSelection', () => {
  it('builds lesson picker items with source and unit context', () => {
    const context = findDeckContext(sampleTree, '11')
    expect(context).not.toBeNull()

    const items = buildLessonSelectionItems(
      context!.deck,
      context!.sourceTitle,
      context!.unitTitle,
    )

    expect(items).toEqual([
      {
        lessonId: 101,
        lessonTitle: 'Lesson 101',
        sourceTitle: 'Source A',
        unitTitle: 'Unit A',
      },
      {
        lessonId: 102,
        lessonTitle: 'Lesson 102',
        sourceTitle: 'Source A',
        unitTitle: 'Unit A',
      },
    ])
  })

  it('marks source nodes as partial until all descendant lessons are selected', () => {
    const source = sampleTree[0]!

    expect(getNodeSelectionStatus(source, new Set())).toBe('none')
    expect(getNodeSelectionStatus(source, new Set([101]))).toBe('partial')
    expect(getNodeSelectionStatus(source, new Set([101, 102]))).toBe('full')
  })

  it('builds a selected-only tree and resolves the first selected lesson by id', () => {
    const filteredTree = buildSelectedTree(sampleTree, new Set([102]))

    expect(filteredTree).toHaveLength(1)
    expect(filteredTree[0]!.children?.[0]!.children?.map((lesson) => lesson.id)).toEqual(['102'])
    expect(findFirstSelectedLessonId(sampleTree[0]!, new Set([102]))).toBe('102')
  })

  it('compresses fully selected scopes into mixed origin deck ids', () => {
    expect(compressLessonSelectionToOriginDeckIds(sampleTree, [101])).toEqual([101])
    expect(compressLessonSelectionToOriginDeckIds(sampleTree, [101, 102])).toEqual([1])
  })

  it('expands active user decks back into selected lesson ids', () => {
    const userDecks: UserDeckSummary[] = [
      {
        id: 1,
        origin_deck_id: 11,
        title: 'Unit A',
        scope_type: 'unit',
        total_count: 9,
        new_count: 3,
        learning_count: 2,
        review_count: 1,
      },
    ]

    expect(expandUserDecksToLessonIds(sampleTree, userDecks)).toEqual([101, 102])
  })
})
