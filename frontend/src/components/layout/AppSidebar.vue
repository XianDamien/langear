<script setup lang="ts">
import { Home, BookMarked, BookOpen, Settings as SettingsIcon } from 'lucide-vue-next'
import SidebarNav from './SidebarNav.vue'
import RetroButton from '../ui/RetroButton.vue'

defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
}>()
</script>

<template>
  <aside
    :class="[
      'fixed inset-y-0 left-0 z-50 w-64 bg-brand-panel border-r border-slate-200 transform transition-transform duration-300 md:relative md:translate-x-0',
      open ? 'translate-x-0' : '-translate-x-full',
    ]"
  >
    <div class="p-6 border-b border-slate-200 bg-white">
      <h1
        class="text-3xl font-bold text-brand-accent tracking-tighter flex items-center gap-2"
      >
        <div class="relative w-8 h-8 flex items-center justify-center">
          <SettingsIcon
            class="animate-spin-slow w-8 h-8 text-brand-accent"
            :stroke-width="2.5"
          />
        </div>
        <span>Lan<span class="text-slate-900">Gear</span></span>
      </h1>
    </div>

    <nav class="mt-8">
      <SidebarNav
        to="/dashboard"
        :icon="Home"
        label="总览"
        @navigate="emit('close')"
      />
      <SidebarNav
        to="/library"
        :icon="BookOpen"
        label="题库资源"
        @navigate="emit('close')"
      />
      <SidebarNav
        to="/my-courses"
        :icon="BookMarked"
        label="我的课程"
        @navigate="emit('close')"
      />
      <SidebarNav
        to="/settings"
        :icon="SettingsIcon"
        label="设置"
        @navigate="emit('close')"
      />
    </nav>

    <div class="absolute bottom-8 left-0 w-full px-6">
      <RetroButton
        variant="primary"
        class="w-full"
        size="sm"
      >
        开通专业版
      </RetroButton>
    </div>
  </aside>
</template>
