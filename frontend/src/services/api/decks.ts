import http from '../http'
import type {
  DeckTreeResponse,
  LessonCardsResponse,
  MyCourseLessonsResponse,
} from '@/types/api'

export function fetchDeckTree() {
  return http.get<DeckTreeResponse>('/decks/tree')
}

export function fetchLessonCards(lessonId: string) {
  return http.get<LessonCardsResponse>(`/decks/${lessonId}/cards`)
}

export function fetchMyCourseLessons() {
  return http.get<MyCourseLessonsResponse>('/my-courses/lessons')
}

export function updateMyCourseLessons(lessonIds: number[]) {
  return http.put<MyCourseLessonsResponse>('/my-courses/lessons', {
    lesson_ids: lessonIds,
  })
}
