import { computed, onBeforeUnmount, ref } from 'vue'
import axios from 'axios'
import type { DialogueEntry } from '@/services/dialogue'
import type { ResourceCard, ResourceDeck } from '@/services/contentCore'
import { reviewHttp, reviewKey, reviewError, reviewErrorCode, uploadReviewAudio, type FlippedReview, type PracticeInput, type Rating, type ReviewInput, type ReviewNext, type ReviewQueue, type ReviewTemplate, type PendingReview } from '@/services/review'

type PendingWrite = { key: string; kind: 'flip'; body: { card_id: string; review_token: string; input: ReviewInput } } |
  { key: string; kind: 'rating'; attemptId: string; body: { rating: Rating; card_schedule_revision: number } }
const recoverable = new Set(['QUEUE_EXPIRED', 'CARD_SCHEDULE_CONFLICT', 'RATING_ALREADY_SET', 'REVIEW_TOKEN_INVALID', 'REVIEW_TOKEN_REUSED', 'DAILY_LIMIT_REACHED'])

export function useReviewSession() {
  const completedRound = ref<DialogueEntry>()
  const roundAttemptIds = new Set<string>()
  let roundKey = reviewKey()
  const deck = ref<ResourceDeck>()
  const state = ref<ReviewNext>()
  const loading = ref(false)
  const busy = ref(false)
  const actionStatus = ref('')
  const error = ref('')
  const needsRecovery = ref(false)
  const pendingReview = ref<PendingReview>()
  const practiceTemplate = ref<ReviewTemplate>()
  const uploadProgress = ref<number | null>(null)
  const flipped = computed(() => !!state.value?.attempt)
  const card = computed<ResourceCard | undefined>(() => state.value?.card ? {
    ...state.value.card, front: state.value.attempt?.front_snapshot || state.value.card.front,
    back: state.value.attempt?.back_snapshot || {},
  } : undefined)
  let generation = 0
  let deckId = ''
  let entry: { id: string; legacy: boolean; template?: ReviewTemplate } = { id: '', legacy: false }
  let pending: PendingWrite | null = null
  let retryAction: (() => Promise<void>) | null = null
  let pollTimer: ReturnType<typeof setTimeout> | undefined
  const storageKey = () => `langear:review-write:${deckId}`
  function remember(value: PendingWrite | null) {
    pending = value
    try {
      if (value) sessionStorage.setItem(storageKey(), JSON.stringify(value))
      else sessionStorage.removeItem(storageKey())
    } catch { /* DB receipts and pending Attempt still provide server recovery. */ }
  }
  function savedWrite(): PendingWrite | null {
    try { return JSON.parse(sessionStorage.getItem(storageKey()) || 'null') as PendingWrite | null }
    catch { return null }
  }
  function fail(cause: unknown) {
    error.value = reviewError(cause)
    const code = reviewErrorCode(cause) || ''
    if (code === 'PENDING_REVIEW_OUTSIDE_SCOPE' && axios.isAxiosError(cause)) pendingReview.value = cause.response?.data?.error?.details
    needsRecovery.value = recoverable.has(code)
    if (needsRecovery.value && code !== 'QUEUE_EXPIRED') remember(null)
  }
  function poll(request = generation, count = 0) {
    clearTimeout(pollTimer)
    const attempt = state.value?.attempt
    if (!attempt || count >= 120 || ![attempt.asr_status, attempt.ai_status].some(s => ['pending', 'processing'].includes(s))) return
    pollTimer = setTimeout(async () => {
      try {
        const { data } = await reviewHttp.get<typeof attempt>(`/attempts/${attempt.id}`)
        if (request !== generation || state.value?.attempt?.id !== data.id) return
        state.value.attempt = data
      } catch { /* A temporary status failure must not block rating. */ }
      if (request === generation) poll(request, count + 1)
    }, 5000)
  }
  async function next(request = generation) {
    const { data } = await reviewHttp.get<ReviewNext>(`/review/queues/${state.value!.queue_id}/next`)
    if (request !== generation) return
    state.value = data
    if (!data.card && roundAttemptIds.size && !completedRound.value) {
      completedRound.value = { deck_id: deckId, review_queue_id: data.queue_id, entry_key: roundKey, attempt_ids: [...roundAttemptIds] }
    }
    poll(request)
  }
  async function send(request = generation) {
    const write = pending
    if (!write || !state.value) return
    const queue = state.value.queue_id
    if (write.kind === 'flip') {
      actionStatus.value = '正在保存作答…'
      const { data } = await reviewHttp.post<FlippedReview>(`/review/queues/${queue}/flip`, write.body, { headers: { 'Idempotency-Key': write.key } })
      if (request !== generation) return
      state.value = { ...state.value, ...data, can_undo: false }
      remember(null)
      poll(request)
    } else {
      actionStatus.value = '正在保存评分…'
      await reviewHttp.put(`/review/queues/${queue}/attempts/${write.attemptId}/rating`, write.body, { headers: { 'Idempotency-Key': write.key } })
      if (request !== generation) return
      roundAttemptIds.add(write.attemptId)
      remember(null)
      retryAction = () => next()
      actionStatus.value = '评分已保存，正在加载下一张…'
      await next(request)
    }
  }
  async function load(id: string, legacy = false, template?: ReviewTemplate) {
    const request = ++generation
    completedRound.value = undefined
    roundAttemptIds.clear()
    roundKey = reviewKey()
    clearTimeout(pollTimer)
    deckId = id
    entry = { id, legacy, template }
    pendingReview.value = undefined
    practiceTemplate.value = undefined
    state.value = undefined
    deck.value = undefined
    pending = savedWrite()
    retryAction = null
    loading.value = true
    busy.value = false
    actionStatus.value = ''
    error.value = ''
    needsRecovery.value = false
    try {
      if (legacy) {
        const { data } = await reviewHttp.get<{ deck_id: string }>(`/review/legacy-lessons/${encodeURIComponent(id)}`)
        if (request !== generation) return
        id = data.deck_id
        deckId = id
        pending = savedWrite()
      }
      const { data: resource } = await reviewHttp.get<ResourceDeck>(`/decks/${id}`)
      if (request !== generation) return
      deck.value = resource
      const imported = !!resource.deck_guid?.startsWith('legacy:')
      practiceTemplate.value = template || (imported ? 'sentence_retelling' : undefined)
      const { data } = await reviewHttp.post<ReviewQueue>('/review/queues', { scope: { deck_id: id, include_descendants: true, exclude_imported: !imported,
        ...(practiceTemplate.value ? { card_template_keys: [practiceTemplate.value] } : {}),
      } })
      if (request !== generation) return
      state.value = data.current || { ...data, review_token: null, card: null }
      if (pending) await send(request)
      await next(request)
    } catch (cause) { if (request === generation) fail(cause) }
    finally { if (request === generation) { loading.value = false; actionStatus.value = '' } }
  }
  async function perform(action: () => Promise<void>) {
    if (busy.value || loading.value) return
    const request = generation
    busy.value = true
    actionStatus.value = '正在保存…'
    error.value = ''
    needsRecovery.value = false
    retryAction = action
    try { await action() }
    catch (cause) { if (request === generation) fail(cause) }
    finally { if (request === generation) { busy.value = false; actionStatus.value = ''; uploadProgress.value = null } }
  }
  async function flip(input: PracticeInput = { type: 'none' }) {
    if (pending || state.value?.attempt || !state.value?.card) return
    const current = state.value
    const request = generation
    await perform(async () => {
      let wire: ReviewInput
      if (input.type === 'audio') {
        uploadProgress.value = 0
        const id = await uploadReviewAudio(input.blob, p => { if (request === generation) uploadProgress.value = p })
        if (request === generation) uploadProgress.value = null
        wire = { type: 'audio', temporary_media_asset_id: id, ...(input.realtimeSessionId ? { realtime_session_id: input.realtimeSessionId } : {}) }
      } else wire = input
      if (request !== generation) return
      remember({ key: reviewKey(), kind: 'flip', body: { card_id: current.card!.id, review_token: current.review_token!, input: wire } })
      await send(request)
    })
  }
  async function rate(rating: Rating) {
    const current = state.value
    if (pending || !current?.attempt || current.card_schedule_revision === undefined || busy.value) return
    remember({ key: reviewKey(), kind: 'rating', attemptId: current.attempt.id, body: { rating, card_schedule_revision: current.card_schedule_revision } })
    await perform(() => send())
  }
  async function undo() {
    if (!state.value?.can_undo) return
    const key = reviewKey()
    await perform(async () => {
      const { data: restored } = await reviewHttp.post<FlippedReview>(`/review/queues/${state.value!.queue_id}/undo`, {}, { headers: { 'Idempotency-Key': key } })
      roundAttemptIds.delete(restored.attempt.id)
      completedRound.value = undefined
      await next()
    })
  }
  async function schedule(action: 'bury' | 'suspend') {
    const current = state.value
    if (!current?.card || current.attempt) return
    await perform(async () => {
      await reviewHttp.post(`/cards/${current.card!.id}/schedule`, { action, card_schedule_revision: current.card!.card_schedule_revision })
      await load(entry.id, entry.legacy, entry.template)
    })
  }
  async function retryProcessing() {
    const attempt = state.value?.attempt
    if (!attempt) return
    const request = generation
    await perform(async () => {
      const { data } = await reviewHttp.post<typeof attempt>(`/attempts/${attempt.id}/retry`)
      if (request !== generation || state.value?.attempt?.id !== data.id) return
      state.value.attempt = data
      poll(request)
    })
  }
  async function retry() {
    if (needsRecovery.value || !state.value) return load(entry.id, entry.legacy, entry.template)
    return perform(pending ? () => send() : retryAction || (() => next()))
  }
  onBeforeUnmount(() => { generation++; clearTimeout(pollTimer) })
  return { completedRound, deck, state, card, flipped, loading, busy, actionStatus, error, needsRecovery, pendingReview, practiceTemplate, uploadProgress, load, flip, rate, undo, schedule, retry, retryProcessing }
}
