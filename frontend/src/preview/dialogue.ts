import { computed, ref } from 'vue'
import type { useDialogue } from '@/composables/useDialogue'
import type { DialogueEntry, DialogueSession } from '@/services/dialogue'

export type PreviewPage = 'recap' | 'refine' | 'task' | 'roleplay' | 'complete' | 'failed'
export const previewStates: { value: PreviewPage; label: string }[] = [
  { value: 'recap', label: '1 · Quick recap' },
  { value: 'refine', label: '2 · A clearer answer' },
  { value: 'task', label: '3 · Your task' },
  { value: 'roleplay', label: '4 · Roleplay' },
  { value: 'complete', label: '5 · Wrap-up' },
  { value: 'failed', label: 'Connection issue' },
]
export interface PreviewMessage {
  id: number
  speaker: 'coach' | 'user' | 'staff'
  english: string
  chinese?: string
  label?: string
  expressions?: { english: string; chinese: string }[]
}
export const previewEntry: DialogueEntry = {
  deck_id: 'preview-lesson', review_queue_id: 'preview-queue',
  entry_key: 'preview-only', attempt_ids: ['preview-attempt'],
}
const sampleSummary = 'He went to the theatre. Some people talked loudly. He was angry.'
const sampleRequest = 'Could you ask them to speak quietly, please?'
const sampleSeats = 'Could we move to quieter seats, please?'

