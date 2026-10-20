<script setup lang="ts">
import type { DashboardLeaderboardEntry } from '@/services/content'

defineProps<{ entries: DashboardLeaderboardEntry[] }>()
</script>

<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 uppercase text-brand-accent">
      排行榜
    </h2>
    <div class="bg-white p-4 border border-slate-200 shadow-mech-sm">
      <p
        v-if="!entries.length"
        class="text-sm text-slate-500"
        role="status"
      >
        暂无排行数据
      </p>
      <template v-else>
        <div
          v-for="(leader, idx) in entries"
          :key="`${leader.rank}-${leader.name}`"
          :class="[
            'flex justify-between pb-2 mb-2',
            idx < entries.length - 1 ? 'border-b border-slate-200' : '',
            leader.is_user ? 'bg-red-50 px-2 -mx-2' : '',
            !leader.is_user && idx === entries.length - 1 ? 'text-slate-500' : '',
          ]"
        >
          <span>
            <span class="font-pixel text-brand-accent">{{ leader.rank }}</span>.
            {{ leader.name }}
          </span>
          <span :class="leader.is_user ? 'text-slate-900 font-bold' : 'text-brand-accent'">
            <span class="font-pixel text-brand-accent">{{ leader.points }}</span>
            积分
          </span>
        </div>
      </template>
    </div>
  </div>
</template>
