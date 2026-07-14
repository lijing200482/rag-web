<template>
  <div id="app">
    <!-- 登录/注册页不显示侧边栏 -->
    <template v-if="isAuthPage">
      <router-view />
    </template>

    <template v-else>
      <el-container style="height: 100vh;">
        <el-aside width="200px">
          <div class="logo">
            <h2>RAG 系统</h2>
          </div>

          <!-- 用户信息 -->
          <div class="user-info" v-if="user">
            <el-avatar :size="28">{{ user.username.charAt(0).toUpperCase() }}</el-avatar>
            <span class="username">{{ user.username }}</span>
            <el-button text size="small" @click="handleLogout" style="color: rgba(255,255,255,0.65);">
              退出
            </el-button>
          </div>

          <el-menu
            :default-active="activeMenu"
            class="el-menu-vertical"
            @select="handleMenuSelect"
          >
            <el-menu-item index="chat">
              <el-icon><ChatDotRound /></el-icon>
              <span>聊天问答</span>
            </el-menu-item>
            <el-menu-item index="documents">
              <el-icon><Document /></el-icon>
              <span>文档管理</span>
            </el-menu-item>
            <el-menu-item index="knowledge">
              <el-icon><DataAnalysis /></el-icon>
              <span>知识库</span>
            </el-menu-item>
            <el-menu-item index="settings">
              <el-icon><Setting /></el-icon>
              <span>系统设置</span>
            </el-menu-item>
            <el-menu-item index="users" v-if="user?.is_superuser">
              <el-icon><User /></el-icon>
              <span>用户管理</span>
            </el-menu-item>
          </el-menu>
        </el-aside>

        <el-main>
          <router-view />
        </el-main>
      </el-container>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()
const activeMenu = ref('chat')
const user = ref(null)

const isAuthPage = computed(() => {
  return route.name === 'login' || route.name === 'register'
})

const loadUser = () => {
  const raw = localStorage.getItem('user')
  if (raw) {
    try { user.value = JSON.parse(raw) } catch { user.value = null }
  }
}

onMounted(() => {
  loadUser()
  activeMenu.value = route.name || 'chat'
})

watch(() => route.name, (name) => {
  activeMenu.value = name || 'chat'
  loadUser()
})

const handleMenuSelect = (index) => {
  activeMenu.value = index
  router.push({ name: index })
}

const handleLogout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  user.value = null
  router.push('/login')
}
</script>

<style>
#app {
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.el-aside {
  background-color: #001529;
  color: #fff;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.logo h2 {
  color: #fff;
  margin: 0;
  font-size: 18px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.username {
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.el-menu-vertical {
  border-right: none;
  background-color: #001529;
}

.el-menu-vertical .el-menu-item {
  color: rgba(255, 255, 255, 0.65);
}

.el-menu-vertical .el-menu-item:hover,
.el-menu-vertical .el-menu-item.is-active {
  color: #fff;
  background-color: #1890ff !important;
}

.el-main {
  background-color: #f5f5f5;
  padding: 20px;
  overflow-y: auto;
}
</style>