<template>
  <div class="chat-layout">
    <!-- 会话侧边栏 -->
    <div class="sidebar-wrapper">
      <SessionSidebar
        ref="sidebarRef"
        :active-id="currentSessionId"
        @new="onNewSession"
        @select="onSelectSession"
        @changed="onSessionChanged"
      />
    </div>

    <!-- 主聊天区 -->
    <div class="chat-container">
      <!-- 顶部标题栏 -->
      <div class="chat-header">
        <h3>{{ currentSessionTitle || '新对话' }}</h3>
      </div>

      <!-- 知识库选择器：仅在选中会话时显示 -->
      <KbSelector :chat-id="currentSessionId" @change="onKbChange" />

      <!-- 消息列表区域 -->
      <div class="messages-wrapper" ref="messagesContainer" @scroll="onMessagesScroll">
        <div v-if="hasMoreMessages" class="load-more-bar">
          <el-button v-if="!loadingMore" text size="small" @click="loadMessages">
            加载更多
          </el-button>
          <span v-else class="loading-text">加载中...</span>
        </div>
        <div class="messages">
          <!-- 欢迎消息：未选中任何会话时的引导 -->
          <div v-if="messages.length === 0" class="welcome">
            <el-icon :size="48" color="#1890ff"><ChatDotRound /></el-icon>
            <h2>欢迎使用 RAG 智能问答系统</h2>
            <p v-if="hasSessions">请从左侧选择一个会话继续对话</p>
            <p v-else>点击左上方"新建会话"开始，或在下方输入框提问</p>
          </div>

          <!-- 消息列表 -->
          <message-bubble
            v-for="msg in messages"
            :key="msg.id"
            :role="msg.role"
            :content="msg.content"
            :sources="msg.sources"
            :class="{ streaming: msg.role === 'assistant' && msg === messages[messages.length - 1] && isStreaming }"
            :alignment="msg.role === 'user' ? 'right' : 'left'"
          />

          <!-- 加载状态：只在等待首个 token 时显示 -->
          <loading-indicator v-if="isLoading && !isStreaming" />
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="input-area">
        <el-input
          v-model="question"
          type="textarea"
          :rows="3"
          placeholder="请输入您的问题..."
          :disabled="isLoading"
          @keydown.enter.prevent="sendMessage"
        />
        <div class="input-actions">
          <el-button
            type="primary"
            @click="sendMessage"
            :loading="isLoading"
            :disabled="!question.trim() || isStreaming"
          >
            <el-icon><Promotion /></el-icon>
            发送
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Promotion } from '@element-plus/icons-vue'
import { askQuestionStream, createSession, getSessionMessages, healthCheck } from '../api/index.js'
import MessageBubble from '../components/MessageBubble.vue'
import LoadingIndicator from '../components/LoadingIndicator.vue'
import SessionSidebar from '../components/SessionSidebar.vue'
import KbSelector from '../components/KbSelector.vue'

const question = ref('')
const isLoading = ref(false)
const isStreaming = ref(false)
const messages = ref([])
const messagesContainer = ref(null)   // 滚动容器 wrapper
const sidebarRef = ref(null)

// 当前 SSE 流的取消函数（组件卸载时调用，避免卸载后仍在更新 messages 状态）
const currentStreamCancel = ref(null)
// 滚动节流标志：rAF 合并多个 token 触发的滚动请求，最多 60fps
const scrollPending = ref(false)

const currentSessionId = ref(null)
const currentSessionTitle = ref('')

// 游标分页相关
const hasMoreMessages = ref(false)
const nextCursor = ref(null)
const loadingMore = ref(false)

// 是否有历史会话（用于空状态文案切换）
const hasSessions = computed(() => {
  return (sidebarRef.value?.sessions?.length || 0) > 0
})

