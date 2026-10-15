import { ref } from 'vue'
import {
  cancelSpeechPlayback,
  createAudioPlayback,
  createSpeechPlayback,
  type AudioPlaybackHandle,
} from '@/adapters/browser/audioPlayback'

export function useAudioPlayer() {
  const isPlaying = ref(false)
  let currentPlayback: AudioPlaybackHandle | null = null
  let playbackToken = 0

  function createPlaybackCallbacks(token: number) {
    return {
      onStart: () => {
        if (token === playbackToken) {
          isPlaying.value = true
        }
      },
      onEnd: () => {
        if (token === playbackToken) {
          isPlaying.value = false
        }
      },
      onError: () => {
        if (token === playbackToken) {
          isPlaying.value = false
        }
      },
    }
  }

  function play(src: string) {
    stop()

    if (!src) return

    const token = ++playbackToken
    currentPlayback = createAudioPlayback(src, createPlaybackCallbacks(token))
    void currentPlayback.play().catch(() => {
      if (token === playbackToken) {
        isPlaying.value = false
      }
    })
  }

  function speakText(text: string, lang = 'en-US') {
    stop()

    const token = ++playbackToken
    currentPlayback = createSpeechPlayback(text, {
      lang,
      rate: 0.9,
      ...createPlaybackCallbacks(token),
    })
    void currentPlayback.play().catch(() => {
      if (token === playbackToken) {
        isPlaying.value = false
      }
    })
  }

  function stop() {
    playbackToken += 1
    currentPlayback?.stop()
    currentPlayback = null
    cancelSpeechPlayback()
    isPlaying.value = false
  }

  return { isPlaying, play, speakText, stop }
}
