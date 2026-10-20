import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import { setUnauthorizedHandler } from './services/coreApi'
import { useAuthStore } from './stores/auth'
import './assets/main.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus)

// A 401 from any in-page request ends the expired session immediately.
setUnauthorizedHandler(() => {
  useAuthStore(pinia).clear()
  const current = router.currentRoute.value
  if (current.name !== 'Login') {
    void router.push({ name: 'Login', query: { redirect: current.fullPath } })
  }
})

app.mount('#app')
