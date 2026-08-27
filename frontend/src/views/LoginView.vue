<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, LogIn, UserPlus } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import RetroButton from '@/components/ui/RetroButton.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const mode = ref<'login' | 'register'>('login')
const form = reactive({
  username: '',
  email: '',
  invitationCode: '',
  password: '',
})

const title = computed(() => (mode.value === 'login' ? '登录 LanGear' : '创建账号'))
const submitIcon = computed(() => (mode.value === 'login' ? LogIn : UserPlus))

async function submit() {
  try {
    if (mode.value === 'login') {
      await authStore.loginWithPassword({
        username: form.username,
        password: form.password,
      })
    } else {
      await authStore.registerWithPassword({
        username: form.username,
        password: form.password,
        email: form.email || undefined,
        invitation_code: form.invitationCode,
      })
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    await router.push(redirect)
  } catch {
    ElMessage.error(mode.value === 'login' ? '用户名或密码不正确' : '账号创建失败')
  }
}
</script>

<template>
  <div class="min-h-screen bg-brand-dark text-slate-900 grid lg:grid-cols-[1.05fr_0.95fr]">
    <section class="hidden lg:flex flex-col justify-between p-10 bg-slate-950 text-white">
      <div class="flex items-center gap-3">
        <div class="h-10 w-10 border-2 border-brand-accent flex items-center justify-center">
          <Lock class="h-5 w-5 text-brand-accent" />
        </div>
        <span class="text-2xl font-bold tracking-tight">LanGear</span>
      </div>

      <div class="max-w-xl">
        <p class="text-sm uppercase tracking-[0.22em] text-brand-accent mb-5">
          AI Retelling Trainer
        </p>
        <h1 class="text-5xl font-black leading-tight mb-6">
          每一次练习都归属于你的个人学习档案
        </h1>
        <p class="text-lg text-slate-300 leading-8">
          登录后，学习卡组、复习计划、练习记录和个性化 FSRS 设置会按用户隔离保存。
        </p>
      </div>

      <div class="grid grid-cols-3 gap-4 text-sm text-slate-300">
        <div class="border border-slate-700 p-4">
          <div class="text-2xl font-black text-white">01</div>
          <div class="mt-2">个人卡组</div>
        </div>
        <div class="border border-slate-700 p-4">
          <div class="text-2xl font-black text-white">02</div>
          <div class="mt-2">复习状态</div>
        </div>
        <div class="border border-slate-700 p-4">
          <div class="text-2xl font-black text-white">03</div>
          <div class="mt-2">练习流水</div>
        </div>
      </div>
    </section>

    <section class="flex items-center justify-center px-5 py-10">
      <div class="w-full max-w-md bg-brand-panel border border-slate-200 shadow-mech p-8">
        <div class="mb-8">
          <div class="text-sm text-slate-500 uppercase mb-2">Account</div>
          <h2 class="text-3xl font-black text-slate-950">{{ title }}</h2>
        </div>

        <form
          class="space-y-5"
          @submit.prevent="submit"
        >
          <label class="block">
            <span class="text-sm font-bold text-slate-700">用户名</span>
            <input
              v-model.trim="form.username"
              class="mt-2 w-full border-2 border-slate-300 bg-white px-4 py-3 outline-none focus:border-brand-accent"
              autocomplete="username"
              required
              minlength="3"
              maxlength="50"
            >
          </label>

          <label
            v-if="mode === 'register'"
            class="block"
          >
            <span class="text-sm font-bold text-slate-700">邮箱</span>
            <input
              v-model.trim="form.email"
              class="mt-2 w-full border-2 border-slate-300 bg-white px-4 py-3 outline-none focus:border-brand-accent"
              autocomplete="email"
              type="email"
            >
          </label>

          <label
            v-if="mode === 'register'"
            class="block"
          >
            <span class="text-sm font-bold text-slate-700">邀请码</span>
            <input
              v-model.trim="form.invitationCode"
              class="mt-2 w-full border-2 border-slate-300 bg-white px-4 py-3 outline-none focus:border-brand-accent"
              autocomplete="off"
              required
              maxlength="64"
            >
          </label>

          <label class="block">
            <span class="text-sm font-bold text-slate-700">密码</span>
            <input
              v-model="form.password"
              class="mt-2 w-full border-2 border-slate-300 bg-white px-4 py-3 outline-none focus:border-brand-accent"
              autocomplete="current-password"
              type="password"
              required
              minlength="8"
            >
          </label>

          <RetroButton
            class="w-full"
            variant="primary"
            type="submit"
            :icon="submitIcon"
            :disabled="authStore.loading"
          >
            {{ mode === 'login' ? '登录' : '创建并登录' }}
          </RetroButton>
        </form>

        <button
          class="mt-6 text-sm text-slate-600 hover:text-brand-accent"
          type="button"
          @click="mode = mode === 'login' ? 'register' : 'login'"
        >
          {{ mode === 'login' ? '没有账号？创建账号' : '已有账号？返回登录' }}
        </button>
      </div>
    </section>
  </div>
</template>
