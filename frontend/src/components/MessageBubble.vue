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

      <div v-if="role === 'assistant' && sources && sources.length > 0" class="sources">
        <div class="sources-header" @click="sourcesOpen = !sourcesOpen">
          <el-icon class="toggle-icon" :class="{ expanded: sourcesOpen }"><ArrowRight /></el-icon>
          <span>查看来源引用</span>
          <el-tag size="small" type="info" round>{{ sources.length }} 个</el-tag>
        </div>

        <transition name="slide">
          <div v-show="sourcesOpen" class="sources-panel">
            <div v-for="(source, index) in sources" :key="index" class="source-card">
              <div class="source-head">
                <el-icon class="file-icon"><Document /></el-icon>
                <div class="source-title-block">
                  <div class="source-name" :title="source.source">
                    {{ source.source }}
                    <el-tag v-if="source.page" size="small" type="warning" round class="page-tag">p.{{ source.page }}</el-tag>
                  </div>
                </div>
                <el-button text size="small" @click.stop="copySource(source, index)" :title="'复制'">
                  <el-icon><CopyDocument v-if="copiedIndex !== index" /><Check v-else /></el-icon>
                </el-button>
              </div>
              <div class="source-snippet">{{ source.content || '(无内容预览)' }}</div>
              <div class="source-meta">
                <el-button text size="small" @click.stop="metaOpen[index] = !metaOpen[index]">
                  <el-icon class="meta-icon" :class="{ expanded: metaOpen[index] }"><ArrowRight /></el-icon>
                  调试信息
                </el-button>
                <div v-show="metaOpen[index]" class="meta-content">
                  <div v-for="(val, key) in pickMeta(source)" :key="key" class="meta-row">
                    <span class="meta-key">{{ key }}:</span>
                    <span class="meta-val">{{ val }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ArrowRight, Document, CopyDocument, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import MarkdownText from './MarkdownText.vue'

const props = defineProps({
  role: { type: String, required: true, validator: (v) => ['user', 'assistant'].includes(v) },
  content: { type: String, required: true },
  sources: { type: Array, default: null },
  alignment: { type: String, default: 'left' }
})

const sourcesOpen = ref(false)
const metaOpen = ref({})
const copiedIndex = ref(-1)

function pickMeta(source) {
  const out = {}
  for (const k of Object.keys(source || {})) {
    const v = source[k]
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') out[k] = v
  }
  return out
}

async function copySource(source, index) {
  try {
    const text = `${source.source}${source.page ? ' (p.' + source.page + ')' : ''}\n\n${source.content || ''}`
    await navigator.clipboard.writeText(text)
    copiedIndex.value = index
    ElMessage.success('已复制')
    setTimeout(() => { copiedIndex.value = -1 }, 1500)
  } catch (e) {
    ElMessage.error('复制失败：' + e.message)
  }
}
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

.sources { margin-top: 8px; }
.sources-header {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 10px; font-size: 13px;
  color: var(--color-primary); background: var(--color-primary-bg);
  border: 1px solid #b3d8ff; border-radius: 6px;
  cursor: pointer; user-select: none;
}
.sources-header:hover { background: #d9edff; }
.toggle-icon { transition: transform 0.2s; font-size: 12px; }
.toggle-icon.expanded { transform: rotate(90deg); }
.sources-panel { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }
.slide-enter-active, .slide-leave-active { transition: opacity 0.2s, max-height 0.25s; overflow: hidden; }
.slide-enter-from, .slide-leave-to { opacity: 0; max-height: 0; }
.slide-enter-to, .slide-leave-from { opacity: 1; max-height: 2000px; }

.source-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 12px; }
.source-card:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); }
.source-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.file-icon { color: var(--color-primary); font-size: 18px; flex-shrink: 0; }
.source-title-block { flex: 1; min-width: 0; }
.source-name { font-size: 13px; font-weight: 500; color: var(--text-primary); display: flex; align-items: center; gap: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.page-tag { flex-shrink: 0; }
.source-snippet {
  font-size: 12.5px; line-height: 1.6; color: var(--text-secondary);
  background: var(--page-bg); padding: 8px 10px; border-radius: 4px;
  border-left: 3px solid var(--color-primary); white-space: pre-wrap; word-break: break-word;
  max-height: 120px; overflow-y: auto;
}
.source-meta { margin-top: 6px; }
.meta-icon { font-size: 10px; margin-right: 2px; transition: transform 0.2s; }
.meta-icon.expanded { transform: rotate(90deg); }
.meta-content { margin-top: 4px; padding: 6px 8px; background: var(--page-bg); border-radius: 4px; font-size: 11px; font-family: ui-monospace, monospace; }
.meta-row { display: flex; gap: 6px; line-height: 1.6; }
.meta-key { color: var(--text-tertiary); flex-shrink: 0; }
.meta-val { color: var(--text-primary); word-break: break-all; }
</style>
