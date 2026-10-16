export const isE2EMode = import.meta.env.VITE_E2E_MODE === 'true'

export function buildE2ERealtimeSessionId(lessonId: number, cardId: number): string {
  return `e2e-session-${lessonId}-${cardId}`
}

export function buildE2EOssAudioPath(cardId: string): string {
  return `recordings/e2e/${cardId}.webm`
}
