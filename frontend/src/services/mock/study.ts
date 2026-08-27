import type { FsrsRating, FsrsState, RatingLabel } from '@/types/domain'
import type {
  StudySessionCardResponse,
  StudySessionResponse,
} from '@/types/api'
import { collectLessonIds, findDeckById } from '@/utils/deckSelection'
import { formatBusinessIso } from '@/utils/businessTime'
import { mockDeckTree, mockLessonCards } from './decks'

const ratingLabelMap: Record<FsrsRating, RatingLabel> = {
  1: 'again',
  2: 'hard',
  3: 'good',
  4: 'easy',
}

const lessonSourceScope: Record<number, number[]> = {
  1001: [1],
  1002: [1],
  1003: [1],
  2001: [2],
}

function formatHoursAgoIso(hours: number): string {
  return formatBusinessIso(new Date(Date.now() - hours * 60 * 60 * 1000))
}

function buildMockCardMeta(index: number): {
  cardState: FsrsState
  isNewCard: boolean
  lastReviewAt: string | null
  dueAt: string | null
} {
  switch (index % 4) {
    case 0:
      return {
        cardState: 'learning',
        isNewCard: true,
        lastReviewAt: null,
        dueAt: formatBusinessIso(new Date()),
      }
    case 1:
      return {
        cardState: 'learning',
        isNewCard: false,
        lastReviewAt: formatHoursAgoIso(12),
        dueAt: formatBusinessIso(new Date(Date.now() + 3 * 60 * 60 * 1000)),
      }
    case 2:
      return {
        cardState: 'review',
        isNewCard: false,
        lastReviewAt: formatHoursAgoIso(36),
        dueAt: formatBusinessIso(new Date(Date.now() + 24 * 60 * 60 * 1000)),
      }
    default:
      return {
        cardState: 'relearning',
        isNewCard: false,
        lastReviewAt: formatHoursAgoIso(6),
        dueAt: formatBusinessIso(new Date(Date.now() + 60 * 60 * 1000)),
      }
  }
}

function isNewCard(card: {
  is_new_card?: boolean
  last_review_at?: string | null
}): boolean {
  if (card.is_new_card != null) return card.is_new_card
  return card.last_review_at === null
}

function buildSessionCards(lessonId: number): StudySessionCardResponse[] {
  const lesson = mockLessonCards[String(lessonId)]
  if (!lesson) return []

  return lesson.cards.map((card, index) => {
    const meta = buildMockCardMeta(index)
    return {
      id: card.id,
      lesson_id: lessonId,
      card_index: index + 1,
      front_text: card.backText,
      back_text: card.backTranslation,
      audio_path: card.frontAudio ?? '',
      oss_audio_path: card.ossAudioPath ?? null,
      card_state: card.cardState ?? meta.cardState,
      due_at: card.dueAt ?? meta.dueAt,
      is_new_card: card.isNewCard ?? meta.isNewCard,
      last_review_at: card.lastReviewAt ?? meta.lastReviewAt,
    }
  })
}

export function buildMockStudySession(params?: {
  lessonId?: number
  userDeckId?: number
}): StudySessionResponse {
  const resolvedLessonId =
    params?.lessonId && mockLessonCards[String(params.lessonId)] ? params.lessonId : 1001
  const userDeckId = params?.userDeckId
  const userDeck = userDeckId != null ? findDeckById(mockDeckTree.tree ?? [], String(userDeckId)) : null
  const cards =
    userDeck != null
      ? collectLessonIds(userDeck).flatMap((lessonId) => buildSessionCards(lessonId))
      : buildSessionCards(resolvedLessonId)
  const reviewCards = cards.filter((card) => !isNewCard(card))
  const newCards = cards.filter((card) => isNewCard(card))

  return {
    server_time: formatBusinessIso(new Date()),
    session_date: formatBusinessIso(new Date()).slice(0, 10),
    scope: {
      lesson_id: userDeck ? null : resolvedLessonId,
      user_deck_id: userDeckId ?? null,
      source_ids: userDeck ? [] : lessonSourceScope[resolvedLessonId] ?? [1],
    },
    quota: {
      daily_new_limit: 10,
      daily_review_limit: 20,
      new_used: 0,
      review_used: 0,
      new_remaining: Math.max(0, 10 - newCards.length),
      review_remaining: Math.max(0, 20 - reviewCards.length),
    },
    summary: {
      new_cards: newCards.length,
      new_remaining: Math.max(0, 10 - newCards.length),
      review_remaining: Math.max(0, 20 - reviewCards.length),
      due_count: reviewCards.filter((card) => card.due_at).length,
    },
    lesson_name:
      userDeck?.name ?? mockLessonCards[String(resolvedLessonId)]?.lessonName ?? '学习任务',
    cards,
  }
}

export function getMockRatingLabel(rating: FsrsRating): RatingLabel {
  return ratingLabelMap[rating]
}

export function buildMockRatingSrs(rating: FsrsRating) {
  const nextDueHours: Record<FsrsRating, number> = {
    1: 0.5,
    2: 6,
    3: 24,
    4: 96,
  }
  const nextState: FsrsState = rating === 1 ? 'relearning' : rating === 2 ? 'learning' : 'review'

  return {
    state: nextState,
    difficulty: rating === 1 ? 0.72 : rating === 2 ? 0.56 : rating === 3 ? 0.41 : 0.28,
    stability: rating === 1 ? 0.4 : rating === 2 ? 2.1 : rating === 3 ? 5.8 : 9.4,
    is_new_card: false,
    last_review_at: formatBusinessIso(new Date()),
    due_at: formatBusinessIso(
      new Date(Date.now() + nextDueHours[rating] * 60 * 60 * 1000),
    ),
  }
}
