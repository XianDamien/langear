<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { legacyReviewLocation } from '@/services/reviewNavigation'
import { reviewError } from '@/services/review'

const route = useRoute()
const router = useRouter()
const error = ref('')
let generation = 0
async function redirect() {
  const request = ++generation
  error.value = ''
  try {
    const location = await legacyReviewLocation(String(route.params.lessonId))
    if (request === generation) await router.replace(location)
  } catch (cause) { if (request === generation) error.value = reviewError(cause) }
}
watch(() => route.params.lessonId, redirect, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>

<template>
  <div class="min-h-screen bg-brand-dark p-8 text-center text-slate-600">
    <div
      v-if="error"
      role="alert"
    >
      <p>{{ error }}</p>
      <button
        type="button"
        class="mt-3 underline"
        @click="redirect"
      >
        重试
      </button>
    </div>
    <p
      v-else
      role="status"
    >
      正在进入复习…
    </p>
  </div>
</template>
