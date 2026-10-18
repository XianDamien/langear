import http from '../http'
import { reviewHttp } from '@/services/review'
import type {
  DeckTreeResponse,
  MyCourseLessonsResponse,
} from '@/types/api'

export function fetchDeckTree() {
  return http.get<DeckTreeResponse>('/decks/tree')
}

export function fetchLessonCards(lessonId: string) {
  return http.get<{ lesson_id: number; cards: { id: number; front_text: string | null; back_text: string | null }[] }>(`/decks/${lessonId}/cards`)
}

export function fetchMyCourseLessons() {
  return reviewHttp.get<MyCourseLessonsResponse>('/review/legacy-lessons')
}

export function updateMyCourseLessons(lessonIds: number[]) {
  return reviewHttp.put<MyCourseLessonsResponse>('/review/legacy-lessons', {
    lesson_ids: lessonIds,
  })
}

export function fetchMyCourseCards(lessonId: string) {
  return reviewHttp.get<{ card_ids: number[] | null }>(`/review/legacy-lessons/${lessonId}/study-selection`)
}

export function updateMyCourseCards(lessonId: string, cardIds: number[] | null) {
  return reviewHttp.put<{ card_ids: number[] | null; lesson_ids: number[] }>(`/review/legacy-lessons/${lessonId}/study-selection`, { card_ids: cardIds })
}
