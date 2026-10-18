<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useDialogue } from '@/composables/useDialogue'
import AttemptEvidence from './AttemptEvidence.vue'
import type { DialogueSource } from '@/services/dialogue'
import type { DialogueEntry } from '@/services/dialogue'

const props = defineProps<{ entry: DialogueEntry }>()
const emit = defineEmits<{ close: [] }>()
const { session, status, error, partial, prepare, connect, record, sendRecording, end, finish } = useDialogue(props.entry)
const dialog = ref<HTMLDialogElement>()
const evidence = ref<DialogueSource>()
const busy = computed(() => ['preparing', 'connecting', 'thinking', 'finishing'].includes(status.value))
const talking = computed(() => ['ready', 'recording', 'speaking', 'thinking', 'connecting'].includes(status.value))
const labels: Record<string, string> = { preparing: '正在准备你的场景…', connecting: '连接中…', speaking: '对方正在说话…', ready: '轮到你了', recording: '正在录音，再次点击发送', thinking: '等待对方回复…', finishing: '正在保存对话…' }
const previousFocus = document.activeElement as HTMLElement | null
function close() {
  if (talking.value && !window.confirm('离开会暂停本次对话，确定离开吗？')) return
  emit('close')
}
onMounted(() => { dialog.value?.showModal(); void prepare() })
onUnmounted(() => previousFocus?.focus())
</script>

<template>
  <dialog
    ref="dialog"
    class="m-auto max-h-[92dvh] w-[min(42rem,94vw)] rounded-2xl border border-slate-200 bg-white p-0 text-slate-900 shadow-2xl backdrop:bg-black/60"
    aria-labelledby="dialogue-title"
    data-testid="dialogue-modal"
    @cancel.prevent="close"
  >
    <header class="sticky top-0 z-10 flex items-start justify-between border-b border-slate-100 bg-white px-6 py-4">
      <div>
        <p class="text-xs font-semibold tracking-wide text-teal-700">
          学完，马上用
        </p><h2
          id="dialogue-title"
          class="mt-1 text-xl font-bold"
        >
          {{ session?.scenario.title || '进入情景对话' }}
        </h2>
      </div>
      <button
        type="button"
        class="rounded px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
        aria-label="关闭情景对话"
        :disabled="status === 'preparing' || status === 'finishing'"
        @click="close"
      >
        关闭
      </button>
    </header>
    <main class="space-y-5 px-6 py-5">
      <p
        v-if="labels[status]"
        role="status"
        class="text-sm text-teal-700"
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
          class="space-y-3 rounded-xl bg-slate-50 p-4"
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
            <summary class="cursor-pointer text-teal-700">
              试着用上这些表达
            </summary><ul class="mt-2 space-y-2">
              <li
                v-for="expression in session.scenario.target_expressions"
                :key="expression.english"
              >
                <strong>{{ expression.english }}</strong><span v-if="expression.meaning_zh"> · {{ expression.meaning_zh }}</span>
                <button
                  class="ml-2 text-teal-700 underline"
                  @click="evidence = expression.source"
                >
                  查看原卡片
                </button>
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
            :class="turn.role === 'user' ? 'ml-8 bg-teal-50' : 'mr-8 bg-slate-100'"
            class="rounded-xl p-3"
          >
            <span class="mb-1 block text-xs text-slate-500">{{ turn.role === 'user' ? '你' : session.scenario.agent_role }}</span><p class="whitespace-pre-wrap text-sm leading-relaxed">
              {{ turn.text }}
            </p>
          </li>
        </ol>
        <p
          v-if="partial"
          aria-live="polite"
          class="mr-8 rounded-xl bg-slate-100 p-3 text-sm leading-relaxed"
        >
          {{ partial }}
        </p>
      </template>
      <AttemptEvidence
        v-if="evidence"
        :source="evidence"
      />
      <div
        v-if="status === 'preview'"
        class="space-y-3"
      >
        <p class="text-xs text-slate-500">
          英语角色扮演 · 最多 8 轮 · 结束后保存对话
        </p><button
          class="w-full rounded-xl bg-teal-700 py-3 font-semibold text-white hover:bg-teal-800"
          @click="connect"
        >
          开始对话
        </button>
      </div>
      <div
        v-if="talking"
        class="space-y-3"
      >
        <button
          class="w-full rounded-xl bg-teal-700 py-3 font-semibold text-white disabled:opacity-40"
          :disabled="!['ready', 'recording'].includes(status)"
          @click="status === 'recording' ? sendRecording() : record()"
        >
          {{ status === 'recording' ? '结束录音并发送' : '点击开始说话' }}
        </button><div class="flex justify-between text-xs text-slate-500">
          <span>{{ session?.user_turns || 0 }} / 8 轮</span><button
            :disabled="status === 'connecting'"
            class="underline disabled:opacity-40"
            @click="end"
          >
            结束对话
          </button>
        </div>
      </div>
      <div
        v-if="status === 'failed'"
        class="flex flex-wrap gap-3"
      >
        <button
          v-if="!session"
          class="rounded-lg bg-teal-700 px-4 py-2 text-white"
          @click="prepare"
        >
          重新准备
        </button><template v-else>
          <button
            v-if="session.status !== 'finished'"
            class="rounded-lg bg-teal-700 px-4 py-2 text-white"
            @click="connect"
          >
            重新连接
          </button><button
            class="rounded-lg border px-4 py-2"
            @click="finish"
          >
            结束对话
          </button>
        </template>
      </div>
      <p
        v-if="status === 'complete'"
        role="status"
        class="text-sm text-teal-700"
      >
        对话已结束，记录已保存。
      </p>
      <button
        v-if="status === 'complete'"
        class="w-full rounded-xl border border-slate-300 py-3 text-sm font-semibold"
        @click="emit('close')"
      >
        完成
      </button>
      <span
        v-if="busy"
        class="sr-only"
      >请稍候</span>
    </main>
  </dialog>
</template>
