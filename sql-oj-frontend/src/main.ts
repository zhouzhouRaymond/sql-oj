import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import { useUserStore } from './stores/user'

const app = createApp(App)  // ← 先创建 app
const pinia = createPinia()

// 注册所有 Element Plus 图标（必须在 app 创建之后）
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(pinia)
app.use(router)
app.use(ElementPlus)

// 应用启动时恢复登录态：若本地存在 token 则先向 /users/me/ 校验会话，
// 保证刷新页面后仍能正确识别已登录用户（而不是把页面当作未登录却能继续访问）。
// 会话无效时会在守卫中跳转到登录页。
useUserStore().restoreSession()

app.mount('#app')