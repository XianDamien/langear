import type { UserDeckSummary } from '@/types/api'
import { collectLessonIds, findDeckById, normalizeOriginDeckIds } from '@/utils/deckSelection'
import { mockDeckTree, mockLessonCards } from './decks'

const STORAGE_KEY = 'mock_user_deck_origin_ids'
const DEFAULT_ORIGIN_DECK_IDS = [1001, 2001]

function readStoredOriginIds(): number[] {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (!stored) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(DEFAULT_ORIGIN_DECK_IDS))
    return DEFAULT_ORIGIN_DECK_IDS
  }

  return normalizeOriginDeckIds(JSON.parse(stored) as number[])
}

export function readMockUserDeckOriginIds(): number[] {
  return readStoredOriginIds()
}

export function writeMockUserDeckOriginIds(originDeckIds: number[]): number[] {
  const normalized = normalizeOriginDeckIds(originDeckIds)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  return normalized
}

export function buildMockUserDecks(originDeckIds: number[]): UserDeckSummary[] {
  const tree = mockDeckTree.tree ?? []

  return originDeckIds.flatMap((originDeckId) => {
    const deck = findDeckById(tree, String(originDeckId))
    if (!deck) return []

    const lessonIds = collectLessonIds(deck)
    const cards = lessonIds.flatMap((lessonId) => mockLessonCards[String(lessonId)]?.cards ?? [])

    return [
      {
        id: originDeckId,
        origin_deck_id: originDeckId,
        title: deck.name,
        scope_type: deck.type,
        total_count: cards.length,
        new_count: cards.filter((card) => card.isNewCard).length,
        learning_count: cards.filter(
          (card) =>
            !card.isNewCard &&
            (card.cardState === 'learning' || card.cardState === 'relearning'),
        ).length,
        review_count: cards.filter(
          (card) => !card.isNewCard && card.cardState === 'review',
        ).length,
      },
    ]
  })
}
