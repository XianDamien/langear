import type {
  FsrsRating,
  Rating,
  RatingLabel,
  FsrsState,
  DailyStats,
  Deck,
  Card,
} from './domain'

export interface ApiError {
  code: string
  message: string
  request_id: string
}

export interface CurrentUser {
  id: number
  username: string
  email?: string | null
  email_verified?: boolean
  email_verified_at?: string | null
}

export interface AuthResponse {
  access_token: string
  token_type: 'bearer'
  user: CurrentUser
}

export interface SubmissionDisplayError {
  errorCode: string | null
  errorMessage: string
  requestId?: string | null
}

export interface STSToken {
  access_key_id: string
  access_key_secret: string
  security_token: string
  expiration: string
  bucket: string
  region: string
  upload_prefix: string
}

export type SubmissionStatus = 'processing' | 'completed' | 'failed'
export type ProgressState = 'asr_completed' | 'ai_processing'

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
}

export interface FeedbackIssue {
  problem: string
  suggestion?: string | null
  target_word?: string | null
  ipa?: string | null
  timestamp?: number | null
}

export interface SrsSnapshot {
  state: FsrsState
  difficulty: number
  stability: number
  due?: string
  due_at?: string
  is_new_card?: boolean
  last_review_at?: string | null
}

export interface SubmitReviewRequest {
  lesson_id: number
  card_id: number
  oss_audio_path: string
  realtime_session_id: string
  user_deck_id?: number | null
  // Optional client-side realtime transcript fallback (used by mock adapter).
  transcription_text?: string
}

export interface SubmitReviewResponseAsync {
  submission_id: number
  status: 'processing'
}

export interface PollingResponseProcessing {
  submission_id: number
  status: 'processing'
  progress?: ProgressState
}

export interface PollingResponseCompleted {
  submission_id: number
  status: 'completed'
  result_type: 'single'
  realtime_session_id?: string
  transcription: TranscriptionResult
  feedback: {
    // V2 兼容字段
    pronunciation?: string
    completeness?: string
    fluency?: string
    suggestions?: FeedbackSuggestion[]
    
    // V3 新增字段
    overall_rating?: string
    issues: FeedbackIssue[]
    'alternative phrases and sentences'?: string[]
  }
  srs?: SrsSnapshot
  oss_audio_path?: string | null
}

export interface SubmitRatingRequest {
  rating: FsrsRating | RatingLabel
}

export interface SubmitRatingResponse {
  submission_id: number
  rating: FsrsRating | RatingLabel
  rating_label?: RatingLabel
  srs: SrsSnapshot
}

export interface PollingResponseFailed {
  submission_id: number
  status: 'failed'
  error_code: string
  error_message: string
}

export type PollingResponse =
  | PollingResponseProcessing
  | PollingResponseCompleted
  | PollingResponseFailed

export interface StudySubmissionListItem {
  submission_id: number
  card_id: number | null
  lesson_id: number
  user_deck_id: number | null
  status: SubmissionStatus
  error_code: string | null
  error_message: string | null
  created_at: string
  oss_audio_path: string | null
  transcription: TranscriptionResult | null
  feedback: PollingResponseCompleted['feedback'] | null
}

export interface StudySubmissionListParams {
  lesson_id?: number
  user_deck_id?: number
  card_id?: number
}

/**
 * @deprecated 使用 SubmitReviewRequest (v2.0) 替代
 */
export interface SubmitReviewRequestV1 {
  lessonId: number
  cardId: number
  rating: Rating
  userAudio: string
  audioFormat: 'wav' | 'webm' | 'mp3'
}

/**
 * @deprecated 使用 PollingResponseCompleted (v2.0) 替代
 */
export interface SubmitReviewResponse {
  reviewLogId: number
  resultType: 'single'
  transcription: string
  feedback: {
    pronunciation: string
    completeness: string
    fluency: string
    suggestions: string[]
    overallScore: number
  }
  srs: SrsSnapshot
}
export interface StudySessionScope {
  source_ids?: number[]
  source_scope?: number[]
  lesson_id?: number | null
  user_deck_id?: number | null
}

export interface StudySessionQuota {
  daily_new_limit?: number
  daily_review_limit?: number
  new_remaining?: number
  review_remaining?: number
  new_used?: number
  review_used?: number
  [key: string]: number | null | undefined
}

export interface StudySessionSummary {
  new_remaining: number
  review_remaining: number
  due_count: number
  new_cards?: number
}

export interface StudySessionCardResponse {
  id: string | number
  lesson_id: string | number
  card_index: number
  front_text: string
  back_text: string
  audio_path?: string
  oss_audio_path?: string | null
  card_state: FsrsState
  due_at?: string | null
  is_new_card?: boolean
  last_review_at?: string | null
}

export interface StudySessionResponse {
  server_time: string
  session_date: string
  scope: StudySessionScope
  quota: StudySessionQuota
  summary: StudySessionSummary
  cards: StudySessionCardResponse[]
  lesson_name?: string
  lessonName?: string
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
  }
  weeklyTrend: { name: string; sentences: number }[]
  heatmap: DailyStats[]
}

export interface LessonSummary {
  lessonId: string
  overallScore: number
  overallComment: string
  frequentIssues: string[]
  improvements: string[]
  cardResults: {
    cardId: string
    score: number
    feedback: string
  }[]
}

export interface SettingsData {
  desiredRetention: number
  learningSteps: string
  relearningSteps: string
  maximumInterval: number
  defaultSourceScope: string
}

export interface DeckTreeLessonNode {
  id: number
  title: string
  total_cards: number
  completed_cards: number
  due_cards: number
  new_cards?: number
}

export interface DeckTreeUnitNode {
  id: number
  title: string
  lessons: DeckTreeLessonNode[]
}

export interface DeckTreeSourceNode {
  id: number
  title: string
  units: DeckTreeUnitNode[]
}

export interface DeckTreeResponse {
  tree?: Deck[]
  sources?: DeckTreeSourceNode[]
}

export interface LessonCardsResponse {
  lessonId: string
  lessonName: string
  cards: Card[]
}

export interface MyCourseLessonsResponse {
  lesson_ids: number[]
}

export interface UserDeckSummary {
  id: number
  origin_deck_id: number
  title: string
  scope_type: 'source' | 'unit' | 'lesson'
  total_count: number
  new_count: number
  learning_count: number
  review_count: number
}

export interface UserDeckListResponse {
  user_decks: UserDeckSummary[]
}

export interface UserDeckSelectionResponse extends UserDeckListResponse {
  origin_deck_ids: number[]
}