// 滚动到底部
const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// 新建会话
const onNewSession = async () => {
  try {
    const session = await createSession('')
    currentSessionId.value = session.id
    currentSessionTitle.value = session.title || '新对话'
    messages.value = []
    if (sidebarRef.value) {
      await sidebarRef.value.fetchSessions()
    }
    ElMessage.success('已创建新会话')
  } catch (e) {
    ElMessage.error('创建会话失败：' + e.message)
  }
}

// 选中已有会话（游标分页：首次只拉最新 limit 条）
const onSelectSession = async (session) => {
  if (currentSessionId.value === session.id) return
  currentSessionId.value = session.id
  currentSessionTitle.value = session.title || '新对话'

  messages.value = []
  hasMoreMessages.value = true
  nextCursor.value = null
  loadingMore.value = false

  try {
    await loadMessages()  // 首次加载最新页
    await scrollToBottom()
  } catch (e) {
    ElMessage.error('加载会话消息失败：' + e.message)
  }
}

// 加载下一页消息
const loadMessages = async () => {
  if (!hasMoreMessages.value || loadingMore.value) return
  loadingMore.value = true

  try {
    const page = await getSessionMessages(
      currentSessionId.value,
      nextCursor.value,
      20
    )
    // 旧消息插入到头部
    messages.value = [
      ...(page.messages || []).map(m => ({
        id: m.id,
        role: m.role,
        content: m.content,
        sources: m.sources,
        timestamp: new Date(m.created_at).getTime()
      })),
      ...messages.value
    ]
    hasMoreMessages.value = page.has_more
    nextCursor.value = page.next_cursor
  } catch (e) {
    if (e.status !== 404) {
      ElMessage.error('加载历史消息失败：' + e.message)
    }
    hasMoreMessages.value = false
  } finally {
    loadingMore.value = false
  }
}

// 滚动到顶部时自动加载更多
const onMessagesScroll = () => {
  if (!messagesContainer.value || !hasMoreMessages.value || loadingMore.value) return
  const el = messagesContainer.value
  if (el.scrollTop <= 50) {
    const prevHeight = el.scrollHeight
    loadMessages().then(() => {
      nextTick(() => {
        el.scrollTop = el.scrollHeight - prevHeight
      })
    })
  }
}

// 会话变更（重命名/删除后由 sidebar 触发）
const onSessionChanged = (deletedId) => {
  // 若删除的是当前会话，清空主区
  if (deletedId && deletedId === currentSessionId.value) {
    currentSessionId.value = null
    currentSessionTitle.value = ''
    messages.value = []
  }
}

// 知识库选择变化：后端 /query/stream 会根据 session_id 自动查询关联 KB
// 这里仅做日志记录，不需要额外传参
const onKbChange = (kbIds) => {
  console.debug('[ChatView] KB selection changed:', kbIds)
}

