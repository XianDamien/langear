<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import AppHeader from '@/components/layout/AppHeader.vue'

const route = useRoute()
const mobileMenuOpen = ref(false)
const langPair = ref('en-zh')

const isFullscreen = computed(() => route.meta.fullscreen === true)
</script>

<template>
  <!-- Fullscreen layout for study session -->
  <div
    v-if="isFullscreen"
    class="min-h-screen bg-brand-dark text-slate-900"
  >
    <router-view />
  </div>

  <!-- Standard layout with sidebar -->
  <div
    v-else
    class="min-h-screen bg-brand-dark text-slate-900 flex"
  >
    <AppSidebar
      :open="mobileMenuOpen"
      @close="mobileMenuOpen = false"
    />

    <main class="flex-1 flex flex-col min-w-0">
      <AppHeader
        v-model:lang-pair="langPair"
        :mobile-menu-open="mobileMenuOpen"
        @toggle-menu="mobileMenuOpen = !mobileMenuOpen"
      />

      <div class="flex-1 p-6 overflow-y-auto">
        <router-view />
      </div>
    </main>

    <!-- Overlay for mobile sidebar -->
    <div
      v-if="mobileMenuOpen"
      class="fixed inset-0 bg-black bg-opacity-70 z-40 md:hidden"
      @click="mobileMenuOpen = false"
    />
  </div>
</template>
