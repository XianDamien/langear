<script setup lang="ts">
// Keep the agreed four-rating layout without inventing schedule intervals.
// Enable these actions once the real Review rating contract is connected.
const ratings = [
  { label: 'Again', color: 'bg-red-500' },
  { label: 'Hard', color: 'bg-amber-500' },
  { label: 'Good', color: 'bg-emerald-600' },
  { label: 'Easy', color: 'bg-sky-600' },
]
</script>

<template>
  <div
    class="grid grid-cols-4 gap-2"
    role="group"
    aria-label="复习评分（尚未启用）"
  >
    <button
      v-for="rating in ratings"
      :key="rating.label"
      type="button"
      disabled
      title="评分尚未启用，暂不记录复习进度"
      :class="rating.color"
      class="cursor-not-allowed rounded-md px-2 py-2 text-white shadow-mech-sm"
    >
      <span class="flex flex-col items-center leading-tight">
        <span class="text-sm font-bold uppercase">{{ rating.label }}</span>
        <span class="text-xs font-medium opacity-90">未启用</span>
      </span>
    </button>
  </div>
</template>
