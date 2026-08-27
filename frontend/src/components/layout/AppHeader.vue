<script setup lang="ts">
import { onMounted } from 'vue'
import { LogOut, Menu, User, X } from 'lucide-vue-next'
import LanguageSelector from '../ui/LanguageSelector.vue'
import RetroButton from '../ui/RetroButton.vue'
import { useAuthStore } from '@/stores/auth'

defineProps<{
  mobileMenuOpen: boolean
}>()

const emit = defineEmits<{
  toggleMenu: []
}>()

const langPair = defineModel<string>('langPair', { default: 'en-zh' })
const authStore = useAuthStore()

onMounted(() => {
  void authStore.loadCurrentUser()
})
</script>

<template>
  <header
    class="h-20 border-b border-slate-200 bg-brand-panel flex items-center justify-between px-6 sticky top-0 z-40 shadow-mech-sm"
  >
    <button
      class="md:hidden text-slate-900"
      @click="emit('toggleMenu')"
    >
      <component :is="mobileMenuOpen ? X : Menu" />
    </button>

    <div class="hidden md:block text-slate-500 uppercase text-sm">
      流利学习引擎
    </div>

    <div class="flex items-center gap-4">
      <LanguageSelector v-model="langPair" />
      <div class="hidden sm:flex items-center gap-2 text-sm font-bold text-slate-700">
        <User class="h-4 w-4 text-brand-accent" />
        <span>{{ authStore.user?.username || '已登录' }}</span>
      </div>
      <RetroButton
        variant="secondary"
        size="sm"
        :icon="LogOut"
        @click="authStore.logout()"
      >
        退出
      </RetroButton>
    </div>
  </header>
</template>
