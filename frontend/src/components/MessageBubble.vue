<template>
  <div class="message-bubble" :class="[role, alignment]">
    <div class="avatar">
      <el-avatar :size="32">
        {{ role === 'user' ? '我' : 'AI' }}
      </el-avatar>
    </div>
    <div class="content">
      <div class="text">{{ content }}</div>

      <!-- 来源引用 -->
      <div v-if="sources && sources.length > 0" class="sources">
        <el-collapse>
          <el-collapse-item title="查看来源引用">
            <div v-for="(source, index) in sources" :key="index" class="source-item">
              <strong>{{ source.source }}</strong>
              <span v-if="source.page"> (第{{ source.page }}页)</span>
              <p>{{ source.content }}</p>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  role: {
    type: String,
    required: true,
    validator: (value) => ['user', 'assistant'].includes(value)
  },
  content: {
    type: String,
    required: true
  },
  sources: {
    type: Array,
    default: null
  },
  alignment: {
    type: String,
    default: 'left'
  }
})
</script>

<style scoped>
.message-bubble {
  display: flex;
  margin-bottom: 20px;
}

.message-bubble.user {
  flex-direction: row-reverse;
}

.avatar {
  flex-shrink: 0;
}

.content {
  max-width: 70%;
  margin: 0 12px;
}

.text {
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.message-bubble.user .text {
  background-color: #1890ff;
  color: white;
  border-top-right-radius: 4px;
}

.message-bubble.assistant .text {
  background-color: white;
  color: #333;
  border: 1px solid #e8e8e8;
  border-top-left-radius: 4px;
}

.sources {
  margin-top: 8px;
}

.source-item {
  margin-bottom: 12px;
  padding: 8px;
  background-color: #f9f9f9;
  border-radius: 4px;
}

.source-item p {
  margin: 4px 0 0 0;
  font-size: 14px;
  color: #666;
}
</style>
