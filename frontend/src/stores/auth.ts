import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { useRouter } from 'vue-router'
import { clearAccessToken, getAccessToken, setAccessToken } from '@/services/authToken'
import { fetchCurrentUser, login, register, type LoginPayload, type RegisterPayload } from '@/services/api/auth'
import type { CurrentUser } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const router = useRouter()
  const token = ref<string | null>(getAccessToken())
  const user = ref<CurrentUser | null>(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value))

  async function loginWithPassword(payload: LoginPayload) {
    loading.value = true
    try {
      const { data } = await login(payload)
      token.value = data.access_token
      user.value = data.user
      setAccessToken(data.access_token)
    } finally {
      loading.value = false
    }
  }

  async function registerWithPassword(payload: RegisterPayload) {
    loading.value = true
    try {
      const { data } = await register(payload)
      token.value = data.access_token
      user.value = data.user
      setAccessToken(data.access_token)
    } finally {
      loading.value = false
    }
  }

  async function loadCurrentUser() {
    if (!token.value || user.value) return
    try {
      const { data } = await fetchCurrentUser()
      user.value = data
    } catch {
      logout(false)
    }
  }

  function logout(redirect = true) {
    token.value = null
    user.value = null
    clearAccessToken()
    if (redirect) {
      void router.push({ name: 'Login' })
    }
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    loginWithPassword,
    registerWithPassword,
    loadCurrentUser,
    logout,
  }
})
