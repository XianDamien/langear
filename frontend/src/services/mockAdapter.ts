import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { mockDashboardData } from './mock/dashboard'
import { mockDeckTree, mockLessonCards } from './mock/decks'
import {
  buildMockUserDecks,
  readMockUserDeckOriginIds,
  writeMockUserDeckOriginIds,
} from './mock/myCourses'
import { mockLessonSummary } from './mock/summary'
import { mockSettings } from './mock/settings'
import {
  buildMockRatingSrs,
  buildMockStudySession,
  getMockRatingLabel,
} from './mock/study'
import type { SettingsData } from '@/types/api'
import type { FsrsRating } from '@/types/domain'
import { formatBusinessIso } from '@/utils/businessTime'

const SUBMISSION_STORAGE_PREFIX = 'submission_'

function delay(ms = 400): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

interface MockResponse {
  __mock: true
  data?: unknown
  error?: { code: string; message: string; request_id: string }
  status?: number
}

function mockResolve(data: unknown): MockResponse {
  return { __mock: true, data }
}

function mockError(code: string, message: string, status = 404): MockResponse {
  return { __mock: true, error: { code, message, request_id: 'mock' }, status }
}

function parseBody(config: InternalAxiosRequestConfig): unknown {
  return typeof config.data === 'string' ? JSON.parse(config.data) : config.data
}

function readStoredSubmissions() {
  const records: Array<Record<string, unknown>> = []
  for (let index = 0; index < sessionStorage.length; index += 1) {
    const key = sessionStorage.key(index)
    if (!key?.startsWith(SUBMISSION_STORAGE_PREFIX)) continue
    const rawValue = sessionStorage.getItem(key)
    if (!rawValue) continue
    records.push(JSON.parse(rawValue) as Record<string, unknown>)
  }
  return records
}

function getParam(config: InternalAxiosRequestConfig, key: string): string | undefined {
  const directValue = config.params?.[key]
  if (directValue !== undefined && directValue !== null) {
    return String(directValue)
  }

  const url = config.url || ''
  const queryIndex = url.indexOf('?')
  if (queryIndex === -1) return undefined

  const searchParams = new URLSearchParams(url.slice(queryIndex + 1))
  return searchParams.get(key) ?? undefined
}

function normalizeUrl(rawUrl: string): string {
  const pathname = new URL(rawUrl, 'http://mock.local').pathname
  return pathname.replace(/^\/api\/v1/, '') || pathname
}

