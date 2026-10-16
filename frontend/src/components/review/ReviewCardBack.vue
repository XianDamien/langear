<script setup lang="ts">

// 背面按模板渲染 Note 可选槽位：缺失槽位不渲染、不用空字符串占位。
defineProps<{
  backSnapshot: { english: string; chinese?: string | null; note?: string | null; phonetic?: string | null }
}>()
</script>

<template>
  <div class="flex w-full flex-col gap-5 text-left">
    <div>
      <p class="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
        English
      </p>
      <p class="break-words text-3xl font-bold text-slate-900">
        {{ backSnapshot.english }}
      </p>
    </div>

    <p
      v-if="backSnapshot.phonetic"
      class="text-base text-slate-500"
    >
      {{ backSnapshot.phonetic }}
    </p>
    <div v-if="backSnapshot.chinese">
      <p class="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
        中文
      </p>
      <p class="text-xl text-slate-700">
        {{ backSnapshot.chinese }}
      </p>
    </div>

    <div v-if="backSnapshot.note">
      <p class="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
        笔记
      </p>
      <p class="text-base leading-relaxed text-slate-600">
        {{ backSnapshot.note }}
      </p>
    </div>
  </div>
</template>
