<template>
  <div class="session-sidebar">
    <!-- 新建会话按钮 -->
    <div class="sidebar-header">
      <el-button type="primary" :icon="Plus" class="new-session-btn" @click="$emit('new')">
        新建会话
      </el-button>
    </div>

    <!-- 会话列表 -->
    <div class="session-list">
      <div v-if="loading" class="loading-tip">
        <el-icon class="is-loading"><Loading /></el-icon>
        加载中...
      </div>

      <div v-else-if="sessions.length === 0" class="empty-tip">
        暂无会话，点击上方按钮开始
      </div>

      <div
        v-else
        v-for="s in sessions"
        :key="s.id"
        class="session-item"
        :class="{ active: s.id === activeId }"
        @click="$emit('select', s)"
        @contextmenu.prevent="openMenu($event, s)"
      >
        <el-icon class="session-icon"><ChatDotRound /></el-icon>
        <span class="session-title">{{ s.title || '新对话' }}</span>
        <span class="session-time">{{ formatTime(s.updated_at) }}</span>
      </div>
    </div>

    <!-- 右键菜单 -->
    <ul
      v-if="menu.visible"
      class="context-menu"
      :style="{ top: menu.top + 'px', left: menu.left + 'px' }"
    >
      <li @click="onRename">
        <el-icon><Edit /></el-icon> 重命名
      </li>
      <li class="danger" @click="onDelete">
        <el-icon><Delete /></el-icon> 删除
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, ChatDotRound, Edit, Delete, Loading } from '@element-plus/icons-vue'
import { listSessions, deleteSession, renameSession } from '../api/index.js'

const props = defineProps({
  activeId: { type: Number, default: null }
})

const emit = defineEmits(['new', 'select', 'changed'])

const sessions = ref([])
const loading = ref(false)
const menu = ref({ visible: false, top: 0, left: 0, target: null })

// 拉取会话列表
const fetchSessions = async () => {
  loading.value = true
  try {
    sessions.value = await listSessions()
  } catch (e) {
    ElMessage.error('加载会话列表失败：' + e.message)
  } finally {
    loading.value = false
  }
}

// 格式化时间
const formatTime = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

// 右键菜单
const openMenu = (e, session) => {
  menu.value = {
    visible: true,
    top: e.clientY,
    left: e.clientX,
    target: session
  }
}

const closeMenu = () => {
  menu.value.visible = false
}

// 重命名
const onRename = async () => {
  const target = menu.value.target
  closeMenu()
  if (!target) return
  try {
    const { value } = await ElMessageBox.prompt('请输入新的会话标题', '重命名', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: target.title,
      inputPattern: /\S+/,
      inputErrorMessage: '标题不能为空'
    })
    await renameSession(target.id, value.trim())
    ElMessage.success('已重命名')
    await fetchSessions()
    emit('changed')
  } catch (e) {
    if (e !== 'cancel' && e?.message) {
      ElMessage.error('重命名失败：' + e.message)
    }
  }
}

// 删除
const onDelete = async () => {
  const target = menu.value.target
  closeMenu()
  if (!target) return
  try {
    await ElMessageBox.confirm(
      `确定删除会话「${target.title || '新对话'}」吗？所有消息将被一并删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    await deleteSession(target.id)
    ElMessage.success('已删除')
    await fetchSessions()
    emit('changed', target.id)
  } catch (e) {
    if (e !== 'cancel' && e?.message) {
      ElMessage.error('删除失败：' + e.message)
    }
  }
}

onMounted(() => {
  fetchSessions()
  document.addEventListener('click', closeMenu)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', closeMenu)
})

defineExpose({ fetchSessions, sessions })
</script>

<style scoped>
.session-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f7f7f8;
  border-right: 1px solid #e8e8e8;
}

.sidebar-header {
  padding: 12px;
  border-bottom: 1px solid #e8e8e8;
}

.new-session-btn {
  width: 100%;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.loading-tip,
.empty-tip {
  text-align: center;
  color: #999;
  padding: 30px 10px;
  font-size: 13px;
}

.session-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background-color 0.2s;
}

.session-item:hover {
  background-color: #ececec;
}

.session-item.active {
  background-color: #e3f2fd;
  color: #1890ff;
}

.session-icon {
  margin-right: 8px;
  flex-shrink: 0;
}

.session-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}

.session-time {
  font-size: 12px;
  color: #999;
  margin-left: 8px;
  flex-shrink: 0;
}

/* 右键菜单 */
.context-menu {
  position: fixed;
  background: white;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  padding: 4px 0;
  margin: 0;
  list-style: none;
  z-index: 9999;
  min-width: 120px;
}

.context-menu li {
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 14px;
}

.context-menu li:hover {
  background-color: #f5f5f5;
}

.context-menu li.danger {
  color: #f56c6c;
}

.context-menu li.danger:hover {
  background-color: #fef0f0;
}
</style>
