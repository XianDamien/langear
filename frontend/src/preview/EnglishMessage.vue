<script setup lang="ts">
import { ref } from 'vue'
defineProps<{ english: string; chinese?: string }>()
const translated = ref(false)
</script>

<template>
  <div>
    <p class="whitespace-pre-wrap text-sm leading-7 text-slate-800">
      {{ english }}
    </p>
    <button
      v-if="chinese"
      type="button"
      class="mt-1 rounded text-xs text-slate-400 transition-colors hover:text-brand-accent focus-visible:outline-brand-accent"
      :aria-expanded="translated"
      @click="translated = !translated"
    >
      {{ translated ? '收起中文' : '中文' }}
    </button>
    <p
      v-if="translated"
      class="mt-2 border-l-2 border-brand-accent/30 pl-3 text-sm leading-6 text-slate-500"
      lang="zh-CN"
    >
      {{ chinese }}
    </p>
  </div>
</template>
