import { describe, expect, it, vi } from 'vitest'
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
  it('submits the username-or-email identifier and redirects after login', async () => {
    const { router, wrapper } = await mountLogin()
    await wrapper.get('input[autocomplete="username"]').setValue('learner@example.com')
    const password = wrapper.get('input[type="password"]')
    await password.setValue('test123')
    expect(password.attributes('minlength')).toBeUndefined()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(useAuthStore().login).toHaveBeenCalledWith('learner@example.com', 'test123')
    expect(router.currentRoute.value.path).toBe('/dashboard')
    wrapper.unmount()
  })

  it('uses the core invitation and six-character password rules when registering', async () => {
    const { wrapper } = await mountLogin()
    await wrapper.get('button.mt-6').trigger('click')
    expect(wrapper.get('input[type="password"]').attributes('minlength')).toBe('6')
    await wrapper.get('input[autocomplete="username"]').setValue('learner')
    await wrapper.get('input[autocomplete="email"]').setValue('learner@example.com')
    await wrapper.get('input[autocomplete="off"]').setValue('INVITE-1')
    await wrapper.get('input[type="password"]').setValue('a-long-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(useAuthStore().register).toHaveBeenCalledWith({
      username: 'learner',
      email: 'learner@example.com',
      password: 'a-long-password',
      invitationCode: 'INVITE-1',
    })
    wrapper.unmount()
  })

  it('shows the server error without leaving the page', async () => {
    const { router, wrapper } = await mountLogin()
    vi.mocked(useAuthStore().login).mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { error: { code: 'INVALID_CREDENTIALS', message: 'Invalid' } } },
    })
    await wrapper.get('input[autocomplete="username"]').setValue('learner')
    await wrapper.get('input[type="password"]').setValue('wrong')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('用户名、邮箱或密码不正确。')
    expect(router.currentRoute.value.path).toBe('/login')
    wrapper.unmount()
  })
})
