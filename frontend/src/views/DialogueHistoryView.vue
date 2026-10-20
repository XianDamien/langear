<script setup lang="ts">
import { onMounted, ref } from 'vue'
import RetroCard from '@/components/ui/RetroCard.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import DialogueText from '@/components/dialogue/DialogueText.vue'
import { dialogueApi, dialogueError, type DialogueHistoryItem, type DialogueSession } from '@/services/dialogue'

const sessions = ref<DialogueHistoryItem[]>([])
const selected = ref<DialogueSession | null>(null)
const loading = ref(true)
const detailLoading = ref(false)
const deleting = ref<string | null>(null)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    sessions.value = await dialogueApi.list()
  } catch (cause) {
    error.value = dialogueError(cause)
  } finally {
    loading.value = false
  }
}

async function open(id: string) {
  detailLoading.value = true
  error.value = ''
  try {
    selected.value = await dialogueApi.get(id)
  } catch (cause) {
    error.value = dialogueError(cause)
  } finally {
    detailLoading.value = false
  }
}

async function remove(item: DialogueHistoryItem) {
  if (!window.confirm(`删除「${item.title || item.deck_name}」这次对话？删除后无法恢复。`)) return
  deleting.value = item.id
  error.value = ''
  try {
    await dialogueApi.remove(item.id)
    if (selected.value?.id === item.id) selected.value = null
    await load()
  } catch (cause) {
    error.value = dialogueError(cause)
  } finally {
    deleting.value = null
  }
}

function formatDate(value: string) {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN')
}

onMounted(load)
</script>

<template>
  <div class="animate-fadeIn">
    <header class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <h2 class="text-3xl font-bold uppercase text-brand-accent">
        对话历史
      </h2>
      <RetroButton
        variant="secondary"
        size="sm"
        :disabled="loading"
        @click="load"
      >
        刷新
      </RetroButton>
    </header>

    <p
      v-if="error"
      role="alert"
      class="mb-4 border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
    >
      {{ error }}
    </p>
    <p
      v-if="loading"
      role="status"
      class="py-16 text-center text-slate-500"
    >
      正在加载对话历史…
    </p>
    <p
      v-else-if="!sessions.length"
      class="border-2 border-dashed border-slate-200 p-8 text-center text-slate-500"
    >
      还没有完成过情景对话。完成一轮练习后会在这里保留对话记录。
    </p>
    <div
      v-else
      class="grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]"
    >
      <ul class="space-y-2">
        <li
          v-for="item in sessions"
          :key="item.id"
          class="border border-slate-200 bg-white p-4"
        >
          <button
            type="button"
            class="w-full text-left"
            :aria-current="selected?.id === item.id ? 'true' : undefined"
            @click="open(item.id)"
          >
            <p class="font-bold text-slate-900">
              {{ item.title || item.deck_name }}
            </p>
            <p class="mt-1 text-xs text-slate-500">
              {{ item.deck_name }} · {{ item.user_turns }} 轮 · {{ formatDate(item.created_at) }}
            </p>
            <p class="mt-1 text-xs text-slate-400">
              {{ item.status === 'finished' ? '已完成' : item.status }}
              {{ item.has_review ? ' · 已复盘' : '' }}
            </p>
          </button>
          <div class="mt-3 flex justify-end">
            <RetroButton
              variant="ghost"
              size="sm"
              :disabled="deleting === item.id"
              @click="remove(item)"
            >
              {{ deleting === item.id ? '删除中…' : '删除' }}
            </RetroButton>
          </div>
        </li>
      </ul>

      <div>
        <p
          v-if="detailLoading"
          role="status"
          class="py-10 text-center text-slate-500"
        >
          正在加载对话…
        </p>
        <p
          v-else-if="!selected"
          class="border border-slate-200 bg-white p-6 text-sm text-slate-500"
        >
          选择左侧一次对话查看完整记录。
        </p>
        <RetroCard
          v-else
          :title="selected.scenario.title"
        >
          <p class="mb-4 text-sm text-slate-600">
            {{ selected.scenario.setup_zh }}
          </p>
          <ol
            class="space-y-3"
            aria-label="对话记录"
          >
            <li
              v-for="turn in selected.turns"
              :key="turn.id"
              :class="turn.role === 'user' ? 'ml-8 bg-red-50/60' : 'mr-8 bg-slate-50'"
              class="rounded-md border border-slate-200 p-3"
            >
              <span class="mb-1 block text-xs text-slate-500">{{ turn.role === 'user' ? '你' : '老师' }}</span>
              <DialogueText
                :english="turn.text"
                :chinese="turn.translation_zh || undefined"
              />
            </li>
          </ol>
          <section
            v-if="selected.review"
            class="mt-5 space-y-3 border-t border-slate-200 pt-4"
          >
            <h3 class="font-bold">
              复盘
            </h3>
            <DialogueText
              :english="selected.review.summary_en || '本次对话已保存。'"
              :chinese="selected.review.summary_zh"
            />
            <p
              v-if="selected.review.used_expressions.length"
              class="text-sm text-brand-accent"
            >
              使用了：{{ selected.review.used_expressions.map(expression => expression.english).join(' · ') }}
            </p>
            <p
              v-if="selected.review.practice_points.length"
              class="text-sm text-slate-600"
            >
              建议复习：{{ selected.review.practice_points.map(point => point.advice_zh).join('；') }}
            </p>
          </section>
        </RetroCard>
      </div>
    </div>
  </div>
</template>
