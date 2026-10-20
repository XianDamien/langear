<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { reportLegacyRouteHit } from '@/services/legacyRouteTelemetry'

const router = useRouter()

onMounted(() => {
  reportLegacyRouteHit('Summary')
  void router.replace({ name: 'MyCourses', query: { notice: 'legacy-link-invalid' } })
})
</script>

<template>
  <div class="min-h-screen bg-brand-dark p-8 text-center text-slate-600">
    <p role="status">
      旧链接已失效，正在返回我的课程…
    </p>
  </div>
</template>
