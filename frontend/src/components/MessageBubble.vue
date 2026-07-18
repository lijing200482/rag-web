<template>
  <div class="message-bubble" :class="[role, alignment]">
    <div class="avatar">
      <el-avatar :size="32">
        {{ role === 'user' ? '我' : 'AI' }}
      </el-avatar>
    </div>

    <div class="content">
      <div class="text" :class="{ 'is-empty': !content }">
        <MarkdownText
          v-if="role === 'assistant'"
          :content="content || '正在思考...'"
          :sources="sources || []"
        />
        <span v-else>{{ content }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import MarkdownText from './MarkdownText.vue'

defineProps({
  role: { type: String, required: true, validator: (v) => ['user', 'assistant'].includes(v) },
  content: { type: String, required: true },
  sources: { type: Array, default: null },
  alignment: { type: String, default: 'left' }
})
</script>

<style scoped>
.message-bubble {
  display: flex;
  margin-bottom: 24px;
  align-items: flex-start;
}
.message-bubble.user { flex-direction: row-reverse; }

.avatar { flex-shrink: 0; margin-top: 4px; }
.avatar .el-avatar { border: 2px solid var(--border-color); }
.message-bubble.user .el-avatar {
  background: var(--color-primary) !important;
  color: #fff !important;
  border-color: var(--color-primary);
}

.content {
  max-width: 70%;
  margin: 0 12px;
  min-width: 0;
}

.text {
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.7;
  word-break: break-word;
  font-size: 14px;
}
.text pre {
  margin: 0; padding: 0; font-family: inherit; font-size: inherit;
  line-height: inherit; color: inherit; background: transparent;
  white-space: pre-wrap; word-break: break-word; overflow: visible;
}
.text.is-empty:empty::before { content: '正在思考...'; color: var(--text-tertiary); }
.message-bubble.user .text {
  background: var(--color-primary); color: #fff;
  border-bottom-right-radius: 4px;
}
.message-bubble.assistant .text {
  background: var(--card-bg); color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-bottom-left-radius: 4px;
  border-left: 3px solid var(--color-primary);
}
</style>