async function matchRoute(config: InternalAxiosRequestConfig): Promise<MockResponse | null> {
  const url = normalizeUrl(config.url || '')
  const method = (config.method || 'get').toLowerCase()

  if (method === 'post' && (url === '/auth/login' || url === '/auth/register')) {
    await delay(200)
    const body = parseBody(config) as { username?: string; email?: string; invitation_code?: string }
    if (url === '/auth/register' && !body.invitation_code?.trim()) {
      return mockError('AUTH_REGISTER_FAILED', '邀请码不能为空', 400)
    }
    const username = body.username?.trim() || 'mock-user'
    return mockResolve({
      access_token: `mock-token-${username}`,
      token_type: 'bearer',
      user: {
        id: 1,
        username,
        email: body.email || null,
        email_verified: false,
        email_verified_at: null,
      },
    })
  }

  if (method === 'get' && url === '/auth/me') {
    await delay(100)
    return mockResolve({
      id: 1,
      username: 'mock-user',
      email: null,
      email_verified: false,
      email_verified_at: null,
    })
  }

  if (method === 'get' && url === '/dashboard') {
    await delay()
    return mockResolve(mockDashboardData)
  }

  if (method === 'get' && url === '/decks/tree') {
    await delay()
    return mockResolve(mockDeckTree)
  }

  if (method === 'get' && url === '/user-decks') {
    await delay()
    return mockResolve({
      user_decks: buildMockUserDecks(readMockUserDeckOriginIds()),
    })
  }

  if (method === 'put' && url === '/user-decks/selection') {
    await delay(200)
    const body = parseBody(config) as { origin_deck_ids?: number[] }
    const originDeckIds = writeMockUserDeckOriginIds(body.origin_deck_ids || [])
    return mockResolve({
      origin_deck_ids: originDeckIds,
      user_decks: buildMockUserDecks(originDeckIds),
    })
  }

  const cardsMatch = url.match(/^\/decks\/([^/]+)\/cards$/)
  if (method === 'get' && cardsMatch) {
    await delay()
    const data = mockLessonCards[cardsMatch[1]!]
    return data ? mockResolve(data) : mockError('NOT_FOUND', '课程不存在')
  }

  if (method === 'get' && url.startsWith('/study/session')) {
    await delay()
    const lessonId = Number(getParam(config, 'lesson_id'))
    const userDeckId = Number(getParam(config, 'user_deck_id'))
    return mockResolve(
      buildMockStudySession({
        lessonId: Number.isFinite(lessonId) ? lessonId : undefined,
        userDeckId: Number.isFinite(userDeckId) ? userDeckId : undefined,
      }),
    )
  }

  if (method === 'get' && url === '/oss/sts-token') {
    await delay()
    return mockResolve({
      access_key_id: 'STS.mock123',
      access_key_secret: 'mock-secret',
      security_token: 'mock-token',
      expiration: formatBusinessIso(new Date(Date.now() + 3600000)),
      bucket: 'langear',
      region: 'oss-cn-shanghai',
      upload_prefix: 'recordings',
    })
  }

  if (method === 'post' && url === '/study/submissions') {
    await delay(200)
    const body = parseBody(config) as {
      lesson_id?: number
      card_id?: number
      user_deck_id?: number | null
      oss_audio_path?: string
      realtime_session_id?: string
      transcription_text?: string
    }
    if (!body?.realtime_session_id) {
      return mockError('REALTIME_SESSION_NOT_FOUND', 'Missing realtime_session_id', 400)
    }

    const submissionId = Math.floor(Math.random() * 10000)
    sessionStorage.setItem(
      `submission_${submissionId}`,
      JSON.stringify({
        submission_id: submissionId,
        lesson_id: body.lesson_id ?? null,
        card_id: body.card_id ?? null,
        user_deck_id: body.user_deck_id ?? null,
        status: 'processing',
        timestamp: Date.now(),
        created_at: formatBusinessIso(new Date()),
        oss_audio_path: typeof body.oss_audio_path === 'string' ? body.oss_audio_path : null,
        realtime_session_id: body.realtime_session_id,
        transcription_text:
          typeof body.transcription_text === 'string' ? body.transcription_text.trim() : '',
      }),
    )
    return mockResolve({
      submission_id: submissionId,
      status: 'processing',
    })
  }

  if (method === 'get' && url === '/study/submissions') {
    await delay(150)
    const lessonId = Number(getParam(config, 'lesson_id'))
    const userDeckIdParam = getParam(config, 'user_deck_id')
    const userDeckId = userDeckIdParam != null ? Number(userDeckIdParam) : null
    const cardIdParam = getParam(config, 'card_id')
    const cardId = cardIdParam != null ? Number(cardIdParam) : null

    const items = readStoredSubmissions()
      .filter((item) =>
        userDeckId != null
          ? Number(item.user_deck_id) === userDeckId
          : Number(item.lesson_id) === lessonId,
      )
      .filter((item) => (cardId == null ? true : Number(item.card_id) === cardId))
      .sort((left, right) => String(right.created_at).localeCompare(String(left.created_at)))
      .map((item) => ({
        submission_id: Number(item.submission_id),
        card_id: item.card_id != null ? Number(item.card_id) : null,
        lesson_id: Number(item.lesson_id),
        user_deck_id: item.user_deck_id != null ? Number(item.user_deck_id) : null,
        status: String(item.status),
        error_code: item.error_code ?? null,
        error_message: item.error_message ?? null,
        created_at: String(item.created_at),
        oss_audio_path: item.oss_audio_path ?? null,
        transcription: (item.transcription as Record<string, unknown> | undefined) ?? null,
        feedback: (item.feedback as Record<string, unknown> | undefined) ?? null,
      }))

    return mockResolve(items)
  }

  const pollMatch = url.match(/^\/study\/submissions\/(\d+)$/)
  if (method === 'get' && pollMatch) {
    await delay(500)
    const submissionId = pollMatch[1]
    const stored = sessionStorage.getItem(`submission_${submissionId}`)

    if (!stored) {
      return mockError('NOT_FOUND', 'Submission not found', 404)
    }

    const data = JSON.parse(stored)
    const elapsed = Date.now() - data.timestamp

    if (elapsed < 3000) {
      return mockResolve({
        submission_id: Number(submissionId),
        status: 'processing',
        progress: elapsed < 1500 ? 'asr_completed' : 'ai_processing',
      })
    }

    const transcriptText =
      typeof data.transcription_text === 'string' ? data.transcription_text.trim() : ''

    const completedPayload = {
      submission_id: Number(submissionId),
      status: 'completed',
      result_type: 'single',
      realtime_session_id: data.realtime_session_id,
      transcription: {
        text: transcriptText || 'By the way, I hope you are all comfortable.',
        timestamps: [],
      },
      feedback: {
        overall_rating: '整体来说你这句表达是能让人听懂的，内容也基本到位，准确度和发音上面没有太大问题。主要还是流利度上可以再自然一点，尤其是在个别短语前后有停顿，听起来还不够连贯。继续练几遍，把节奏带顺，会更像自然交流。',
        issues: [
          {
            problem: '在“extra seats”前后停顿有点明显，影响了整句的连贯度。',
            suggestion: '把“in extra seats so that”这一小段连起来多练几遍，尽量一口气顺下来。',
            target_word: 'extra seats',
            ipa: null,
            timestamp: 0.8,
          },
          {
            problem: '“squashed”的发音还不够清楚，结尾听起来有点含糊。',
            suggestion: '重点练 /skw/ 和结尾 /t/，先慢读 squashed，再放回整句里练习。',
            target_word: 'squashed',
            ipa: '/skwɒʃt/',
            timestamp: 2.05,
          },
          {
            problem: '开头少了“we”，虽然不太影响理解，但和原句相比不够完整。',
            suggestion: '练习时注意把主语一起带出来，特别是“we have brought in”这一段要成块记忆。',
            target_word: 'we have brought in',
            ipa: null,
            timestamp: 0.55,
          },
        ],
        'alternative phrases and sentences': [
          'We’ve added some extra seats so nobody has to stand.',
          'There are a few extra seats at the back if anyone needs one.',
          'It might be a little crowded at the back, but everyone should be able to sit down.',
        ],
      },
      srs: {
        state: 'review',
        difficulty: 0.3,
        stability: 5.0,
        due: formatBusinessIso(new Date(Date.now() + 86400000 * 3)),
        due_at: formatBusinessIso(new Date(Date.now() + 86400000 * 3)),
        is_new_card: false,
        last_review_at: formatBusinessIso(new Date()),
      },
    }

    sessionStorage.setItem(
      `submission_${submissionId}`,
      JSON.stringify({
        ...data,
        status: 'completed',
      }),
    )
    return mockResolve({
      ...completedPayload,
      oss_audio_path: data.oss_audio_path ?? null,
    })
  }

  const ratingMatch = url.match(/^\/study\/submissions\/(\d+)\/rating$/)
  if (method === 'post' && ratingMatch) {
    await delay(200)
    const body = parseBody(config) as { rating?: FsrsRating }
    const rating = body?.rating

    if (rating !== 1 && rating !== 2 && rating !== 3 && rating !== 4) {
      return mockError('INVALID_RATING', 'rating 必须是 1 | 2 | 3 | 4', 400)
    }

    const stored = sessionStorage.getItem(`submission_${ratingMatch[1]}`)
    if (!stored) {
      return mockError('NOT_FOUND', 'Submission not found', 404)
    }

    return mockResolve({
      submission_id: Number(ratingMatch[1]),
      rating,
      rating_label: getMockRatingLabel(rating),
      srs: buildMockRatingSrs(rating),
    })
  }

  const summaryMatch = url.match(/^\/decks\/([^/]+)\/summary$/)
  if (method === 'get' && summaryMatch) {
    await delay(600)
    return mockResolve(mockLessonSummary(summaryMatch[1]!))
  }

  if (method === 'get' && url === '/settings') {
    await delay()
    return mockResolve({ ...mockSettings })
  }

  if (method === 'put' && url === '/settings') {
    await delay()
    return mockResolve(parseBody(config) as SettingsData)
  }

  return null
}

export function installMockAdapter(http: AxiosInstance) {
  http.interceptors.request.use(async (config) => {
    const mock = await matchRoute(config)
    if (mock) return Promise.reject(mock)
    return config
  })

  http.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error?.__mock) {
        if (error.error) {
          return Promise.reject({
            response: { data: { error: error.error }, status: error.status || 500 },
          })
        }
        return Promise.resolve({ data: error.data, status: 200 })
      }
      return Promise.reject(error)
    },
  )
}
