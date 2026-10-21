<script setup lang="ts">
import { ref, watch } from 'vue'
const props = defineProps<{ english: string; chinese?: string; translate?: () => Promise<string> }>()
const translated = ref(false)
const translation = ref('')
const busy = ref(false)
const failed = ref(false)
let generation = 0
watch(() => props.english, () => {
  generation++; translated.value = false; translation.value = ''; busy.value = false; failed.value = false
})
async function toggle() {
  if (busy.value) return
  if (translated.value) { translated.value = false; return }
  if (props.chinese || translation.value) { translated.value = true; return }
  if (!props.translate) return
  const request = generation
  busy.value = true; failed.value = false
  try {
    const result = await props.translate()
    if (request !== generation) return
    translation.value = result; translated.value = true
  } catch { if (request === generation) failed.value = true }
  finally { if (request === generation) busy.value = false }
}
</script>

<template>
  <div>
    <p
      class="whitespace-pre-wrap text-sm leading-7 text-slate-800"
      lang="en"
    >
      {{ english }}
    </p>
    <button
      v-if="chinese || translate"
      type="button"
      class="mt-1 rounded text-xs text-slate-400 transition-colors hover:text-brand-accent focus-visible:outline-brand-accent"
      :aria-expanded="translated"
      :disabled="busy"
      @click="toggle"
    >
      {{ busy ? '翻译中…' : failed ? '重试中文' : translated ? '收起中文' : '中文' }}
    </button>
    <p
      v-if="translated"
      class="mt-2 border-l-2 border-brand-accent/30 pl-3 text-sm leading-6 text-slate-500"
      lang="zh-CN"
    >
      {{ chinese || translation }}
    </p>
  </div>
</template>
