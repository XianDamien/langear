export interface ApiError {
  code: string
  message: string
  request_id: string
  details?: Record<string, unknown>
}

export type FeedbackDimension = 'pronunciation' | 'completeness' | 'fluency'

export interface WordTimestamp {
  word: string
  start: number
  end: number
}

export interface TranscriptionResult {
  text: string
  timestamps: WordTimestamp[]
}

export interface FeedbackSuggestion {
  text: string
  target_word?: string | null
  timestamp?: number | null
  dimension?: FeedbackDimension | null
}

export interface FeedbackIssue {
  problem: string
  suggestion?: string | null
  target_word?: string | null
  ipa?: string | null
  timestamp?: number | null
}

export interface AttemptFeedback {
  pronunciation?: string
  completeness?: string
  fluency?: string
  suggestions?: FeedbackSuggestion[]
  overall_rating?: string
  issues: FeedbackIssue[]
  'alternative phrases and sentences'?: string[]
}

export interface PollingResponseCompleted {
  feedback: AttemptFeedback
}

export interface DashboardData {
  stats: {
    points: number
    reviewsPending: number
    streakDays: number
    dailyGoal: number
    dailyDone: number
    todayNew: number
    todayReview: number
    todayDone: number
    newDue?: number
    reviewDue?: number
    learningDue?: number
    localDate?: string
  }
  weeklyTrend: { name: string; sentences: number }[]
  heatmap: { date: string; count: number }[]
  leaderboard: { rank: number; name: string; points: number; is_user?: boolean }[]
}

export interface SettingsData {
  deckId?: string
  schedulingEnabled?: boolean
  deckTitle?: string
  dailyNewLimit?: number
  dailyReviewLimit?: number
  newCardGatherOrder?: string | null
  newCardSortOrder?: string | null
  effectiveNewCardGatherOrder?: string
  effectiveNewCardSortOrder?: string
  desiredRetention: number
  learningSteps: string
  relearningSteps: string
  maximumInterval: number
  defaultDeckScope: string
}

export interface CollectionSettingsData {
  new_limit: number
  review_limit: number
  desired_retention: number
  learning_steps: number[]
  relearning_steps: number[]
  maximum_review_interval: number
  default_deck_scope: string[]
}

export interface DeckSettingsData {
  deck_id: string
  deck_title: string
  scheduling_enabled: boolean
  new_card_order_overrides: {
    new_card_gather_order: string | null
    new_card_sort_order: string | null
  }
  daily_new_limit: number
  daily_review_limit: number
  desired_retention: number
  maximum_interval: number
  learning_steps: number[]
  relearning_steps: number[]
  new_card_gather_order?: string | null
  new_card_sort_order?: string | null
}

export type BackendSettingsData =
  | Partial<CollectionSettingsData>
  | Partial<DeckSettingsData>
