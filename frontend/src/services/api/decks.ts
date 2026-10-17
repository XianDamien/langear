import http from '../http'
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
  return http.get<MyCourseLessonsResponse>('/my-courses/lessons')
}

export function updateMyCourseLessons(lessonIds: number[]) {
  return http.put<MyCourseLessonsResponse>('/my-courses/lessons', {
    lesson_ids: lessonIds,
  })
}

export function fetchMyCourseCards(lessonId: string) {
  return http.get<{ card_ids: number[] | null }>(`/my-courses/lessons/${lessonId}/cards`)
}

export function updateMyCourseCards(lessonId: string, cardIds: number[] | null) {
  return http.put<{ card_ids: number[] | null; lesson_ids: number[] }>(`/my-courses/lessons/${lessonId}/cards`, { card_ids: cardIds })
}
