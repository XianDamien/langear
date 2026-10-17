import { ref } from 'vue'
import { defineStore } from 'pinia'
import { coreHttp, setCoreCsrf, type CoreIdentity } from '@/services/contentCore'

export const useCoreAuthStore = defineStore('coreAuth', () => {
  const user = ref<CoreIdentity['user'] | null>(null)
  const loading = ref(false)
  async function check() {
    try { user.value = (await coreHttp.get<CoreIdentity>('/auth/me')).data.user; return true }
    catch (error) { user.value = null; throw error }
  }
  async function signIn(mode: 'login' | 'register', email: string, password: string) {
    loading.value = true
    try {
      const { data } = await coreHttp.post<CoreIdentity>(`/auth/${mode}`, { email, password })
      user.value = data.user
      setCoreCsrf(data.csrf_token || '')
    } finally { loading.value = false }
  }
  async function logout() {
    await coreHttp.post('/auth/logout')
    user.value = null
    setCoreCsrf('')
  }
  return { user, loading, check, signIn, logout }
})
