import { useStudyStore } from '@/stores/study'
import { buildMockStudySession } from '@/services/mock/study'
import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { nextTick, type Ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fetchStudySession,
  getOSSSignedUrl,
  getSTSToken,
  listStudySubmissions,
  pollSubmissionResult,
  submitRating,
  submitReviewAsync,
} from '@/services/api/study'
import { __mockRealtimeAsr } from '@/composables/useRealtimeAsr'
import { mountWithApp } from '../../helpers/mountWithApp'
import StudySessionView from '@/views/StudySessionView.vue'

const { ossPutMock } = vi.hoisted(() => ({
  ossPutMock: vi.fn(),
}))

declare module '@/composables/useRealtimeAsr' {
  export const __mockRealtimeAsr: {
    status: Ref<'idle' | 'connecting' | 'streaming' | 'finalizing' | 'ready' | 'failed'>
    partialTranscript: Ref<string>
    finalTranscript: Ref<string>
    realtimeSessionId: Ref<string | null>
    errorCode: Ref<string | null>
    errorMessage: Ref<string | null>
    connect: ReturnType<typeof vi.fn>
    appendAudioChunk: ReturnType<typeof vi.fn>
    commit: ReturnType<typeof vi.fn>
    endSession: ReturnType<typeof vi.fn>
    reset: ReturnType<typeof vi.fn>
  }
}

vi.mock('ali-oss', () => ({
  default: class MockOSS {
    put = ossPutMock

    signatureUrl(path: string) {
      return `https://oss.example/${path}`
    }
  },
}))

vi.mock('@/services/api/study', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/study')>(
    '@/services/api/study',
  )

  return {
    ...actual,
    fetchStudySession: vi.fn(),
    getOSSSignedUrl: vi.fn(),
    getSTSToken: vi.fn(),
    listStudySubmissions: vi.fn(),
    pollSubmissionResult: vi.fn(),
    submitRating: vi.fn(),
    submitReviewAsync: vi.fn(),
  }
})

vi.mock('@/composables/useRealtimeAsr', async () => {
  const { ref } = await import('vue')

  const state = {
    status: ref<'idle' | 'connecting' | 'streaming' | 'finalizing' | 'ready' | 'failed'>('idle'),
    partialTranscript: ref(''),
    finalTranscript: ref(''),
    realtimeSessionId: ref<string | null>(null),
    errorCode: ref<string | null>(null),
    errorMessage: ref<string | null>(null),
    connect: vi.fn(async (lessonId: number, cardId: number) => {
      state.status.value = 'streaming'
      state.realtimeSessionId.value = `mock-session-${lessonId}-${cardId}`
      return true
    }),
    appendAudioChunk: vi.fn(),
    commit: vi.fn(async () => true),
    endSession: vi.fn(() => {
      state.status.value = 'idle'
    }),
    reset: vi.fn(() => {
      state.status.value = 'idle'
      state.partialTranscript.value = ''
      state.finalTranscript.value = ''
      state.realtimeSessionId.value = null
      state.errorCode.value = null
      state.errorMessage.value = null
    }),
  }

  return {
    __mockRealtimeAsr: state,
    useRealtimeAsr: () => state,
  }
})

function createStudyRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/study/:lessonId',
        component: StudySessionView,
      },
      {
        path: '/library',
        component: { template: '<div />' },
      },
      {
        path: '/summary/:lessonId',
        component: { template: '<div />' },
      },
    ],
  })
}

function mountStudySessionView(
  router: ReturnType<typeof createStudyRouter>,
  options: { renderReviewUI?: boolean } = {},
) {
  const { renderReviewUI = false } = options

  return mountWithApp(StudySessionView, {
    pinia: {
      stubActions: false,
    },
    global: {
      plugins: [router],
      stubs: {
        ...(renderReviewUI
          ? {
              GradeButtons: { template: '<div data-testid="grade-buttons-stub" />' },
              RetroCard: { template: '<div><slot /></div>' },
              StudyAudioPlayer: { template: '<div data-testid="study-audio-player-stub" />' },
              SummaryModal: { template: '<div data-testid="summary-modal-stub" />' },
              WordExplanation: { template: '<div data-testid="word-explanation-stub" />' },
            }
          : {
              CardBack: { template: '<div data-testid="card-back-stub" />' },
              RetroCard: { template: '<div><slot /></div>' },
              StudyTaskNav: { template: '<div data-testid="study-task-nav-stub" />' },
              SummaryModal: { template: '<div data-testid="summary-modal-stub" />' },
              WordExplanation: { template: '<div data-testid="word-explanation-stub" />' },
            }),
      },
    },
  })
}

