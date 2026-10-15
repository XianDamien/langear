import { describe, expect, it } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import LoginView from '@/views/LoginView.vue'
import { useAuthStore } from '@/stores/auth'
import { mountWithApp } from '../../helpers/mountWithApp'

async function mountLogin() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', component: LoginView },
      { path: '/dashboard', component: { template: '<div />' } },
    ],
  })
  await router.push('/login?redirect=/dashboard')
  await router.isReady()
  return { router, wrapper: mountWithApp(LoginView, { global: { plugins: [router] } }) }
}

describe('LoginView', () => {
  it('accepts an existing seven-character password and redirects after login', async () => {
    const { router, wrapper } = await mountLogin()
    await wrapper.get('input[autocomplete="username"]').setValue('test')
    const password = wrapper.get('input[type="password"]')
    await password.setValue('test123')
    expect(password.attributes('minlength')).toBeUndefined()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(useAuthStore().loginWithPassword).toHaveBeenCalledWith({
      username: 'test', password: 'test123',
    })
    expect(router.currentRoute.value.path).toBe('/dashboard')
    wrapper.unmount()
  })

  it('keeps the eight-character minimum for registration', async () => {
    const { wrapper } = await mountLogin()
    await wrapper.get('button.mt-6').trigger('click')
    expect(wrapper.get('input[type="password"]').attributes('minlength')).toBe('8')
    wrapper.unmount()
  })
})
