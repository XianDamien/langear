import http from '../http'
import type {
  DeckTreeResponse,
  LessonCardsResponse,
  UserDeckListResponse,
  UserDeckSelectionResponse,
} from '@/types/api'

export function fetchDeckTree() {
  return http.get<DeckTreeResponse>('/decks/tree')
}

export function fetchLessonCards(lessonId: string) {
  return http.get<LessonCardsResponse>(`/decks/${lessonId}/cards`)
}

export function fetchUserDecks() {
  return http.get<UserDeckListResponse>('/user-decks')
}

export function updateUserDeckSelection(originDeckIds: number[]) {
  return http.put<UserDeckSelectionResponse>('/user-decks/selection', {
    origin_deck_ids: originDeckIds,
  })
}
