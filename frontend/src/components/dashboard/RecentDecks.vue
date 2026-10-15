<script setup lang="ts">
import { Play } from 'lucide-vue-next'
import type { Deck } from '@/types/domain'

defineProps<{
  decks: Deck[]
  loading?: boolean
  error?: string | null
}>()

const emit = defineEmits<{
  play: [deckId: string]
  retry: []
}>()
</script>

<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 uppercase text-brand-accent">
      学习中
    </h2>
    <p v-if="loading" role="status" class="p-4 text-slate-500">课程加载中...</p>
    <div v-else-if="error" role="alert" class="border border-amber-400 p-4">
      <p>{{ error }}</p>
      <button type="button" class="mt-3 underline" @click="emit('retry')">重试</button>
    </div>
    <div v-else-if="!decks.length" class="border border-dashed border-slate-200 p-6 text-slate-500">
      <p>还没有加入课程</p>
      <RouterLink to="/library" class="mt-3 inline-block text-brand-accent underline">去题库添加课程</RouterLink>
    </div>
    <div v-else class="space-y-3">
      <div
        v-for="deck in decks"
        :key="deck.id"
        class="bg-white p-4 border border-slate-200 hover:border-brand-accent cursor-pointer transition-colors flex justify-between items-center group"
        @click="emit('play', deck.id)"
      >
        <div>
          <div class="font-bold text-lg group-hover:text-brand-accent">
            {{ deck.name }}
          </div>
          <div class="text-sm text-slate-500">
            <span class="font-pixel text-brand-accent">{{ deck.newCards }}</span>
            新卡 •
            <span class="font-pixel text-brand-accent">{{ deck.reviewCards }}</span>
            复习
          </div>
        </div>
        <Play
          class="text-slate-400 group-hover:text-brand-accent"
          fill="currentColor"
        />
      </div>
    </div>
  </div>
</template>
