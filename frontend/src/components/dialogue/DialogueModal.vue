<script setup lang="ts">
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { dialogueControllerKey, useDialogue } from '@/composables/useDialogue'
import AttemptEvidence from './AttemptEvidence.vue'
import DialogueText from './DialogueText.vue'
import { dialogueApi } from '@/services/dialogue'
import RetroButton from '@/components/ui/RetroButton.vue'
import type { DialogueSource } from '@/services/dialogue'
import type { DialogueEntry } from '@/services/dialogue'

const props = withDefaults(defineProps<{ entry: DialogueEntry; confirmOnClose?: boolean; closeLabel?: string }>(), { confirmOnClose: true, closeLabel: '关闭' })
const emit = defineEmits<{ close: [] }>()
const createController = inject(dialogueControllerKey, useDialogue)
const { session, status, error, notice, partial, userPartial, remaining, prepare, connect, record, sendRecording, sendText, end, finishAndReview } = createController(props.entry)
const dialog = ref<HTMLDialogElement>()
const evidence = ref<DialogueSource>()
const reply = ref('')
const anchor = ref<HTMLElement>()
watch(() => session.value?.turns.length, async () => {
  await nextTick()
  anchor.value?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
})
function submitText() {
  if (status.value !== 'ready' || !reply.value.trim()) return
  sendText(reply.value)
  reply.value = ''
}
watch(session, () => { evidence.value = undefined })
const busy = computed(() => ['preparing', 'connecting', 'thinking', 'reviewing'].includes(status.value))
const talking = computed(() => ['ready', 'recording', 'speaking', 'thinking', 'connecting'].includes(status.value))
const labels: Record<string, string> = { preparing: '正在准备…', connecting: '正在连接…', speaking: '老师正在说话…', ready: '轮到你了', recording: '正在录音，再次点击发送。', thinking: '正在思考…', reviewing: '正在整理…' }
const clock = computed(() => {
  const total = Math.max(0, remaining.value)
  return Math.floor(total / 60) + ':' + String(total % 60).padStart(2, '0')
})
const previousFocus = document.activeElement as HTMLElement | null
function close() {
  if (props.confirmOnClose && talking.value && !window.confirm('离开会暂停本次对话，确定离开吗？')) return
  emit('close')
}
onMounted(() => { dialog.value?.showModal(); void prepare() })
onUnmounted(() => previousFocus?.focus())
</script>