describe('StudySessionView', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_POLLING_INTERVAL', '10')
    vi.stubEnv('VITE_POLLING_TIMEOUT', '1000')

    vi.mocked(fetchStudySession).mockResolvedValue({
      data: buildMockStudySession(1001),
    } as Awaited<ReturnType<typeof fetchStudySession>>)
    vi.mocked(listStudySubmissions).mockResolvedValue({
      data: [],
    } as Awaited<ReturnType<typeof listStudySubmissions>>)
    vi.mocked(getOSSSignedUrl).mockReset()
    vi.mocked(getSTSToken).mockReset()
    vi.mocked(pollSubmissionResult).mockReset()
    vi.mocked(submitRating).mockReset()
    vi.mocked(submitReviewAsync).mockReset()
    ossPutMock.mockReset()

    __mockRealtimeAsr.reset()
    __mockRealtimeAsr.connect.mockClear()
    __mockRealtimeAsr.appendAudioChunk.mockClear()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('uses the same queue counts as word practice and updates from ratings without a progress bar', async () => {
    const session = buildMockStudySession(1001)
    const sample = session.cards[0]!
    const due = new Date(Date.now() - 60_000).toISOString()
    const future = new Date(Date.now() + 86_400_000).toISOString()
    session.cards = [
      { ...sample, id: 2001, is_new_card: true, card_state: 'learning', last_review_at: null },
      { ...sample, id: 2002, is_new_card: false, card_state: 'learning', due_at: due },
      { ...sample, id: 2003, is_new_card: false, card_state: 'relearning', due_at: future },
      { ...sample, id: 2004, is_new_card: false, card_state: 'review', due_at: due },
      { ...sample, id: 2005, is_new_card: false, card_state: 'review', due_at: future },
    ]
    vi.mocked(fetchStudySession).mockResolvedValue({ data: session } as Awaited<ReturnType<typeof fetchStudySession>>)
    const router = createStudyRouter()
    await router.push('/study/1001')
    const wrapper = mountStudySessionView(router)
    await flushPromises()
    const counts = () => wrapper.get('header [aria-label="剩余卡片"]').findAll('dd').map(value => Number(value.text()))
    expect(wrapper.get('[aria-label="剩余卡片"]').findAll('dt').map(label => label.text())).toEqual(['未学习', '学习中', '待复习'])
    expect(counts()).toEqual([1, 2, 1])
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('已练')
    const store = useStudyStore()
    store.submissionId = 9001
    for (const [state, expected] of [['learning', [0, 3, 1]], ['review', [0, 2, 1]]] as const) {
      vi.mocked(submitRating).mockResolvedValueOnce({ data: { srs: { state, due_at: future, is_new_card: false } } } as Awaited<ReturnType<typeof submitRating>>)
      await store.submitCardRating(state === 'learning' ? 1 : 3)
      await nextTick()
      expect(counts()).toEqual(expected)
    }
    wrapper.unmount()
  })

  it('blocks recording while speech playback is active and allows it afterwards', async () => {
    const session = buildMockStudySession(1001)
    session.cards[0]!.audio_path = ''
    vi.mocked(fetchStudySession).mockResolvedValue({ data: session } as Awaited<ReturnType<typeof fetchStudySession>>)
    const router = createStudyRouter()

    await router.push('/study/1001')
    await router.isReady()

    const wrapper = mountStudySessionView(router)

    await flushPromises()

    await wrapper.get('[data-testid="play-reference-audio"]').trigger('click')
    await flushPromises()

    const recordToggle = wrapper.get('[data-testid="record-toggle"]')
    await vi.waitFor(() => {
      expect(recordToggle.attributes('disabled')).toBeDefined()
    })
    expect(wrapper.text()).toContain(
      '建议完整听完原音频之后再录音',
    )

    await recordToggle.trigger('click')
    expect(__mockRealtimeAsr.connect).not.toHaveBeenCalled()

    window.speechSynthesis.cancel()
    await nextTick()
    await flushPromises()

    expect(recordToggle.attributes('disabled')).toBeUndefined()

    await recordToggle.trigger('click')
    await flushPromises()

    expect(__mockRealtimeAsr.connect).toHaveBeenCalledWith(1001, 2001)
    expect(recordToggle.text()).toContain('停止')
  })

  it('preserves completed feedback and transcription when switching away and back to a card', async () => {
    const completedTranscript = 'The quick brown fox jumps over the lazy dog.'
    const completedFeedback = '发音整体清晰，注意连读部分。'
    const compactTranscript = completedTranscript.replace(/\s+/g, '')
    const studySession = buildMockStudySession(1001)
    const secondCard = studySession.cards[1]!

    vi.mocked(fetchStudySession).mockResolvedValue({
      data: studySession,
    } as Awaited<ReturnType<typeof fetchStudySession>>)
    vi.mocked(getSTSToken).mockResolvedValue({
      data: {
        access_key_id: 'STS.mock123',
        access_key_secret: 'mock-secret',
        security_token: 'mock-token',
        expiration: '2099-01-01T00:00:00+08:00',
        bucket: 'langear',
        region: 'oss-cn-shanghai',
        upload_prefix: 'test/recordings',
      },
    } as Awaited<ReturnType<typeof getSTSToken>>)
    ossPutMock.mockResolvedValue({
      res: {
        status: 200,
      },
    })
    vi.mocked(submitReviewAsync).mockResolvedValue({
      data: {
        submission_id: 9001,
        status: 'processing',
      },
    } as Awaited<ReturnType<typeof submitReviewAsync>>)
    vi.mocked(pollSubmissionResult).mockResolvedValue({
      data: {
        submission_id: 9001,
        status: 'completed',
        result_type: 'single',
        realtime_session_id: 'mock-session-1001-2001',
        transcription: {
          text: completedTranscript,
          timestamps: [],
        },
        feedback: {
          pronunciation: completedFeedback,
          completeness: '内容完整，未遗漏关键信息。',
          fluency: '语速适中，部分句末有停顿。',
          suggestions: [],
          issues: [],
        },
        oss_audio_path: 'recordings/2026-03-24/2001_123456.webm',
      },
    } as Awaited<ReturnType<typeof pollSubmissionResult>>)
    vi.mocked(getOSSSignedUrl).mockResolvedValue('https://oss.example/recording.webm')

    const router = createStudyRouter()
    await router.push('/study/1001')
    await router.isReady()

    const wrapper = mountStudySessionView(router, { renderReviewUI: true })
    await flushPromises()

    const recordToggle = wrapper.get('[data-testid="record-toggle"]')
    await recordToggle.trigger('click')
    await flushPromises()

    expect(__mockRealtimeAsr.connect).toHaveBeenCalledWith(1001, 2001)

    __mockRealtimeAsr.finalTranscript.value = completedTranscript
    await nextTick()
    await flushPromises()

    await recordToggle.trigger('click')
    await flushPromises()

    await wrapper.get('[data-testid="flip-button"]').trigger('click')
    await flushPromises()

    await vi.waitFor(() => {
      expect(ossPutMock).toHaveBeenCalledTimes(1)
      expect(submitReviewAsync).toHaveBeenCalledTimes(1)
      expect(pollSubmissionResult).toHaveBeenCalledWith(9001)
      expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
    })

    expect(wrapper.get('[data-testid="card-back-container"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="feedback-panel"]').text()).toContain(completedFeedback)
    expect(wrapper.get('[data-testid="transcription-result"]').text().replace(/\s+/g, '')).toContain(
      compactTranscript,
    )

    expect(wrapper.find('[data-testid="study-task-nav"]').exists()).toBe(false)
    useStudyStore().selectCard(1)
    await flushPromises()

    expect(wrapper.get('[aria-label="剩余卡片"]').exists()).toBe(true)
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="card-front-container"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="feedback-panel"]').exists()).toBe(false)

    useStudyStore().selectCard(0)
    await flushPromises()

    await vi.waitFor(() => {
      expect(wrapper.get('[data-testid="card-back-container"]').exists()).toBe(true)
      expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
      expect(wrapper.get('[data-testid="feedback-panel"]').text()).toContain(completedFeedback)
      expect(
        wrapper.get('[data-testid="transcription-result"]').text().replace(/\s+/g, ''),
      ).toContain(compactTranscript)
    })
  })
})
