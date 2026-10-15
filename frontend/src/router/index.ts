import { createRouter, createWebHistory } from 'vue-router'
import { hasAccessToken } from '@/services/authToken'

const router = createRouter({
  history: createWebHistory(),
  routes: [
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
      path: '/study/:lessonId',
      name: 'Study',
      component: () => import('@/views/StudySessionView.vue'),
      meta: { fullscreen: true },
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

router.beforeEach((to) => {
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
