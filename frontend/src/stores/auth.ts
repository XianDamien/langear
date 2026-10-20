import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  fetchCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
  type CoreCollection,
  type CoreUser,
} from '@/services/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CoreUser | null>(null)
  const collection = ref<CoreCollection | null>(null)
  const loading = ref(false)
  const checked = ref(false)

  const isAuthenticated = computed(() => Boolean(user.value))

  function apply(identity: { user: CoreUser; collection: CoreCollection }) {
    user.value = identity.user
    collection.value = identity.collection
    checked.value = true
  }

  function clear() {
    user.value = null
    collection.value = null
    checked.value = true
  }

  async function check(): Promise<boolean> {
    try {
      apply(await fetchCurrentUser())
      return true
    } catch {
      clear()
      return false
    }
  }

  async function login(identifier: string, password: string) {
    loading.value = true
    try {
      apply(await loginRequest(identifier, password))
    } finally {
      loading.value = false
    }
  }

  async function register(payload: {
    username?: string
    email?: string
    password: string
    invitationCode?: string
  }) {
    loading.value = true
    try {
      apply(await registerRequest(payload))
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      await logoutRequest()
    } finally {
      clear()
    }
  }

  return {
    user,
    collection,
    loading,
    checked,
    isAuthenticated,
    check,
    login,
    register,
    logout,
    clear,
  }
})
