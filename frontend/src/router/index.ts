import { createRouter, createWebHistory } from 'vue-router'
import { contentCoreEnabled } from '@/services/contentCore'
import { useCoreAuthStore } from '@/stores/coreAuth'
import { hasAccessToken } from '@/services/authToken'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: contentCoreEnabled ? '/library' : '/dashboard',
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true, fullscreen: true },
    },
    {
      path: '/dashboard',
      name: 'Dashboard',
      component: () => import('@/views/DashboardView.vue'),
    },
    {
      path: '/library',
      name: 'Library',
      component: contentCoreEnabled ? () => import('@/views/ResourceLibraryView.vue') : () => import('@/views/LibraryView.vue'),
    },
    {
      path: '/my-courses',
      name: 'MyCourses',
      component: () => import('@/views/MyCoursesView.vue'),
    },
    {
      path: '/study/:lessonId',
      name: 'Study',
      component: () => import('@/views/StudySessionView.vue'),
      meta: { fullscreen: true },
    },
    {
      path: '/review/:deckId',
      name: 'DeckReview',
      component: () => import('@/views/DeckReviewView.vue'),
      meta: { fullscreen: true },
    },
    {
      path: '/decks/:deckId/settings',
      name: 'DeckSettings',
      redirect: to => ({ name: 'Settings', query: { deck_id: String(to.params.deckId) } }),
    },
    {
      path: '/cards/:cardId',
      name: 'CardDetail',
      component: () => import('@/views/CardDetailView.vue'),
    },
    {
      path: '/summary/:lessonId',
      name: 'Summary',
      component: () => import('@/views/SummaryView.vue'),
    },
    {
      path: '/settings',
      name: 'Settings',
      component: () => import('@/views/SettingsView.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  if (contentCoreEnabled) {
    const auth = useCoreAuthStore()
    if (to.name === 'Login') return true
    try { await auth.check() }
    catch { return { name: 'Login', query: { redirect: to.fullPath } } }
    if (to.name !== 'Library') return { name: 'Library' }
    return true
  }
  if (to.meta.public) {
    if (to.name === 'Login' && hasAccessToken()) {
      return { name: 'Dashboard' }
    }
    return true
  }

  if (!hasAccessToken()) {
    return {
      name: 'Login',
      query: { redirect: to.fullPath },
    }
  }

  return true
})

export default router
