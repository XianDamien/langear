import { describe, expect, it } from 'vitest'
import AudioRecorderPanel from '@/components/study/modules/AudioRecorderPanel.vue'
import { mountWithApp } from '../../helpers/mountWithApp'

describe('AudioRecorderPanel', () => {
  it('shows only the retelling label on the card front', () => {
    const wrapper = mountWithApp(AudioRecorderPanel, {
      props: {
        audioPlaying: false,
        isRecording: false,
        liveTranscript: '',
        userTranscript: '',
        uploadState: 'idle',
        uploadProgress: 0,
      },
    })

    expect(wrapper.text()).toContain('句子复述')
    expect(wrapper.find('[data-testid="retelling-hint"]').exists()).toBe(false)
  })

  it('disables recording when requested by the card', async () => {
    const wrapper = mountWithApp(AudioRecorderPanel, {
      props: {
        audioPlaying: true,
        recordingDisabled: true,
        isRecording: false,
        liveTranscript: '',
        userTranscript: '',
        uploadState: 'idle',
        uploadProgress: 0,
      },
    })

    const button = wrapper.get('[data-testid="record-toggle"]')
    expect(button.attributes('disabled')).toBeDefined()

    await button.trigger('click')
    expect(wrapper.emitted('toggleRecording')).toBeFalsy()
  })

  it('emits recording toggle once playback is idle', async () => {
    const wrapper = mountWithApp(AudioRecorderPanel, {
      props: {
        audioPlaying: false,
        isRecording: false,
        liveTranscript: '',
        userTranscript: '',
        uploadState: 'idle',
        uploadProgress: 0,
      },
    })

    await wrapper.get('[data-testid="record-toggle"]').trigger('click')
    expect(wrapper.emitted('toggleRecording')).toHaveLength(1)
  })
})
