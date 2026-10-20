import type { Page } from '@playwright/test'
import { browserMockContract } from '../../tests/setup/browserMockContract'

export async function installBrowserMocks(page: Page) {
  await page.addInitScript((contract: typeof browserMockContract) => {
    class MockSpeechSynthesisUtterance {
      text: string
      lang = 'en-US'
      rate = 1
      onstart: ((event: Event) => void) | null = null
      onend: ((event: Event) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(text: string) {
        this.text = text
      }
    }

    class MockAudio {
      src: string
      currentTime = 0
      onplay: ((event: Event) => void) | null = null
      onended: ((event: Event) => void) | null = null
      onerror: ((event: Event) => void) | null = null
      isPlaying = false

      constructor(src = '') {
        this.src = src
      }

      async play() {
        this.isPlaying = true
        this.onplay?.(new Event('play'))
      }

      pause() {
        if (!this.isPlaying) {
          return
        }

        this.isPlaying = false
        this.onended?.(new Event('ended'))
      }
    }

    let activeUtterance: MockSpeechSynthesisUtterance | null = null

    Object.defineProperty(window, 'SpeechSynthesisUtterance', {
      configurable: true,
      value: MockSpeechSynthesisUtterance,
    })

    Object.defineProperty(window, 'Audio', {
      configurable: true,
      value: MockAudio,
    })

    Object.defineProperty(window, 'speechSynthesis', {
      configurable: true,
      value: {
        speak(utterance: MockSpeechSynthesisUtterance) {
          const currentUtterance = utterance as MockSpeechSynthesisUtterance
          activeUtterance = currentUtterance
          window.setTimeout(() => {
            currentUtterance.onstart?.(new Event('start'))
          }, 0)
        },
        cancel() {
          if (!activeUtterance) {
            return
          }

          const utterance = activeUtterance
          activeUtterance = null
          utterance.onend?.(new Event('end'))
        },
        pause() {
          return undefined
        },
        resume() {
          return undefined
        },
        speaking: false,
        pending: false,
        paused: false,
        getVoices() {
          return []
        },
        addEventListener() {
          return undefined
        },
        removeEventListener() {
          return undefined
        },
        dispatchEvent() {
          return true
        },
        onvoiceschanged: null,
      },
    })

    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        async getUserMedia() {
          return {
            getTracks() {
              return [
                {
                  stop() {
                    return undefined
                  },
                },
              ]
            },
          }
        },
      },
    })

    Object.defineProperty(window, 'MediaRecorder', {
      configurable: true,
      value: class MockMediaRecorder {
        static isTypeSupported() {
          return true
        }

        state = 'inactive'
        ondataavailable = null
        onstop = null
        chunkEmitted = false

        constructor(stream: MediaStream) {
          void stream
        }

        start(timeslice = 0) {
          this.state = 'recording'
          window.setTimeout(() => {
            if (this.state !== 'recording' || this.chunkEmitted) {
              return
            }

            this.chunkEmitted = true
            this.ondataavailable?.({
              data: new Blob([contract.audioBlobText], {
                type: contract.audioMimeType,
              }),
            })
          }, timeslice)
        }

        stop() {
          if (this.state === 'inactive') {
            return
          }

          this.state = 'inactive'
          if (!this.chunkEmitted) {
            this.chunkEmitted = true
            this.ondataavailable?.({
              data: new Blob([contract.audioBlobText], {
                type: contract.audioMimeType,
              }),
            })
          }

          this.onstop?.()
        }
      },
    })

    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: class MockAudioContext {
        sampleRate = 48000
        state = 'running'
        destination = {} as AudioDestinationNode
        audioWorklet = { addModule: async () => undefined }

        createMediaStreamSource() {
          return {
            connect(target?: { __emitMockPcmFrame?: () => void }) {
              target?.__emitMockPcmFrame?.()
              return undefined
            },
            disconnect() {
              return undefined
            },
          }
        }

        createScriptProcessor() {
          const processor = {
            onaudioprocess: null,
            connect() {
              window.setTimeout(() => {
                processor.onaudioprocess?.({
                  inputBuffer: {
                    getChannelData: () => new Float32Array(contract.pcmFrame),
                  },
                })
              }, 0)
              return undefined
            },
            disconnect() {
              return undefined
            },
          }

          return processor
        }

        createGain() {
          return {
            gain: { value: 1 },
            connect() {
              return undefined
            },
            disconnect() {
              return undefined
            },
          }
        }

        async resume() {
          this.state = 'running'
        }

        async close() {
          return undefined
        }
      },
    })

    Object.defineProperty(window, 'AudioWorkletNode', {
      configurable: true,
      value: class MockAudioWorkletNode {
        port = {
          onmessage: null as ((event: { data: Float32Array }) => void) | null,
          close() {
            return undefined
          },
        }

        constructor() {
          window.setTimeout(() => {
            this.port.onmessage?.({ data: new Float32Array(contract.pcmFrame) })
          }, 0)
        }

        __emitMockPcmFrame() {
          window.setTimeout(() => {
            this.port.onmessage?.({ data: new Float32Array(contract.pcmFrame) })
          }, 0)
        }

        connect() {
          return undefined
        }

        disconnect() {
          return undefined
        }
      },
    })

    Object.defineProperty(window, 'webkitAudioContext', {
      configurable: true,
      value: window.AudioContext,
    })
  }, browserMockContract)
}