// 发送消息（SSE 流式）
const sendMessage = async () => {
  if (!question.value.trim() || isLoading.value) return

  // 没有会话时自动创建一个
  if (!currentSessionId.value) {
    try {
      const session = await createSession('')
      currentSessionId.value = session.id
      currentSessionTitle.value = session.title || '新对话'
      if (sidebarRef.value) {
        await sidebarRef.value.fetchSessions()
      }
    } catch (e) {
      ElMessage.error('创建会话失败：' + e.message)
      return
    }
  }

  const userContent = question.value.trim()
  const userMsg = {
    id: Date.now(),
    role: 'user',
    content: userContent,
    timestamp: Date.now()
  }

  messages.value.push(userMsg)
  question.value = ''

  // 创建 AI 占位气泡，token 到达时逐步填充
  const aiMsgId = Date.now() + 1
  messages.value.push({
    id: aiMsgId,
    role: 'assistant',
    content: '',
    sources: null,
    timestamp: Date.now()
  })
  const aiMsgIdx = messages.value.length - 1  // 通过索引访问 Proxy 确保响应式

  isLoading.value = true
  isStreaming.value = false
  await scrollToBottom()

  const { cancel } = askQuestionStream(userContent, null, currentSessionId.value, {
    onToken({ content }) {
      if (!isStreaming.value) {
        isStreaming.value = true
      }
      messages.value[aiMsgIdx].content += content
      // 用 requestAnimationFrame 节流滚动：长答案数千 token 不再逐次强制滚动，最多 60fps
      if (!scrollPending.value) {
        scrollPending.value = true
        requestAnimationFrame(() => {
          scrollToBottom()
          scrollPending.value = false
        })
      }
    },
    onSources(arr) {
      messages.value[aiMsgIdx].sources = arr
    },
    async onDone({ session_id: _sessionId }) {
      isLoading.value = false
      isStreaming.value = false
      currentStreamCancel.value = null

      // 刷新侧边栏（第一条消息后端自动填充 title）
      if (sidebarRef.value) {
        await sidebarRef.value.fetchSessions()
        const matched = sidebarRef.value.sessions?.find(s => s.id === currentSessionId.value)
        if (matched) {
          currentSessionTitle.value = matched.title || '新对话'
        }
      }
    },
    onError(err) {
      isLoading.value = false
      isStreaming.value = false
      currentStreamCancel.value = null

      const aiIdx = messages.value.findIndex(m => m.id === aiMsgId)
      if (aiIdx !== -1) {
        if (messages.value[aiIdx].content) {
          messages.value[aiIdx].content += '\n\n[生成中断：' + (err.message || '未知错误') + ']'
        } else {
          messages.value.splice(aiIdx, 1)
          const uIdx = messages.value.findIndex(m => m.id === userMsg.id)
          if (uIdx !== -1) messages.value.splice(uIdx, 1)
        }
      }
      ElMessage.error('发送失败：' + (err.message || '请稍后重试'))
    }
  })
  currentStreamCancel.value = cancel
}

// 组件挂载时只检查后端状态；不自动加载任何会话历史，
// 避免破坏 Redis 两层架构的「按需加载」原则：
//   - 进入聊天页 → 仅从后端 GET /chat/sessions 拉取会话列表（轻量）
//   - 用户点击某个会话 → 触发 GET /chat/sessions/{id}，后端按需从 MySQL 加载到 Redis
onMounted(async () => {
  try {
    await healthCheck()
  } catch (e) {
    ElMessage.warning('后端服务未连接，请确保后端已启动')
  }
})

onBeforeUnmount(() => {
  // 组件卸载时中断进行中的 SSE 流，避免卸载后仍在更新 messages 状态
  currentStreamCancel.value?.()
})
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: calc(100vh - 0px);
  background: var(--card-bg);
  border-radius: 0;
  overflow: hidden;
}

.sidebar-wrapper {
  width: 260px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-color);
}

.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px;
  border-bottom: 1px solid var(--border-color);
  background: var(--card-bg);
}

.chat-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.messages-wrapper {
  flex: 1;
  overflow-y: auto;
  padding: 0;
  background: var(--page-bg);
}

.load-more-bar {
  text-align: center;
  padding: 10px;
}

.load-more-bar .loading-text {
  color: var(--text-tertiary);
  font-size: 13px;
}

.messages {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
}

.welcome {
  text-align: center;
  padding: 80px 20px;
  color: var(--text-tertiary);
}

.welcome .el-icon {
  font-size: 48px;
  color: #d9d9d9;
}

.welcome h2 {
  margin: 20px 0 10px;
  font-size: 18px;
  font-weight: 500;
  color: var(--text-secondary);
}

.welcome p {
  font-size: 13px;
}

.input-area {
  padding: 16px 20px;
  border-top: 1px solid var(--border-color);
  background: var(--card-bg);
}

.input-actions {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

/* 流式打字光标效果 */
.message-bubble.streaming .text::after {
  content: '|';
  animation: blink 1s step-end infinite;
  color: var(--color-primary);
  font-weight: 400;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