/** Scripted UI preview only: no model, network, microphone, or learning writes. */
export function createDialoguePreview() {
  const page = ref<PreviewPage>('recap')
  const input = ref('')
  const messages = ref<PreviewMessage[]>([])
  const roleplayTurns = ref(0)
  let nextId = 0
  const session = ref<DialogueSession>({
    id: 'preview-session', deck_id: previewEntry.deck_id, status: 'ready', finish_reason: null,
    user_turns: 0, max_user_turns: 8, turns: [], review: null,
    scenario: { title: 'Let’s talk about it.', setup_zh: '', learner_role: 'Audience member', agent_role: 'Theatre staff', goals: [], target_expressions: [] },
  })
  const status = ref<ReturnType<typeof useDialogue>['status']['value']>('preview')
  const error = ref('')
  const partial = ref('')
  const canReply = computed(() => ['recap', 'roleplay'].includes(page.value))
  const sample = computed(() => page.value === 'recap' ? sampleSummary : roleplayTurns.value ? sampleSeats : sampleRequest)
  const phase = computed(() => ({ recap: 'Recall', refine: 'Refine', task: 'Your task', roleplay: 'Roleplay', complete: 'Wrap-up', failed: 'Reconnect' })[page.value])

  function add(speaker: PreviewMessage['speaker'], english: string, chinese?: string, extra?: Pick<PreviewMessage, 'label' | 'expressions'>) {
    messages.value.push({ id: ++nextId, speaker, english, chinese, ...extra })
  }
  function reset() {
    messages.value = []; input.value = ''; roleplayTurns.value = 0
    status.value = 'preview'; error.value = ''; page.value = 'recap'
    add('coach', 'You’ve just practised “A private conversation.” What happened at the theatre? Tell me in two or three sentences.', '你刚练习了《一次私人谈话》。剧院里发生了什么？用两三句话告诉我。')
  }
  function refine(answer: string) {
    add('user', answer)
    // Known lesson facts provide a stable teaching example; no model evaluation is implied.
    const mentionedNoise = /talk|loud|nois|hear/i.test(answer)
    add('coach', mentionedNoise
      ? 'You mentioned the noise. Add how it affected him: he couldn’t hear the actors.'
      : 'Let’s connect the setting, the problem, and his reaction. Here’s one way to say it.',
    mentionedNoise ? '你提到了噪声。再补充它带来的影响：他听不清演员的台词。' : '我们把场景、问题和他的反应连起来。可以这样说。')
    add('coach', 'He went to the theatre, but the people behind him were talking loudly. He couldn’t hear the actors, so he asked them to be quiet.', '他去剧院看戏，但后面的人一直大声说话。他听不清演员的台词，于是请他们安静一些。', { label: 'A clearer version' })
    page.value = 'refine'
  }
  function introduceTask() {
    page.value = 'task'; status.value = 'preview'
    add('coach', 'Now it’s your turn. You’re at the theatre and can’t hear the play. I’ll be a staff member. Explain the problem and ask for help. If it’s still noisy, ask to change seats.', '现在换你了。你在剧院里听不清演出。我来扮演工作人员。说明问题并请求帮助；如果仍然太吵，就试着请求换座。', {
      label: 'Your mission',
      expressions: [
        { english: 'I can’t hear the actors.', chinese: '我听不清演员的台词。' },
        { english: 'Could you… please?', chinese: '能请你……吗？' },
        { english: 'Could we move to quieter seats?', chinese: '我们能换到安静一点的座位吗？' },
      ],
    })
  }
  function startRoleplay() {
    page.value = 'roleplay'; status.value = 'ready'
    add('staff', 'Good evening. Is everything all right with your seats?', '晚上好。你们的座位有什么问题吗？')
  }
  function finish() {
    const count = roleplayTurns.value
    const requests = messages.value.filter(message => message.speaker === 'user').slice(1)
    const polite = requests.some(message => /could|please|would/i.test(message.english))
    page.value = 'complete'; status.value = 'complete'; input.value = ''
    if (!count) add('coach', 'We stopped before your first reply. Next time, try explaining the problem and making one polite request.', '我们在你第一次回复前结束了。下次试着先说明问题，再提出一个礼貌的请求。')
    else add('coach', polite
      ? 'You made a polite request. Next time, add one detail about the problem before asking for help.'
      : 'You tried the conversation. Next time, make your request softer with “Could you… please?”',
    polite ? '你提出了礼貌的请求。下次求助前，再补充一个问题细节。' : '你尝试完成了对话。下次可以用“Could you… please?”让请求更委婉。')
  }
  function submit() {
    const answer = input.value.trim()
    if (!answer || !canReply.value) return
    input.value = ''; status.value = 'ready'
    if (page.value === 'recap') { refine(answer); return }
    add('user', answer)
    roleplayTurns.value++
    if (roleplayTurns.value === 1) {
      add('staff', 'I’m sorry about the noise. I’ll speak to them. Would you prefer to move to quieter seats?', '很抱歉这里太吵了。我会去和他们沟通。你想换到安静一点的座位吗？')
    } else {
      add('staff', 'Of course. There are two seats in the third row. Let me show you the way.', '当然可以。第三排有两个座位。我带你们过去。')
      finish()
    }
  }
  function useSample() { input.value = sample.value }
  function setInput(value: string) { input.value = value }
  function record() { if (canReply.value) status.value = 'recording' }
  function sendRecording() { useSample(); submit() }
  function show(target: PreviewPage) {
    reset()
    if (target === 'recap') return
    refine(sampleSummary)
    if (target === 'refine') return
    introduceTask()
    if (target === 'task') return
    startRoleplay()
    if (target === 'complete') {
      input.value = sampleRequest; submit()
      input.value = sampleSeats; submit()
    } else if (target === 'failed') {
      page.value = 'failed'; status.value = 'failed'
      error.value = 'Connection lost. Your conversation is still here.'
    }
  }
  async function connect() { error.value = ''; page.value = 'roleplay'; status.value = 'ready' }
  const controller: ReturnType<typeof useDialogue> = {
    session, status, error, partial, prepare: async () => {}, connect,
    record: async () => { record() }, sendRecording, end: finish, finishAndReview: async () => { finish() },
  }
  reset()
  return { controller, page, phase, input, messages, canReply, roleplayTurns, show, submit, useSample, setInput, record, sendRecording, introduceTask, startRoleplay, finish, reset }
}
