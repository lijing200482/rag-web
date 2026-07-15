import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import HomeView from '../views/HomeView.vue'
import ChatView from '../views/ChatView.vue'
import KnowledgeView from '../views/KnowledgeView.vue'
import KnowledgeDetail from '../views/KnowledgeDetail.vue'
import ApiKeyView from '../views/ApiKeyView.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import UsersView from '../views/UsersView.vue'

function isTokenExpired(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return Date.now() >= payload.exp * 1000
  } catch {
    return true
  }
}

const routes = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { guest: true },
  },
  {
    path: '/register',
    name: 'register',
    component: RegisterView,
    meta: { guest: true },
  },
  {
    path: '/',
    name: 'home',
    component: HomeView,
    meta: { requiresAuth: true },
  },
  {
    path: '/home',
    redirect: '/',
  },
  {
    path: '/chat',
    name: 'chat',
    component: ChatView,
    meta: { requiresAuth: true },
  },
  {
    path: '/knowledge',
    name: 'knowledge',
    component: KnowledgeView,
    meta: { requiresAuth: true },
  },
  {
    path: '/knowledge/:kbId',
    name: 'knowledge-detail',
    component: KnowledgeDetail,
    meta: { requiresAuth: true },
  },
  {
    path: '/api-keys',
    name: 'api-keys',
    component: ApiKeyView,
    meta: { requiresAuth: true },
  },
  {
    path: '/users',
    name: 'users',
    component: UsersView,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const auth = useAuthStore()

  // JWT 过期检测
  if (auth.token && isTokenExpired(auth.token)) {
    auth.clearAuth()
    return next('/login')
  }

  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    next('/login')
  } else if (to.meta.guest && auth.isLoggedIn) {
    next('/')
  } else if (to.meta.requiresAdmin && !auth.isSuperuser) {
    // 非管理员访问管理页面 → 跳回首页
    next('/')
  } else {
    next()
  }
})

export default router
