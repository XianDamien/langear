<script setup lang="ts">
import { Award } from 'lucide-vue-next'
import RetroCard from '@/components/ui/RetroCard.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import ProgressBar from '@/components/ui/ProgressBar.vue'
import type { DashboardData } from '@/types/api'

defineProps<{
  stats: DashboardData['stats']
}>()

const emit = defineEmits<{
  reviewAll: []
}>()
</script>

<template>
  <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
    <RetroCard title="积分">
      <div class="flex items-center gap-3">
        <Award
          class="text-yellow-400"
          :size="32"
        />
        <div>
          <div class="text-3xl font-bold font-pixel text-brand-accent">
            {{ stats.points.toLocaleString() }}
          </div>
          <div class="text-xs text-slate-500 uppercase">
            已获得积分
          </div>
        </div>
      </div>
    </RetroCard>

    <RetroCard title="待复习">
      <div class="flex flex-col gap-2">
        <div class="text-3xl font-bold text-brand-accent">
          <span class="font-pixel">{{ stats.reviewsPending }}</span>
          <span>张卡</span>
        </div>
        <RetroButton
          size="sm"
          variant="primary"
          @click="emit('reviewAll')"
        >
          立即复习
        </RetroButton>
      </div>
    </RetroCard>

    <RetroCard title="连续学习">
      <div class="flex items-center gap-3">
        <div class="text-4xl font-bold text-brand-accent font-pixel">
          {{ stats.streakDays }}
        </div>
        <div class="flex flex-col">
          <span class="font-bold">天</span>
          <span class="text-xs text-green-500">目标达成 ✓</span>
        </div>
      </div>
    </RetroCard>

    <RetroCard title="今日目标">
      <p class="text-sm text-slate-500 mb-2">
        熟能生巧
      </p>
      <ProgressBar
        :value="stats.dailyDone"
        :max="stats.dailyGoal"
        label="句子"
      />
    </RetroCard>
  </div>
</template>
