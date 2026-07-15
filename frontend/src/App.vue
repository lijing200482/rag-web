<template>
  <div id="app">
    <template v-if="isAuthPage">
      <router-view />
    </template>

    <template v-else>
      <el-container class="app-layout">
        <el-aside width="220px" class="app-sidebar">
          <div class="sidebar-logo" @click="router.push('/')" style="cursor: pointer">
            <div class="logo-icon">
              <el-icon :size="24"><DataAnalysis /></el-icon>
            </div>
            <span class="logo-text">RAG 系统</span>
          </div>

          <div class="sidebar-user" v-if="user">
            <el-avatar :size="36" class="user-avatar">
              {{ user.username.charAt(0).toUpperCase() }}
            </el-avatar>
            <div class="user-meta">
              <div class="user-name">{{ user.username }}</div>
              <div class="user-role">{{ user.is_superuser ? '管理员' : '用户' }}</div>
            </div>
            <el-button text size="small" class="logout-btn" @click="handleLogout">
              退出
            </el-button>
          </div>

          <el-menu
            :default-active="activeMenu"
            class="sidebar-menu"
            @select="handleMenuSelect"
          >
            <el-menu-item index="home">
              <el-icon><HomeFilled /></el-icon>
              <span>首页</span>
            </el-menu-item>
            <el-menu-item index="knowledge">
              <el-icon><FolderOpened /></el-icon>
              <span>知识库</span>
            </el-menu-item>
            <el-menu-item index="chat">
              <el-icon><ChatDotRound /></el-icon>
              <span>对话</span>
            </el-menu-item>
            <el-menu-item index="api-keys">
              <el-icon><Key /></el-icon>
              <span>API 密钥</span>
            </el-menu-item>
            <el-menu-item index="users" v-if="user?.is_superuser">
              <el-icon><User /></el-icon>
              <span>用户管理</span>
            </el-menu-item>
          </el-menu>
        </el-aside>

        <el-main class="app-main">
          <router-view />
        </el-main>
      </el-container>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth.js'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const activeMenu = ref('home')

const isAuthPage = computed(() => {
  return route.name === 'login' || route.name === 'register'
})

const user = computed(() => authStore.user)

onMounted(() => {
  activeMenu.value = route.name || 'home'
})

watch(() => route.name, (name) => {
  activeMenu.value = name || 'home'
})

const handleMenuSelect = (index) => {
  activeMenu.value = index
  router.push({ name: index })
}

const handleLogout = () => {
  authStore.clearAuth()
  router.push('/login')
}
</script>

<style>
/* 布局 */
.app-layout {
  height: 100vh;
  background: var(--page-bg);
}

/* 侧边栏 */
.app-sidebar {
  background: var(--sidebar-bg);
  border-right: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;
  user-select: none;
}

.sidebar-logo {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px;
  border-bottom: 1px solid var(--sidebar-border);
}

.logo-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary);
  color: #fff;
  border-radius: 8px;
}

.logo-text {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
}

/* 用户信息 */
.sidebar-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--sidebar-border);
}

.user-avatar {
  flex-shrink: 0;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  font-weight: 600;
}

.user-meta {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-role {
  font-size: 11px;
  color: var(--text-tertiary);
}

.logout-btn {
  color: var(--text-tertiary) !important;
  flex-shrink: 0;
}
.logout-btn:hover {
  color: var(--color-primary) !important;
}

/* 菜单 */
.sidebar-menu {
  border-right: none;
  flex: 1;
  padding: 8px 0;
}

.sidebar-menu .el-menu-item {
  height: 44px;
  line-height: 44px;
  margin: 2px 8px;
  border-radius: 8px;
  color: var(--sidebar-text);
  font-size: 14px;
}

.sidebar-menu .el-menu-item .el-icon {
  font-size: 18px;
}

.sidebar-menu .el-menu-item:hover {
  background: var(--sidebar-hover-bg);
  color: var(--sidebar-text-active);
}

.sidebar-menu .el-menu-item.is-active {
  background: var(--color-primary-bg);
  color: var(--sidebar-text-active);
  font-weight: 500;
}

/* 主区域 */
.app-main {
  background: var(--page-bg);
  padding: 0;
  overflow-y: auto;
}
</style>
