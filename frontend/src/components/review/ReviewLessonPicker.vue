<script lang="ts">
export interface ReviewLessonOption {
  id: string
  name: string
  path: string
  due: number
}
</script>

<script setup lang="ts">
import { X } from 'lucide-vue-next'
import RetroButton from '@/components/ui/RetroButton.vue'

defineProps<{
  open: boolean
  lessons: ReviewLessonOption[]
  loading?: boolean
  error?: string | null
}>()

const emit = defineEmits<{
  close: []
  select: [deckId: string]
  retry: []
}>()
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
    role="dialog"
    aria-modal="true"
    aria-labelledby="review-picker-title"
    @click.self="emit('close')"
  >
    <div class="flex max-h-[85vh] w-full max-w-lg flex-col border-2 border-slate-900 bg-white shadow-mech">
      <header class="flex items-start justify-between gap-4 border-b border-slate-200 p-5">
        <div>
          <h3
            id="review-picker-title"
            class="text-lg font-bold text-slate-900"
          >
            立即复习
          </h3>
          <p class="mt-1 text-sm text-slate-500">
            选择有到期复习卡片的课程开始练习
          </p>
        </div>
        <button
          type="button"
          class="-m-1 p-1 text-slate-400 transition-colors hover:text-slate-800"
          aria-label="关闭"
          @click="emit('close')"
        >
          <X :size="18" />
        </button>
      </header>

      <div class="overflow-y-auto p-5">
        <p
          v-if="loading"
          class="py-10 text-center text-slate-500"
        >
          加载中...
        </p>
        <div
          v-else-if="error"
          role="alert"
          class="rounded border border-amber-300 bg-amber-50 p-4"
        >
          <p>{{ error }}</p>
          <button
            type="button"
            class="mt-2 underline"
            @click="emit('retry')"
          >
            重试
          </button>
        </div>
        <p
          v-else-if="!lessons.length"
          class="py-10 text-center text-slate-500"
        >
          当前没有到期的复习卡片。
        </p>
        <div
          v-else
          class="space-y-2"
        >
          <div
            v-for="lesson in lessons"
            :key="lesson.id"
            class="flex items-center justify-between gap-3 border border-slate-200 p-3 transition-colors hover:border-brand-accent"
          >
            <div class="min-w-0">
              <p class="truncate font-bold">
                {{ lesson.name }}
              </p>
              <p class="truncate text-sm text-slate-500">
                {{ lesson.path }}
              </p>
            </div>
            <div class="flex shrink-0 items-center gap-3">
              <span class="text-sm text-slate-500">
                <span class="font-pixel text-lg text-brand-accent">{{ lesson.due }}</span>
                张待复习
              </span>
              <RetroButton
                size="sm"
                :aria-label="`开始复习 ${lesson.name}`"
                @click="emit('select', lesson.id)"
              >
                开始复习
              </RetroButton>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
