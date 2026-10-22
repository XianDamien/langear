import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ResourceCard } from '@/services/content'

const { clearTranscript, play, realtimeFinal } = vi.hoisted(() => ({
  clearTranscript: vi.fn(),
  play: vi.fn(),
  realtimeFinal: { value: 'previous transcript' },
}))

vi.mock('@/composables/useRealtimeAsr', () => ({
  useRealtimeAsr: () => ({
    status: { value: 'ready' },
    partialTranscript: { value: '' },
    finalTranscript: realtimeFinal,
    realtimeSessionId: { value: 'session-id' },
    connectReview: vi.fn(),
    appendAudioChunk: vi.fn(),
    commit: vi.fn(),
    reset: vi.fn(),
    clearTranscript,
  }),
}))

vi.mock('@/composables/useAudioPlayer', () => ({
  useAudioPlayer: () => ({ isPlaying: { value: false }, play, stop: vi.fn() }),
}))

vi.mock('@/composables/useRecorder', () => ({
  useRecorder: () => ({
    isRecording: { value: false },
    recordingBlob: { value: null },
    audioUrl: { value: null },
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    reset: vi.fn(),
  }),
}))

vi.mock('@/services/review', async importOriginal => ({
  ...(await importOriginal<typeof import('@/services/review')>()),
  reviewHttp: {
    defaults: { baseURL: '/api/v1' },
    get: vi.fn(async () => ({ data: { url: '/reference.wav' } })),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

import SentencePracticeCard from '@/components/review/SentencePracticeCard.vue'
import RetellingCard from '@/components/study/cards/RetellingCard.vue'

const card = {
  id: 'card-1',
  card_template_key: 'sentence_retelling',
  front: { reference_audio: 'audio-1' },
  back: { english: 'Hello' },
} as unknown as ResourceCard

beforeEach(() => {
  clearTranscript.mockClear()
  play.mockClear()
  realtimeFinal.value = 'previous transcript'
})

describe('SentencePracticeCard', () => {
  it('clears the previous take transcript when the reference is replayed', async () => {
    const wrapper = mount(SentencePracticeCard, { props: { card, isFlipped: false } })
    await flushPromises()

    wrapper.findComponent(RetellingCard).vm.$emit('playReference')
    await flushPromises()

    expect(clearTranscript).toHaveBeenCalledTimes(1)
    expect(play).toHaveBeenCalledWith('/reference.wav')
    wrapper.unmount()
  })
})
