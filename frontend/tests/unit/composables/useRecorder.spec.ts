import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { useRecorder } from '@/composables/useRecorder'

const { createRecordingSession } = vi.hoisted(() => ({ createRecordingSession: vi.fn() }))

vi.mock('@/adapters/browser/recording', () => ({
  createRecordingSession,
  RecordingStartError: class RecordingStartError extends Error {
    code: string

    constructor(code: string, message: string) {
      super(message)
      this.code = code
    }
  },
}))

function mountRecorder() {
  let recorder!: ReturnType<typeof useRecorder>
  const wrapper = mount(defineComponent({
    setup() {
      recorder = useRecorder()
      return () => null
    },
  }))

  return { recorder, wrapper }
}

function createSession() {
  let onStop = () => {}

  return {
    getState: () => 'recording' as const,
    setOnDataAvailable: vi.fn(),
    setOnStop: (handler: () => void) => { onStop = handler },
    start: vi.fn(),
    stop: vi.fn(),
    dispose: vi.fn(),
    finish: () => onStop(),
  }
}

describe('useRecorder', () => {
  it('overwrites the cached recording when a new take starts', async () => {
    const first = createSession()
    const second = createSession()
    createRecordingSession.mockResolvedValueOnce(first).mockResolvedValueOnce(second)
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:first')
    const revokeObjectUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const { recorder, wrapper } = mountRecorder()

    await recorder.startRecording()
    first.finish()
    expect(recorder.recordingBlob.value).toBeInstanceOf(Blob)
    expect(recorder.audioUrl.value).toBe('blob:first')

    await recorder.startRecording()
    expect(recorder.recordingBlob.value).toBeNull()
    expect(recorder.audioUrl.value).toBeNull()
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:first')
    wrapper.unmount()
  })
})
