import { normalizeLessonIds } from '@/utils/deckSelection'

const STORAGE_KEY = 'mock_my_course_lesson_ids'
const DEFAULT_LESSON_IDS = [1001, 2001]

export function readMockMyCourseLessonIds(): number[] {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (!stored) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(DEFAULT_LESSON_IDS))
    return DEFAULT_LESSON_IDS
  }

  return normalizeLessonIds(JSON.parse(stored) as number[])
}

export function writeMockMyCourseLessonIds(lessonIds: number[]): number[] {
  const normalized = normalizeLessonIds(lessonIds)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  return normalized
}
