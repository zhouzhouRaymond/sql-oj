import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../stores/user'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('../views/Login.vue')
    },
    {
      path: '/',
      redirect: '/questions'
    },
    // ========== 学生端页面（无布局）==========
    {
      path: '/questions',
      name: 'QuestionList',
      component: () => import('../views/student/QuestionList.vue'),
      meta: { requiresAuth: true, allowedRoles: ['student', 'teacher'] }
    },
    {
      path: '/questions/:id',
      name: 'QuestionDetail',
      component: () => import('../views/student/QuestionDetail.vue'),
      meta: { requiresAuth: true, allowedRoles: ['student', 'teacher'] }
    },
    {
      path: '/exams',
      name: 'ExamList',
      component: () => import('../views/student/ExamList.vue'),
      meta: { requiresAuth: true, allowedRoles: ['student', 'teacher'] }
    },
    // 学生端的「我的提交」/「个人中心」共用页面（学生 / 教师均可访问）。
    // 教师端菜单走 /teacher/submissions、/teacher/profile（见下方 /teacher 子路由），
    // 这两个顶层路由保留给学生，以及从学生端页面跳转进来时使用（带 ?from= 可原路返回）。
    {
      path: '/submissions',
      name: 'MySubmissions',
      component: () => import('../views/MySubmissions.vue'),
      meta: { requiresAuth: true, allowedRoles: ['student', 'teacher'] }
    },
    {
      path: '/profile',
      name: 'Profile',
      component: () => import('../views/Profile.vue'),
      meta: { requiresAuth: true, allowedRoles: ['student', 'teacher'] }
    },
    {
      path: '/exam/:id',
      name: 'ExamPanel',
      component: () => import('../views/student/ExamPanel.vue'),
      meta: { requiresAuth: true, allowedRoles: ['student'] }
    },
    {
      path: '/exam/:id/result',
      name: 'ExamResult',
      component: () => import('../views/student/ExamResult.vue'),
      meta: { requiresAuth: true, allowedRoles: ['student', 'teacher'] }
    },
    // ========== 教师端页面（使用 Layout）==========
    {
      path: '/teacher',
      component: () => import('../views/teacher/Layout.vue'),
      meta: { requiresAuth: true, allowedRoles: ['teacher'] },
      children: [
        {
          path: 'questions',
          name: 'TeacherQuestionList',
          component: () => import('../views/teacher/QuestionManage.vue')
        },
        {
          path: 'questions/:id',
          name: 'TeacherQuestionDetail',
          component: () => import('../views/teacher/QuestionDetail.vue')
        },
        {
          path: 'questions/create',
          name: 'CreateQuestion',
          component: () => import('../views/teacher/CreateQuestion.vue')
        },
        {
          path: 'exams',
          name: 'ExamManage',
          component: () => import('../views/teacher/ExamManage.vue')
        },
        {
          path: 'stats',
          name: 'Statistics',
          component: () => import('../views/teacher/Statistics.vue')
        },
        {
          path: 'accounts',
          name: 'AccountManage',
          component: () => import('../views/teacher/AccountManage.vue')
        },
        // 与学生端共用同一页面组件，但渲染在教师布局内：点击菜单后侧边栏常驻，
        // 与「题目管理 / 考试管理 / 统计分析 / 账号管理」的打开方式保持一致。
        {
          path: 'submissions',
          name: 'TeacherSubmissions',
          component: () => import('../views/MySubmissions.vue')
        },
        {
          path: 'profile',
          name: 'TeacherProfile',
          component: () => import('../views/Profile.vue')
        },
        {
          path: '',
          redirect: '/teacher/questions'
        }
      ]
    }
  ]
})

// 各角色对应的首页
const homeOf = (role?: string) => (role === 'teacher' ? '/teacher' : '/questions')

// 路由守卫：检查登录 + 角色权限
// 关键点：不能只判断 localStorage 里有没有 token（任意字符串都能伪造），
// 必须校验会话有效（token 能换回用户信息）后才允许进入受保护页面，
// 否则未登录 / 登录已失效时仍会渲染题目页并暴露提交入口。
router.beforeEach(async (to, _from, next) => {
  const userStore = useUserStore()

  // 登录页：若已登录（token 有效）则直接进入对应首页，避免出现
  // “看到登录页、以为未登录，却仍能访问题目页并提交”的困惑。
  if (to.path === '/login') {
    if (userStore.token) {
      const ok = userStore.user ? true : await userStore.restoreSession()
      if (ok) {
        next(homeOf(userStore.user?.user_type))
        return
      }
    }
    next()
    return
  }

  // 公开页面直接放行
  if (!to.meta.requiresAuth) {
    next()
    return
  }

  // 无 token：未登录，跳转登录页
  if (!userStore.token) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  // 有 token 但内存中还没有用户信息（例如刷新页面后）：先校验并恢复会话
  if (!userStore.user) {
    const ok = await userStore.restoreSession()
    if (!ok) {
      // token 失效 / 伪造，清除后跳转登录页
      next({ path: '/login', query: { redirect: to.fullPath } })
      return
    }
  }

  // 检查角色权限（用户信息缺失时同样拒绝，避免绕过角色校验）
  const allowedRoles = to.meta.allowedRoles as string[] | undefined
  if (allowedRoles && (!userStore.user || !allowedRoles.includes(userStore.user.user_type))) {
    if (userStore.user?.user_type === 'teacher') {
      next('/teacher')
    } else {
      next('/questions')
    }
    return
  }

  next()
})

export default router