<template>
  <dialog
    ref="dialog"
    class="m-auto max-h-[92dvh] w-[min(42rem,94vw)] rounded-md border border-brand-accent bg-brand-panel p-0 text-slate-900 shadow-mech backdrop:bg-black/60"
    aria-labelledby="dialogue-title"
    data-testid="dialogue-modal"
    @cancel.prevent="close"
  >
    <slot name="preview-controls" />
    <header class="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-slate-200 bg-brand-panel px-6 py-4">
      <div>
        <slot name="heading">
          <h2
            id="dialogue-title"
            class="sr-only"
          >
            情景对话
          </h2>
        </slot>
      </div>
      <RetroButton
        variant="ghost"
        size="sm"
        class="shrink-0 rounded-md"
        aria-label="关闭情景对话"
        :disabled="status === 'preparing' || status === 'reviewing'"
        @click="close"
      >
        {{ closeLabel }}
      </RetroButton>
    </header>
    <main class="space-y-5 px-6 py-5">
      <slot name="content">
        <p
          v-if="labels[status]"
          role="status"
          class="text-sm text-brand-accent"
        >
          {{ labels[status] }}
        </p>
        <p
          v-if="error"
          role="alert"
          class="rounded-lg bg-amber-50 p-3 text-sm text-amber-900"
        >
          {{ error }}
        </p>
        <p
          v-if="notice"
          role="status"
          class="rounded-lg bg-slate-100 p-3 text-sm text-slate-700"
        >
          {{ notice }}
        </p>
        <template v-if="session">
          <ol
            v-if="session.turns.length"
            aria-label="对话记录"
            class="space-y-3"
          >
            <li
              v-for="turn in session.turns"
              :key="turn.id"
              :class="turn.role === 'user' ? 'ml-8 border-brand-accent/20 bg-red-50/60' : 'mr-8 border-slate-200 bg-brand-dark'"
              class="rounded-md border p-3"
            >
              <span class="mb-1 block text-xs text-slate-500">{{ turn.role === 'user' ? '你' : '老师' }}</span>
              <DialogueText
                :english="turn.text"
                :chinese="turn.translation_zh || undefined"
                :translate="turn.translation_zh ? undefined : () => dialogueApi.translate(session!.id, turn.id)"
              />
            </li>
          </ol>
          <p
            v-if="userPartial"
            aria-live="polite"
            class="ml-8 rounded-md border border-brand-accent/20 bg-red-50/60 p-3 text-sm leading-relaxed"
          >
            <span class="mb-1 block text-xs text-slate-500">你 · 识别中</span>
            <span lang="en">{{ userPartial }}</span>
          </p>
          <p
            v-if="partial"
            aria-live="polite"
            class="mr-8 rounded-md border border-slate-200 bg-brand-dark p-3 text-sm leading-relaxed"
          >
            {{ partial }}
          </p>
          <section
            v-if="session.review"
            class="space-y-4"
            aria-label="对话复盘"
          >
            <h3 class="font-bold">
              快速回顾
            </h3>
            <DialogueText
              :english="session.review.summary_en || 'Your conversation is saved.'"
              :chinese="session.review.summary_zh"
            />
            <p
              v-if="session.review.used_expressions.length"
              class="text-sm text-brand-accent"
            >
              你用到了：{{ session.review.used_expressions.map(e => e.english).join(' · ') }}
            </p>
            <div
              v-for="(point, index) in session.review.practice_points"
              :key="index"
              class="rounded-md bg-amber-50 p-3 text-sm"
            >
              <DialogueText
                :english="point.advice_en || 'Revisit this expression from your practice.'"
                :chinese="point.advice_zh"
              /><button
                class="mt-2 inline-block text-brand-accent underline"
                @click="evidence = point.source"
              >
                查看原练习
              </button>
            </div>
          </section>
        </template>
        <slot
          v-if="evidence"
          name="evidence"
          :source="evidence"
        >
          <AttemptEvidence :source="evidence" />
        </slot>
        <div
          v-if="status === 'preview'"
          class="space-y-3"
        >
          <p class="text-xs text-slate-500">
            先聊聊你刚练习的内容，再试着完成一段真实的对话。
          </p><RetroButton
            class="w-full rounded-md"
            @click="connect"
          >
            开始对话
          </RetroButton>
        </div>
        <div
          v-if="talking"
          class="space-y-3"
        >
          <RetroButton
            class="w-full rounded-md"
            :disabled="!['ready', 'recording'].includes(status)"
            @click="status === 'recording' ? sendRecording() : record()"
          >
            {{ status === 'recording' ? '发送录音' : '点击说话' }}
          </RetroButton><div class="flex justify-between text-xs text-slate-500">
            <span>{{ remaining > 0 ? '剩余 ' + clock : '' }}</span><button
              :disabled="status === 'connecting'"
              class="underline disabled:opacity-40"
              @click="end"
            >
              结束对话
            </button>
          </div>
        </div>
        <form
          v-if="talking"
          class="space-y-2"
          @submit.prevent="submitText"
        >
          <label
            for="dialogue-reply"
            class="text-xs text-slate-500"
          >或输入文字回复</label>
          <textarea
            id="dialogue-reply"
            v-model="reply"
            rows="2"
            maxlength="4000"
            :disabled="status !== 'ready'"
            class="w-full rounded-md border border-slate-200 bg-brand-dark px-3 py-2 text-sm outline-brand-accent"
            placeholder="用英语简短回答…"
          />
          <RetroButton
            type="submit"
            size="sm"
            class="ml-auto rounded-md"
            :disabled="status !== 'ready' || !reply.trim()"
          >
            发送
          </RetroButton>
        </form>
        <div ref="anchor" />
        <div
          v-if="status === 'failed'"
          class="flex flex-wrap gap-3"
        >
          <RetroButton
            v-if="!session"
            size="sm"
            class="rounded-md"
            @click="prepare"
          >
            重试
          </RetroButton><template v-else>
            <RetroButton
              v-if="session.status !== 'finished'"
              size="sm"
              class="rounded-md"
              @click="connect"
            >
              重新连接
            </RetroButton><RetroButton
              variant="secondary"
              size="sm"
              class="rounded-md"
              @click="finishAndReview(false)"
            >
              结束对话
            </RetroButton>
          </template>
        </div>
        <RetroButton
          v-if="status === 'complete'"
          variant="secondary"
          class="w-full rounded-md"
          @click="emit('close')"
        >
          完成
        </RetroButton>
        <span
          v-if="busy"
          class="sr-only"
        >请稍候</span>
      </slot>
    </main>
  </dialog>
</template>
