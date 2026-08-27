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

  function startSpeechPlayback(text: string, lang = 'en-US') {
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

  function playWithFallback(src: string, fallbackText: string, lang = 'en-US') {
    stop()

    if (!src) {
      if (fallbackText.trim()) {
        startSpeechPlayback(fallbackText, lang)
      }
      return
    }

    const token = ++playbackToken
    const fallbackToSpeech = () => {
      if (token === playbackToken) {
        isPlaying.value = false
        if (fallbackText.trim()) {
          startSpeechPlayback(fallbackText, lang)
        }
      }
    }

    currentPlayback = createAudioPlayback(src, {
      ...createPlaybackCallbacks(token),
      onError: fallbackToSpeech,
    })
    void currentPlayback.play().catch(fallbackToSpeech)
  }

  function speakText(text: string, lang = 'en-US') {
    stop()
    startSpeechPlayback(text, lang)
  }

  function stop() {
    playbackToken += 1
    currentPlayback?.stop()
    currentPlayback = null
    cancelSpeechPlayback()
    isPlaying.value = false
  }

  return { isPlaying, play, playWithFallback, speakText, stop }
}
