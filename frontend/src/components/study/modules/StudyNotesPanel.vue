<script setup lang="ts">
defineProps<{
  notes: string
}>()

const emit = defineEmits<{
  'update:notes': [value: string]
}>()
</script>

<template>
  <div class="rounded-md border border-slate-200 bg-white p-3">
    <h3 class="mb-2 text-xs font-bold uppercase text-slate-500">
      学习笔记
    </h3>
    <textarea
      class="w-full resize-none rounded border border-slate-200 p-3 text-sm text-slate-900 focus:border-brand-accent focus:outline-none focus:ring-2 focus:ring-brand-accent/20"
      placeholder="记录易错点或理解要点..."
      :value="notes"
      rows="2"
      @input="emit('update:notes', ($event.target as HTMLTextAreaElement).value)"
    />
  </div>
</template>
