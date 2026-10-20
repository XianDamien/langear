import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import StudySessionView from '@/views/StudySessionView.vue'
import SummaryView from '@/views/SummaryView.vue'

const { reportLegacyRouteHit } = vi.hoisted(() => ({ reportLegacyRouteHit: vi.fn() }))
vi.mock('@/services/legacyRouteTelemetry', () => ({ reportLegacyRouteHit }))

async function start(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/study/:lessonId', component: StudySessionView },
      { path: '/summary/:lessonId', component: SummaryView },
      { path: '/my-courses', name: 'MyCourses', component: { template: '<div>my courses</div>' } },
    ],
  })
  await router.push(path)
  const wrapper = mount(RouterView, { global: { plugins: [router] } })
  await flushPromises()
  return { router, wrapper }
}

describe('retired lesson routes', () => {
  it('reports a Study hit and redirects to My Courses without an ID lookup', async () => {
    const { router, wrapper } = await start('/study/1001')
    expect(reportLegacyRouteHit).toHaveBeenCalledWith('Study')
    expect(router.currentRoute.value.name).toBe('MyCourses')
    expect(router.currentRoute.value.query.notice).toBe('legacy-link-invalid')
    expect(wrapper.text()).toContain('my courses')
    wrapper.unmount()
  })

  it('reports a Summary hit and redirects to My Courses', async () => {
    const { router, wrapper } = await start('/summary/1001')
    expect(reportLegacyRouteHit).toHaveBeenCalledWith('Summary')
    expect(router.currentRoute.value.name).toBe('MyCourses')
    expect(router.currentRoute.value.query.notice).toBe('legacy-link-invalid')
    wrapper.unmount()
  })
})
