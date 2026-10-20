import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { isUuid } from '@/services/api/settings'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...(import.meta.env.DEV ? [{
      path: '/preview/dialogue',
      name: 'DialoguePreview',
      component: () => import('@/views/DialoguePreviewView.vue'),
      meta: { public: true, fullscreen: true },
    }] : []),
    {
      path: '/',
      redirect: '/dashboard',
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
      component: () => import('@/views/LibraryView.vue'),
    },
    {
      path: '/my-courses',
      name: 'MyCourses',
      component: () => import('@/views/MyCoursesView.vue'),
    },
    {
      // Retired numeric-lesson URL: telemetry only, no ID mapping.
      path: '/study/:lessonId',
      name: 'Study',
      component: () => import('@/views/StudySessionView.vue'),
      meta: { fullscreen: true, retired: true },
    },
    {
      // Retired numeric-lesson summary URL: telemetry only.
      path: '/summary/:lessonId',
      name: 'Summary',
      component: () => import('@/views/SummaryView.vue'),
      meta: { retired: true },
    },
    {
      path: '/review/:deckId',
      name: 'DeckReview',
      component: () => import('@/views/ReviewSessionView.vue'),
      meta: { fullscreen: true },
    },
    {
      path: '/decks/:deckId/settings',
      name: 'DeckSettings',
      redirect: to => ({
        name: 'Settings',
        query: isUuid(String(to.params.deckId)) ? { deck_id: String(to.params.deckId) } : {},
      }),
    },
    {
      path: '/cards/:cardId',
      name: 'CardDetail',
      component: () => import('@/views/CardDetailView.vue'),
    },
    {
      path: '/dialogue/history',
      name: 'DialogueHistory',
      component: () => import('@/views/DialogueHistoryView.vue'),
    },
    {
      path: '/settings',
      name: 'Settings',
      component: () => import('@/views/SettingsView.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/dashboard',
    },
  ],
})

router.beforeEach(async (to) => {
  if (import.meta.env.DEV && to.name === 'DialoguePreview') return true

  const auth = useAuthStore()

  if (to.name === 'Login') {
    if (await auth.check()) return { name: 'Dashboard' }
    return true
  }

  if (!(await auth.check())) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  if (to.name === 'DeckReview' && !isUuid(String(to.params.deckId))) {
    return { name: 'MyCourses', query: { notice: 'invalid-deck' } }
  }
  if (to.name === 'CardDetail' && !isUuid(String(to.params.cardId))) {
    return { name: 'MyCourses', query: { notice: 'invalid-card' } }
  }

  return true
})

export default router
