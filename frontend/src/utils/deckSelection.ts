import type { Deck } from '@/types/domain'
import type { UserDeckSummary } from '@/types/api'

export type DeckSelectionStatus = 'none' | 'partial' | 'full'

export interface LessonSelectionItem {
  lessonId: number
  lessonTitle: string
  sourceTitle: string
  unitTitle: string
}

export interface DeckContext {
  deck: Deck
  sourceTitle: string
  unitTitle: string
}

function toLessonId(value: string): number {
  return Number(value)
}

function toDeckId(value: string): number {
  return Number(value)
}

export function normalizeLessonIds(lessonIds: number[]): number[] {
  return [...new Set(lessonIds)].sort((left, right) => left - right)
}

export function normalizeOriginDeckIds(originDeckIds: number[]): number[] {
  return [...new Set(originDeckIds)]
}

export function collectLessonIds(deck: Deck): number[] {
  if (deck.type === 'lesson') {
    return [toLessonId(deck.id)]
  }

  return normalizeLessonIds((deck.children || []).flatMap(collectLessonIds))
}

function compressDeckSelection(deck: Deck, selectedLessonIdSet: Set<number>): number[] {
  const lessonIds = collectLessonIds(deck)
  const selectedCount = lessonIds.filter((lessonId) => selectedLessonIdSet.has(lessonId)).length

  if (selectedCount === 0) return []
  if (selectedCount === lessonIds.length) {
    return [toDeckId(deck.id)]
  }

  return (deck.children || []).flatMap((child) => compressDeckSelection(child, selectedLessonIdSet))
}

export function compressLessonSelectionToOriginDeckIds(
  decks: Deck[],
  selectedLessonIds: number[],
): number[] {
  const selectedLessonIdSet = new Set(selectedLessonIds)
  return normalizeOriginDeckIds(
    decks.flatMap((deck) => compressDeckSelection(deck, selectedLessonIdSet)),
  )
}

export function buildLessonSelectionItems(
  deck: Deck,
  sourceTitle = '',
  unitTitle = '',
): LessonSelectionItem[] {
  if (deck.type === 'lesson') {
    return [
      {
        lessonId: toLessonId(deck.id),
        lessonTitle: deck.name,
        sourceTitle,
        unitTitle,
      },
    ]
  }

  const nextSourceTitle = deck.type === 'source' ? deck.name : sourceTitle
  const nextUnitTitle = deck.type === 'unit' ? deck.name : unitTitle

  return (deck.children || [])
    .flatMap((child) => buildLessonSelectionItems(child, nextSourceTitle, nextUnitTitle))
    .sort((left, right) => left.lessonId - right.lessonId)
}

export function findDeckContext(
  decks: Deck[],
  deckId: string,
  sourceTitle = '',
  unitTitle = '',
): DeckContext | null {
  for (const deck of decks) {
    const nextSourceTitle = deck.type === 'source' ? deck.name : sourceTitle
    const nextUnitTitle = deck.type === 'unit' ? deck.name : unitTitle

    if (deck.id === deckId) {
      return {
        deck,
        sourceTitle: nextSourceTitle,
        unitTitle: nextUnitTitle,
      }
    }

    if (deck.children?.length) {
      const found = findDeckContext(deck.children, deckId, nextSourceTitle, nextUnitTitle)
      if (found) return found
    }
  }

  return null
}

export function getNodeSelectionStatus(deck: Deck, selectedLessonIds: Set<number>): DeckSelectionStatus {
  const lessonIds = collectLessonIds(deck)
  const selectedCount = lessonIds.filter((lessonId) => selectedLessonIds.has(lessonId)).length

  if (selectedCount === 0) return 'none'
  if (selectedCount === lessonIds.length) return 'full'
  return 'partial'
}

export function getSelectedLessonCount(deck: Deck, selectedLessonIds: Set<number>): number {
  return collectLessonIds(deck).filter((lessonId) => selectedLessonIds.has(lessonId)).length
}

export function buildSelectedTree(decks: Deck[], selectedLessonIds: Set<number>): Deck[] {
  return decks.flatMap((deck) => {
    if (deck.type === 'lesson') {
      return selectedLessonIds.has(toLessonId(deck.id)) ? [deck] : []
    }

    const children = buildSelectedTree(deck.children || [], selectedLessonIds)
    if (!children.length) return []

    return [
      {
        ...deck,
        children,
        totalCards: children.reduce((sum, child) => sum + child.totalCards, 0),
        newCards: children.reduce((sum, child) => sum + child.newCards, 0),
        reviewCards: children.reduce((sum, child) => sum + child.reviewCards, 0),
        completedCards: children.reduce((sum, child) => sum + child.completedCards, 0),
      },
    ]
  })
}

export function findDeckById(decks: Deck[], deckId: string): Deck | null {
  for (const deck of decks) {
    if (deck.id === deckId) return deck
    if (deck.children?.length) {
      const found = findDeckById(deck.children, deckId)
      if (found) return found
    }
  }

  return null
}

export function findFirstSelectedLessonId(deck: Deck, selectedLessonIds: Set<number>): string | null {
  const lessonId = collectLessonIds(deck).find((candidate) => selectedLessonIds.has(candidate))
  return lessonId ? String(lessonId) : null
}

export function expandOriginDeckIdsToLessonIds(
  decks: Deck[],
  originDeckIds: number[],
): number[] {
  return normalizeLessonIds(
    originDeckIds.flatMap((originDeckId) => {
      const deck = findDeckById(decks, String(originDeckId))
      return deck ? collectLessonIds(deck) : []
    }),
  )
}

export function expandUserDecksToLessonIds(decks: Deck[], userDecks: UserDeckSummary[]): number[] {
  return expandOriginDeckIdsToLessonIds(
    decks,
    userDecks.map((userDeck) => userDeck.origin_deck_id),
  )
}
