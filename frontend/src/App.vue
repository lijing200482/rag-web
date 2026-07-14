<template>
  <div id="app">
    <el-container style="height: 100vh;">
      <!-- 侧边栏 -->
      <el-aside width="200px">
        <div class="logo">
          <h2>RAG 系统</h2>
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
        </el-menu>
      </el-aside>

      <!-- 主内容区 -->
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()
const activeMenu = ref('chat')

onMounted(() => {
  activeMenu.value = route.name || 'chat'
})

watch(() => route.name, (name) => {
  activeMenu.value = name || 'chat'
})

const handleMenuSelect = (index) => {
  activeMenu.value = index
  router.push({ name: index })
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
