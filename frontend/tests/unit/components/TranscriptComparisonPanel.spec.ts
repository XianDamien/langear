import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import TranscriptComparisonPanel from '@/components/study/TranscriptComparisonPanel.vue'

const props = {
  originalText: 'The quick brown fox.',
  transcriptText: 'The brown fox.',
  translationText: '敏捷的棕色狐狸。',
  showTranslation: false,
  translationLoading: false,
  referenceAudioUrl: '/reference.wav',
  userAudioUrl: '/recording.wav',
}

describe('TranscriptComparisonPanel audio pairing', () => {
  it('pauses the other track and sends feedback timestamps to the user recording', async () => {
    const wrapper = mount(TranscriptComparisonPanel, { props })
    const [reference, recording] = wrapper.findAll('audio').map(node => node.element)
    const referencePlay = vi.spyOn(reference!, 'play').mockResolvedValue()
    const referencePause = vi.spyOn(reference!, 'pause').mockImplementation(() => {})
    const recordingPlay = vi.spyOn(recording!, 'play').mockResolvedValue()
    const recordingPause = vi.spyOn(recording!, 'pause').mockImplementation(() => {})
    Object.defineProperty(recording, 'duration', { configurable: true, value: 10 })

    await wrapper.get('[aria-label="播放原音频"]').trigger('click')
    expect(referencePlay).toHaveBeenCalledOnce()
    expect(recordingPause).toHaveBeenCalledOnce()

    await wrapper.get('[aria-label="播放我的录音"]').trigger('click')
    expect(recordingPlay).toHaveBeenCalledOnce()
    expect(referencePause).toHaveBeenCalledOnce()

    await wrapper.vm.jumpToUserAudio(2.05)
    expect(recording!.currentTime).toBe(2.05)
    expect(reference!.currentTime).toBe(0)
    expect(recordingPlay).toHaveBeenCalledTimes(2)
    expect(referencePause).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('disables missing audio without disabling text and translation actions', async () => {
    const wrapper = mount(TranscriptComparisonPanel, {
      props: { ...props, referenceAudioUrl: null, userAudioUrl: null },
    })
    expect(wrapper.get('[aria-label="播放原音频"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[aria-label="我的录音进度"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-expanded="false"]').trigger('click')
    expect(wrapper.emitted('toggleTranslation')).toHaveLength(1)
    await wrapper.get('[data-testid="original-text"] button').trigger('click')
    expect(wrapper.emitted('wordClick')).toEqual([['The']])
    wrapper.unmount()
  })

  it.each(['hello, world!', 'Hello world!', 'Hello,  world!'])('detects strict dictation differences in %s', text => {
    const wrapper = mount(TranscriptComparisonPanel, { props: {
      ...props, comparisonMode: 'dictation', originalText: 'Hello, world!', transcriptText: text, showUserAudio: false,
    } })
    expect(wrapper.get('[data-testid="text-difference-count"]').text()).not.toBe('0 处差异')
    expect(wrapper.get('[data-testid="original-text"]').text()).toBe('Hello, world!')
    wrapper.unmount()
  })

  it('shows alternative translations without marking them as dictation errors', () => {
    const wrapper = mount(TranscriptComparisonPanel, { props: {
      ...props, comparisonMode: 'translation', transcriptLabel: '我的译文', originalText: 'Hello.', transcriptText: 'Hi.',
      referenceAudioUrl: null, translationText: '', showUserAudio: false,
    } })
    expect(wrapper.text()).toContain('参考译文')
    expect(wrapper.text()).toContain('我的译文')
    expect(wrapper.find('[data-testid="text-difference-count"]').exists()).toBe(false)
    expect(wrapper.findAll('.line-through')).toHaveLength(0)
    expect(wrapper.findAll('audio')).toHaveLength(0)
    wrapper.unmount()
  })
})
