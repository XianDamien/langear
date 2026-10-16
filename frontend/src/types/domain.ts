export interface Deck {
  origin?: 'core'
  id: string
  name: string
  description: string
  totalCards: number
  newCards: number
  reviewCards: number
  completedCards: number
  parentId?: string
  children?: Deck[]
  type: 'source' | 'unit' | 'lesson'
}

export interface Card {
  id: string
  lessonId?: string
  cardIndex?: number
  frontAudio?: string
  frontText?: string
  backText: string
  backTranslation: string
  notes?: string
  difficulty: number
  ossAudioPath?: string | null
  cardState?: FsrsState
  dueAt?: string | null
  isNewCard?: boolean
  lastReviewAt?: string | null
  grammarInfo?: {
    nouns: string[]
    verbs: string[]
  }
}

export type FsrsRating = 1 | 2 | 3 | 4
export type RatingLabel = 'again' | 'hard' | 'good' | 'easy'
export type Rating = RatingLabel
export type FsrsState = 'learning' | 'review' | 'relearning'

export interface DailyStats {
  date: string
  count: number
}

export interface StudySessionResult {
  cardId: string
  rating: FsrsRating | Rating
  userAudioBlob?: Blob
  responseTime: number
}
