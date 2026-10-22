<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Eye, EyeOff, KeyRound, Lock, LogIn, Mail, Settings, Sparkles, User, UserPlus } from 'lucide-vue-next'
import { authError } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'
import RetroButton from '@/components/ui/RetroButton.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const formError = ref('')

const mode = ref<'login' | 'register'>('login')
const showPassword = ref(false)

const form = reactive({
  identifier: '',
  username: '',
  email: '',
  invitationCode: '',
  password: '',
})

const title = computed(() => (mode.value === 'login' ? '登录账号' : '创建账号'))
const submitIcon = computed(() => (mode.value === 'login' ? LogIn : UserPlus))

function switchMode(newMode?: 'login' | 'register') {
  formError.value = ''
  if (newMode) {
    mode.value = newMode
  } else {
    mode.value = mode.value === 'login' ? 'register' : 'login'
  }
}

async function submit() {
  formError.value = ''
  try {
    if (mode.value === 'login') {
      await authStore.login(form.identifier, form.password)
    } else {
      if (!form.username.trim() && !form.email.trim()) {
        formError.value = '请填写用户名或邮箱。'
        return
      }
      await authStore.register({
        username: form.username || undefined,
        email: form.email || undefined,
        password: form.password,
        invitationCode: form.invitationCode || undefined,
      })
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    await router.push(redirect)
  } catch (error) {
    formError.value = authError(error)
  }
}
</script>

<template>
  <div class="relative min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-center items-center px-4 py-12 sm:px-6 lg:px-8 overflow-hidden select-none">
    <!-- 背景机械氛围修饰：微弱的网格蓝图与光晕 -->
    <div
      class="pointer-events-none absolute inset-0 opacity-[0.03]"
      style="background-image: radial-gradient(#ffffff 1px, transparent 1px); background-size: 24px 24px;"
    />
    <div class="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 w-[600px] h-[350px] bg-brand-accent/10 blur-[120px] rounded-full" />

    <!-- 顶部居中：品牌 Logo、齿轮动效与核心标语 -->
    <div class="relative z-10 w-full max-w-md text-center mb-8 flex flex-col items-center">
      <!-- 品牌名称：带联动齿轮的主视觉 -->
      <div class="flex items-center justify-center gap-3 mb-3">
        <div class="relative flex items-center justify-center w-12 h-12 rounded-xl bg-slate-900 border-2 border-slate-700/80 shadow-mech text-brand-accent group">
          <Settings class="w-7 h-7 text-brand-accent animate-spin-slow transition-transform" />
          <div class="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-slate-950 border border-slate-700 flex items-center justify-center">
            <Sparkles class="w-2.5 h-2.5 text-brand-accent" />
          </div>
        </div>
        <h1 class="text-4xl sm:text-5xl font-black tracking-tight text-white flex items-baseline">
          Lan<span class="text-brand-accent">Gear</span>
        </h1>
      </div>

      <!-- 核心产品标语：“让语言学习成为齿轮” -->
      <p class="text-lg sm:text-xl font-bold text-slate-200 tracking-tight">
        让语言学习成为齿轮
      </p>
    </div>

    <!-- 居中控制台面板 -->
    <div class="relative z-10 w-full max-w-md bg-white text-slate-900 rounded-none border-2 border-slate-300 shadow-[0_20px_50px_rgba(0,0,0,0.4)] p-6 sm:p-8">
      <!-- 机械风切换分段 Tab -->
      <div class="grid grid-cols-2 p-1 bg-slate-100 border border-slate-200 mb-6">
        <button
          type="button"
          class="py-2.5 text-sm font-bold uppercase tracking-wider transition-all duration-150 flex items-center justify-center gap-1.5 cursor-pointer"
          :class="mode === 'login' ? 'bg-white text-slate-950 shadow-sm border border-slate-200' : 'text-slate-500 hover:text-slate-900'"
          @click="switchMode('login')"
        >
          <LogIn class="w-4 h-4" />
          登录
        </button>
        <button
          type="button"
          class="py-2.5 text-sm font-bold uppercase tracking-wider transition-all duration-150 flex items-center justify-center gap-1.5 cursor-pointer"
          :class="mode === 'register' ? 'bg-white text-slate-950 shadow-sm border border-slate-200' : 'text-slate-500 hover:text-slate-900'"
          @click="switchMode('register')"
        >
          <UserPlus class="w-4 h-4" />
          注册
        </button>
      </div>

      <!-- 提示与错误提示 -->
      <div class="mb-4">
        <h2 class="text-xl font-black text-slate-950">
          {{ title }}
        </h2>
        <p class="text-xs text-slate-500 mt-1">
          {{ mode === 'login' ? '支持使用用户名或注册邮箱登录。' : '填写以下信息创建你的学习账号。' }}
        </p>
      </div>

      <p
        v-if="formError"
        class="mb-4 px-3 py-2 text-xs font-semibold text-red-700 bg-red-50 border border-red-200 flex items-center gap-1.5"
        role="alert"
      >
        <span class="inline-block w-1.5 h-1.5 bg-red-600 rounded-full" />
        {{ formError }}
      </p>

      <form
        class="space-y-4"
        @submit.prevent="submit"
      >
        <!-- 登录模式：用户名或邮箱 -->
        <div v-if="mode === 'login'">
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
            用户名或邮箱
          </label>
          <div class="relative flex items-center">
            <span class="absolute left-3 text-slate-400">
              <User class="w-4 h-4" />
            </span>
            <input
              v-model.trim="form.identifier"
              class="w-full border-2 border-slate-200 bg-slate-50/50 pl-9 pr-4 py-2.5 text-sm text-slate-900 outline-none transition-colors focus:border-brand-accent focus:bg-white"
              placeholder="请输入用户名或邮箱"
              autocomplete="username"
              required
              maxlength="254"
            >
          </div>
        </div>

        <!-- 注册模式：用户名、邮箱、邀请码 -->
        <template v-else>
          <div>
            <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              用户名
            </label>
            <div class="relative flex items-center">
              <span class="absolute left-3 text-slate-400">
                <User class="w-4 h-4" />
              </span>
              <input
                v-model.trim="form.username"
                class="w-full border-2 border-slate-200 bg-slate-50/50 pl-9 pr-4 py-2.5 text-sm text-slate-900 outline-none transition-colors focus:border-brand-accent focus:bg-white"
                placeholder="设置用户名（英文字母、数字等）"
                autocomplete="username"
                minlength="3"
                maxlength="50"
                pattern="[A-Za-z0-9._-]+"
              >
            </div>
          </div>

          <div>
            <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              邮箱（可选）
            </label>
            <div class="relative flex items-center">
              <span class="absolute left-3 text-slate-400">
                <Mail class="w-4 h-4" />
              </span>
              <input
                v-model.trim="form.email"
                class="w-full border-2 border-slate-200 bg-slate-50/50 pl-9 pr-4 py-2.5 text-sm text-slate-900 outline-none transition-colors focus:border-brand-accent focus:bg-white"
                placeholder="用于找回密码或接收报告"
                autocomplete="email"
                type="email"
                maxlength="254"
              >
            </div>
          </div>

          <div>
            <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              邀请码
            </label>
            <div class="relative flex items-center">
              <span class="absolute left-3 text-slate-400">
                <KeyRound class="w-4 h-4" />
              </span>
              <input
                v-model.trim="form.invitationCode"
                class="w-full border-2 border-slate-200 bg-slate-50/50 pl-9 pr-4 py-2.5 text-sm text-slate-900 outline-none transition-colors focus:border-brand-accent focus:bg-white"
                placeholder="若开启邀请制请填写"
                autocomplete="off"
                maxlength="64"
              >
            </div>
            <span class="mt-1 block text-[11px] text-slate-500">如果账号服务开启邀请制，请填写有效邀请码。</span>
          </div>
        </template>

        <!-- 密码字段 -->
        <div>
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
            密码
          </label>
          <div class="relative flex items-center">
            <span class="absolute left-3 text-slate-400">
              <Lock class="w-4 h-4" />
            </span>
            <input
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              class="w-full border-2 border-slate-200 bg-slate-50/50 pl-9 pr-10 py-2.5 text-sm text-slate-900 outline-none transition-colors focus:border-brand-accent focus:bg-white"
              :placeholder="mode === 'register' ? '至少 12 位密码' : '请输入密码'"
              autocomplete="current-password"
              required
              :minlength="mode === 'register' ? 12 : undefined"
            >
            <button
              type="button"
              class="absolute right-3 text-slate-400 hover:text-slate-700 transition-colors p-1"
              @click="showPassword = !showPassword"
            >
              <component :is="showPassword ? EyeOff : Eye" class="w-4 h-4" />
            </button>
          </div>
          <span
            v-if="mode === 'register'"
            class="mt-1 block text-[11px] text-slate-500"
          >
            密码长度至少为 12 位。
          </span>
        </div>

        <!-- 提交按钮 -->
        <div class="pt-2">
          <RetroButton
            class="w-full py-3"
            variant="primary"
            type="submit"
            :icon="submitIcon"
            :disabled="authStore.loading"
          >
            {{ mode === 'login' ? '登 录' : '注 册 并 登 录' }}
          </RetroButton>
        </div>
      </form>

      <!-- 快捷切换模式按钮 -->
      <button
        class="mt-6 w-full text-center text-xs font-medium text-slate-500 hover:text-brand-accent transition-colors"
        type="button"
        @click="switchMode()"
      >
        {{ mode === 'login' ? '还没有账号？点击注册新账号' : '已有账号？返回登录' }}
      </button>
    </div>
  </div>
</template>
