<template>
  <div class="message-bubble" :class="[role, alignment]">
    <div class="avatar">
      <el-avatar :size="32">
        {{ role === 'user' ? '我' : 'AI' }}
      </el-avatar>
    </div>

    <div class="content">
      <!-- 消息正文（纯文本，不渲染 markdown） -->
      <div class="text" :class="{ 'is-empty': !content }">
        <pre v-if="role === 'assistant'">{{ content || '正在思考...' }}</pre>
        <span v-else>{{ content }}</span>
      </div>

      <!-- 来源引用面板：点击展开 -->
      <div v-if="role === 'assistant' && sources && sources.length > 0" class="sources">
        <div class="sources-header" @click="sourcesOpen = !sourcesOpen">
          <el-icon class="toggle-icon" :class="{ expanded: sourcesOpen }">
            <ArrowRight />
          </el-icon>
          <span>查看来源引用</span>
          <el-tag size="small" type="info" round>{{ sources.length }} 个</el-tag>
        </div>

        <transition name="slide">
          <div v-show="sourcesOpen" class="sources-panel">
            <div
              v-for="(source, index) in sources"
              :key="index"
              class="source-card"
            >
              <!-- 卡片头部：文件图标 + 文件名 + 页码 -->
              <div class="source-head">
                <el-icon class="file-icon"><Document /></el-icon>
                <div class="source-title-block">
                  <div class="source-name" :title="source.source">
                    {{ source.source }}
                    <el-tag v-if="source.page" size="small" type="warning" round class="page-tag">
                      p.{{ source.page }}
                    </el-tag>
                  </div>
                </div>
                <el-button
                  text
                  size="small"
                  @click.stop="copySource(source, index)"
                  :title="'复制'"
                >
                  <el-icon><CopyDocument v-if="copiedIndex !== index" /><Check v-else /></el-icon>
                </el-button>
              </div>

              <!-- 内容片段 -->
              <div class="source-snippet">
                {{ source.content || '(无内容预览)' }}
              </div>

              <!-- 调试信息（默认折叠） -->
              <div class="source-meta">
                <el-button
                  text
                  size="small"
                  @click.stop="metaOpen[index] = !metaOpen[index]"
                >
                  <el-icon class="meta-icon" :class="{ expanded: metaOpen[index] }">
                    <ArrowRight />
                  </el-icon>
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

const props = defineProps({
  role: {
    type: String,
    required: true,
    validator: (v) => ['user', 'assistant'].includes(v)
  },
  content: { type: String, required: true },
  sources: { type: Array, default: null },
  alignment: { type: String, default: 'left' }
})

const sourcesOpen = ref(false)
const metaOpen = ref({})
const copiedIndex = ref(-1)

function pickMeta(source) {
  // 调试信息：展示 source 中所有字符串/数字字段
  const out = {}
  for (const k of Object.keys(source || {})) {
    const v = source[k]
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
      out[k] = v
    }
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
  margin-bottom: 20px;
}
.message-bubble.user { flex-direction: row-reverse; }

.avatar { flex-shrink: 0; }

.content {
  max-width: 70%;
  margin: 0 12px;
  min-width: 0;
}

.text {
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.6;
  word-break: break-word;
}
.text pre {
  margin: 0;
  padding: 0;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  color: inherit;
  background: transparent;
  white-space: pre-wrap;
  word-break: break-word;
  overflow: visible;
}
.text.is-empty:empty::before {
  content: '正在思考...';
  color: #aaa;
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

/* ===== 来源面板 ===== */
.sources { margin-top: 8px; }

.sources-header {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 13px;
  color: #1890ff;
  background: #f0f7ff;
  border: 1px solid #d6e8ff;
  border-radius: 6px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.sources-header:hover { background: #e6f2ff; }

.toggle-icon {
  transition: transform 0.2s;
  font-size: 12px;
}
.toggle-icon.expanded { transform: rotate(90deg); }

.sources-panel {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.slide-enter-active, .slide-leave-active {
  transition: opacity 0.2s, max-height 0.25s;
  overflow: hidden;
}
.slide-enter-from, .slide-leave-to {
  opacity: 0;
  max-height: 0;
}
.slide-enter-to, .slide-leave-from {
  opacity: 1;
  max-height: 2000px;
}

/* ===== 来源卡片 ===== */
.source-card {
  background: #fff;
  border: 1px solid #e1e4e8;
  border-radius: 8px;
  padding: 10px 12px;
  transition: box-shadow 0.15s;
}
.source-card:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); }

.source-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.file-icon { color: #1890ff; font-size: 18px; flex-shrink: 0; }
.source-title-block { flex: 1; min-width: 0; }
.source-name {
  font-size: 13px;
  font-weight: 500;
  color: #1f1f1f;
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.page-tag { flex-shrink: 0; }

.source-snippet {
  font-size: 12.5px;
  line-height: 1.6;
  color: #444;
  background: #f9fafb;
  padding: 8px 10px;
  border-radius: 4px;
  border-left: 3px solid #1890ff;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
}

/* ===== 调试信息 ===== */
.source-meta { margin-top: 6px; }
.meta-icon {
  font-size: 10px;
  margin-right: 2px;
  transition: transform 0.2s;
}
.meta-icon.expanded { transform: rotate(90deg); }
.meta-content {
  margin-top: 4px;
  padding: 6px 8px;
  background: #f5f5f5;
  border-radius: 4px;
  font-size: 11px;
  font-family: ui-monospace, monospace;
}
.meta-row { display: flex; gap: 6px; line-height: 1.6; }
.meta-key { color: #888; flex-shrink: 0; }
.meta-val { color: #333; word-break: break-all; }
</style>
