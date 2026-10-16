<script setup lang="ts">
import type { ResourceCard } from '@/services/contentCore'

defineProps<{ card: Pick<ResourceCard, 'front' | 'card_template_key'> }>()
</script>

<template>
  <div class="flex w-full min-w-0 flex-col items-center justify-center text-center">
    <p class="max-w-full break-words text-3xl font-bold text-slate-900 sm:text-4xl md:text-5xl">
      {{ card.card_template_key === 'vocabulary_chinese_to_english' ? card.front.meaning : card.front.word }}
    </p>
  </div>
</template>
