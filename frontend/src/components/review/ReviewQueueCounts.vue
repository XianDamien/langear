<script setup lang="ts">
defineProps<{ newRemaining: number; learningRemaining: number; reviewRemaining: number }>()
</script>

<template>
  <dl
    class="flex w-full items-center justify-end gap-4 text-xs sm:gap-6"
    aria-label="剩余卡片"
    role="status"
    aria-live="polite"
    aria-atomic="true"
  >
    <div class="flex items-baseline gap-1.5">
      <dt class="text-slate-500">未学习</dt>
      <dd class="text-base font-bold tabular-nums text-blue-700">{{ newRemaining }}</dd>
    </div>
    <div class="flex items-baseline gap-1.5">
      <dt class="text-slate-500">学习中</dt>
      <dd class="text-base font-bold tabular-nums text-amber-700">{{ learningRemaining }}</dd>
    </div>
    <div class="flex items-baseline gap-1.5">
      <dt class="text-slate-500">待复习</dt>
      <dd class="text-base font-bold tabular-nums text-emerald-700">{{ reviewRemaining }}</dd>
    </div>
  </dl>
</template>
