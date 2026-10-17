<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { libraryContent } from '@/services/libraryContent'
import { fieldLabels } from '@/services/contentCore'

const props = defineProps<{ fields: Record<string, string> }>()
const urls = ref<Record<string, string>>({})
const errors = ref<Record<string, boolean>>({})
const container = ref<HTMLElement>()
const mediaKeys = new Set(['reference_audio', 'image'])
const entries = computed(() => Object.entries(props.fields).filter(([, value]) => !!value))
let generation = 0
function stopAudio() {
  container.value?.querySelectorAll('audio').forEach(audio => audio.pause())
}
async function loadMedia() {
  const current = ++generation
  stopAudio()
  urls.value = {}
  errors.value = {}
  await Promise.all(entries.value.filter(([key]) => mediaKeys.has(key)).map(async ([key, id]) => {
    try {
      const { data } = await libraryContent.get<{ url: string }>(`/media-assets/${id}/url`)
      if (current === generation) urls.value[key] = data.url
    } catch {
      if (current === generation) errors.value[key] = true
    }
  }))
}
watch(() => props.fields, loadMedia, { immediate: true })
onBeforeUnmount(() => { generation++; stopAudio() })
</script>

<template>
  <div
    ref="container"
    class="w-full space-y-6"
    data-testid="practice-fields"
  >
    <div
      v-for="[key, value] in entries"
      :key="key"
      class="min-w-0"
    >
      <p class="mb-2 text-sm text-slate-500">
        {{ fieldLabels[key] || key }}
      </p>
      <template v-if="mediaKeys.has(key)">
        <div
          v-if="errors[key]"
          role="alert"
          class="text-sm text-amber-700"
        >
          {{ key === 'image' ? '图片' : '音频' }}加载失败
          <button
            type="button"
            class="ml-2 underline"
            @click="loadMedia"
          >
            重试
          </button>
        </div>
        <audio
          v-else-if="urls[key] && key === 'reference_audio'"
          :src="urls[key]"
          controls
          preload="metadata"
          class="mx-auto w-full max-w-md"
          @error="errors[key] = true"
        />
        <img
          v-else-if="urls[key]"
          :src="urls[key]"
          alt="辅助图片"
          class="mx-auto max-h-80 max-w-full"
          @error="errors[key] = true"
        >
        <p
          v-else
          role="status"
          class="text-sm text-slate-500"
        >
          加载中…
        </p>
      </template>
      <p
        v-else
        class="whitespace-pre-wrap break-words text-xl leading-relaxed sm:text-2xl"
      >
        {{ value }}
      </p>
    </div>
  </div>
</template>
