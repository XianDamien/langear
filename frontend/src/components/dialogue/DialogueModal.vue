<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { dialogueControllerKey, useDialogue } from '@/composables/useDialogue'
import AttemptEvidence from './AttemptEvidence.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import type { DialogueSource } from '@/services/dialogue'
import type { DialogueEntry } from '@/services/dialogue'

const props = withDefaults(defineProps<{ entry: DialogueEntry; confirmOnClose?: boolean; closeLabel?: string }>(), { confirmOnClose: true, closeLabel: '关闭' })
const emit = defineEmits<{ close: [] }>()
const createController = inject(dialogueControllerKey, useDialogue)
const { session, status, error, partial, prepare, connect, record, sendRecording, end, finishAndReview } = createController(props.entry)
const dialog = ref<HTMLDialogElement>()
const evidence = ref<DialogueSource>()
watch(session, () => { evidence.value = undefined })
const busy = computed(() => ['preparing', 'connecting', 'thinking', 'reviewing'].includes(status.value))
const talking = computed(() => ['ready', 'recording', 'speaking', 'thinking', 'connecting'].includes(status.value))
const labels: Record<string, string> = { preparing: '正在准备你的场景…', connecting: '连接中…', speaking: '对方正在说话…', ready: '轮到你了', recording: '正在录音，再次点击发送', thinking: '等待对方回复…', reviewing: '正在整理本次练习…' }
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
          <p class="text-xs font-semibold tracking-wide text-slate-500">
            学完，马上用
          </p><h2
            id="dialogue-title"
            class="mt-1 text-xl font-bold text-brand-accent"
          >
            {{ session?.scenario.title || '进入情景对话' }}
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
        <template v-if="session">
          <section
            v-if="!session.review"
            class="space-y-3 rounded-md border border-slate-200 bg-brand-dark p-4"
          >
            <p class="text-sm leading-relaxed">
              {{ session.scenario.setup_zh }}
            </p>
            <p class="text-xs text-slate-600">
              你：{{ session.scenario.learner_role }} · 对方：{{ session.scenario.agent_role }}
            </p>
            <ul class="list-inside list-disc text-sm">
              <li
                v-for="goal in session.scenario.goals"
                :key="goal.id"
              >
                {{ goal.description_zh }}
              </li>
            </ul>
            <details class="text-sm">
              <summary class="cursor-pointer text-brand-accent">
                试着用上这些表达
              </summary><ul class="mt-2 space-y-2">
                <li
                  v-for="expression in session.scenario.target_expressions"
                  :key="expression.english"
                >
                  <strong>{{ expression.english }}</strong> · {{ expression.meaning_zh }}
                </li>
              </ul>
            </details>
          </section>
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
              <span class="mb-1 block text-xs text-slate-500">{{ turn.role === 'user' ? '你' : session.scenario.agent_role }}</span><p class="whitespace-pre-wrap text-sm leading-relaxed">
                {{ turn.text }}
              </p>
            </li>
          </ol>
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
              这次用得怎么样
            </h3><p class="text-sm leading-relaxed">
              {{ session.review.summary_zh }}
            </p>
            <ul class="space-y-2 text-sm">
              <li
                v-for="goal in session.review.goals"
                :key="goal.goal_id"
              >
                {{ goal.completed ? '✓' : '○' }} {{ session.scenario.goals.find(g => g.id === goal.goal_id)?.description_zh }}
              </li>
            </ul>
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
              <p>{{ point.advice_zh }}</p><button
                class="mt-2 inline-block text-brand-accent underline"
                @click="evidence = point.source"
              >
                查看原卡片与反馈
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
            英语角色扮演 · 最多 8 轮 · 结束后一起复盘
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
            {{ status === 'recording' ? '结束录音并发送' : '点击开始说话' }}
          </RetroButton><div class="flex justify-between text-xs text-slate-500">
            <span>{{ session?.user_turns || 0 }} / 8 轮</span><button
              :disabled="status === 'connecting'"
              class="underline disabled:opacity-40"
              @click="end"
            >
              结束并复盘
            </button>
          </div>
        </div>
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
            重新准备
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
              @click="finishAndReview"
            >
              {{ session.status === 'finished' ? '重试复盘' : '结束并复盘' }}
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
