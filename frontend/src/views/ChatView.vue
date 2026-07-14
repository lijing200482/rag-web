<template>
  <div class="chat-container">
    <!-- 消息列表区域 -->
    <div class="messages-wrapper">
      <div class="messages" ref="messagesContainer">
        <!-- 欢迎消息 -->
        <div v-if="messages.length === 0" class="welcome">
          <el-icon :size="48" color="#1890ff"><ChatDotRound /></el-icon>
          <h2>欢迎使用 RAG 智能问答系统</h2>
          <p>请上传文档后开始提问，或输入您的问题直接咨询</p>
        </div>

        <!-- 消息列表 -->
        <message-bubble
          v-for="msg in messages"
          :key="msg.id"
          :role="msg.role"
          :content="msg.content"
          :sources="msg.sources"
          :alignment="msg.role === 'user' ? 'right' : 'left'"
        />

        <!-- 加载状态 -->
        <loading-indicator v-if="isLoading" />
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
          :disabled="!question.trim()"
        >
          <el-icon><Promotion /></el-icon>
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { askQuestion, healthCheck } from '../api/index.js'
import MessageBubble from '../components/MessageBubble.vue'
import LoadingIndicator from '../components/LoadingIndicator.vue'

const question = ref('')
const isLoading = ref(false)
const messages = ref([])
const messagesContainer = ref(null)
let messageId = 0

// 滚动到底部
const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// 发送消息
const sendMessage = async () => {
  if (!question.value.trim() || isLoading.value) return

  const userMessage = {
    id: ++messageId,
    role: 'user',
    content: question.value.trim(),
    timestamp: Date.now()
  }

  messages.value.push(userMessage)
  const currentQuestion = question.value.trim()
  question.value = ''

  // 显示加载状态
  isLoading.value = true
  await scrollToBottom()

  try {
    // 调用 API
    const response = await askQuestion(currentQuestion)

    // 添加 AI 回复
    const aiMessage = {
      id: ++messageId,
      role: 'assistant',
      content: response.answer,
      sources: response.sources,
      timestamp: Date.now()
    }

    messages.value.push(aiMessage)
    await scrollToBottom()
  } catch (error) {
    console.error('发送失败:', error)
    ElMessage.error('发送失败，请稍后重试')
  } finally {
    isLoading.value = false
  }
}

// 组件挂载时检查后端状态
onMounted(async () => {
  try {
    await healthCheck()
    ElMessage.success('后端服务连接成功')
  } catch (error) {
    console.warn('后端服务未连接:', error)
    ElMessage.warning('后端服务未连接，请确保后端已启动')
  }
})
</script>

<style scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 100px);
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.messages-wrapper {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background-color: #fafafa;
}

.messages {
  max-width: 800px;
  margin: 0 auto;
}

.welcome {
  text-align: center;
  padding: 60px 20px;
  color: #666;
}

.welcome h2 {
  margin: 20px 0 10px;
  color: #333;
}

.input-area {
  padding: 20px;
  border-top: 1px solid #e8e8e8;
  background: white;
}

.input-actions {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
