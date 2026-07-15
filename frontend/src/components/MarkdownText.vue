<template>
  <div ref="rootEl" class="markdown-body" @click="onClick" v-html="sanitized"></div>

  <!-- 行内引用弹窗：fixed 定位，浮在视口 -->
  <Teleport to="body">
    <div
      v-if="activeSource"
      class="cite-popover"
      :style="{ top: popoverPos.top + 'px', left: popoverPos.left + 'px' }"
      @click.stop
    >
      <div class="cite-pop-arrow"></div>
      <div class="cite-pop-head">
        <el-icon class="cite-file-icon"><Document /></el-icon>
        <span class="cite-filename" :title="activeSource.source">{{ activeSource.source }}</span>
        <el-tag v-if="activeSource.page" size="small" type="warning" round>p.{{ activeSource.page }}</el-tag>
        <button class="cite-close" @click="closePopover">×</button>
      </div>
      <div class="cite-pop-body">{{ activeSource.content || '(无内容预览)' }}</div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { Document } from '@element-plus/icons-vue'

const props = defineProps({
  content: { type: String, required: true },
  sources: { type: Array, default: () => [] }
})

const rootEl = ref(null)
const activeSource = ref(null)
const popoverPos = ref({ top: 0, left: 0 })

// 引用检测正则
const CITE_RE = /\[([^\]\n]+?\.(?:md|pdf|docx|txt|markdown))(?:[，,]\s*p\.(\d+))?\]/gi

// 关键：用 marked 的 inline extension 而不是预处理 + 自定义 renderer
// 这样 marked 解析时把 [xxx.md] 视为合法 token，不破坏 **bold** 等结构
const citationExt = {
  name: 'citation',
  level: 'inline',
  start(src) { return src.indexOf('[') },
  tokenizer(src) {
    const m = /^\[([^\]\n]+?\.(?:md|pdf|docx|txt|markdown))(?:[，,]\s*p\.(\d+))?\]/i.exec(src)
    if (m) {
      return {
        type: 'citation',
        raw: m[0],
        filename: m[1].trim(),
        page: m[2] || null
      }
    }
    return undefined
  },
  renderer(token) {
    const idx = findSourceIndex(token.filename, token.page)
    if (idx === -1) return token.raw  // 不破坏原文
    return `<span class="cite-tag" data-cite-idx="${idx}">${token.filename}${token.page ? `, p.${token.page}` : ''}</span>`
  }
}

// 全局只 use 一次（避免每个组件实例重复注册）
let _markedConfigured = false
function configureMarked() {
  if (_markedConfigured) return
  _markedConfigured = true
  marked.setOptions({ breaks: true, gfm: true })
  marked.use({ extensions: [citationExt] })
}
configureMarked()

const rendered = computed(() => {
  try {
    return marked.parse(props.content || '')
  } catch (e) {
    // 解析失败时降级为转义文本
    return `<p>${escapeHtml(props.content || '')}</p>`
  }
})

// marked v12 已移除内置 sanitize，LLM 输出可能含 <img onerror=...> 等危险标签，
// 这里用 DOMPurify 在注入 DOM 前清洗，保留白名单标签/属性（含 cite-tag span）
const sanitized = computed(() => DOMPurify.sanitize(rendered.value, {
  ADD_ATTR: ['data-cite-idx']
}))

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]))
}

// 在 sources 数组中查找匹配
function findSourceIndex(filename, page) {
  if (!props.sources.length) return -1
  const strip = (s) => (s || '')
    .toLowerCase()
    .replace(/\.(md|pdf|docx|txt|markdown)$/i, '')
    .replace(/[\s\-_·、，,：:]+/g, '')
    .trim()
  const fNorm = strip(filename)
  for (let i = 0; i < props.sources.length; i++) {
    const s = props.sources[i]
    if (!s.source) continue
    if (s.source === filename) return i
    const sNorm = strip(s.source)
    if (sNorm === fNorm) return i
    if (fNorm && (sNorm.includes(fNorm) || fNorm.includes(sNorm))) return i
  }
  return -1
}

// 点击行内引用
function onClick(e) {
  const target = e.target.closest('.cite-tag')
  if (!target) return
  const idx = parseInt(target.getAttribute('data-cite-idx'), 10)
  if (isNaN(idx) || idx < 0 || idx >= props.sources.length) return
  const rect = target.getBoundingClientRect()
  activeSource.value = props.sources[idx]
  const popW = 360
  const top = rect.bottom + window.scrollY + 6
  let left = rect.left + window.scrollX
  if (left + popW > window.innerWidth - 8) {
    left = window.innerWidth - popW - 8
  }
  popoverPos.value = { top, left }
}
function closePopover() { activeSource.value = null }

function onGlobalClick(e) {
  if (!activeSource.value) return
  if (e.target.closest('.cite-popover')) return
  if (e.target.closest('.cite-tag')) return
  closePopover()
}
function onEsc(e) { if (e.key === 'Escape') closePopover() }
onMounted(() => {
  document.addEventListener('click', onGlobalClick)
  document.addEventListener('keydown', onEsc)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onGlobalClick)
  document.removeEventListener('keydown', onEsc)
})
</script>

<style>
/* markdown-body 基础样式 */
.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: #333;
  word-break: break-word;
}
.markdown-body p { margin: 0 0 8px 0; }
.markdown-body p:last-child { margin-bottom: 0; }
.markdown-body strong { font-weight: 600; color: #111; }
.markdown-body em { font-style: italic; }
.markdown-body h1, .markdown-body h2, .markdown-body h3 {
  font-weight: 600;
  margin: 12px 0 8px 0;
  line-height: 1.4;
}
.markdown-body h1 { font-size: 18px; }
.markdown-body h2 { font-size: 16px; }
.markdown-body h3 { font-size: 15px; }
.markdown-body ul, .markdown-body ol { padding-left: 22px; margin: 6px 0; }
.markdown-body li { margin: 2px 0; }
.markdown-body code:not(.hljs) {
  background: #f4f4f5;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #d6336c;
}
.markdown-body pre {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 10px 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
  font-size: 13px;
}
.markdown-body pre code {
  background: transparent;
  padding: 0;
  color: inherit;
  font-size: 13px;
}
.markdown-body blockquote {
  border-left: 3px solid #d0d7de;
  padding-left: 12px;
  color: #57606a;
  margin: 8px 0;
}
.markdown-body a { color: #1890ff; text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body table {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 13px;
}
.markdown-body th, .markdown-body td {
  border: 1px solid #d0d7de;
  padding: 6px 10px;
}
.markdown-body th { background: #f6f8fa; }
.markdown-body hr {
  border: none;
  border-top: 1px solid #e1e4e8;
  margin: 12px 0;
}
.markdown-body br { line-height: 1.7; }

/* 行内引用：胶囊样式 */
.cite-tag {
  display: inline-block;
  padding: 0 6px;
  margin: 0 1px;
  font-size: 12.5px;
  font-weight: 500;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #1890ff;
  background: #e6f2ff;
  border: 1px solid #b3d8ff;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
  vertical-align: baseline;
  user-select: none;
}
.cite-tag:hover {
  background: #1890ff;
  color: white;
  border-color: #1890ff;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(24, 144, 255, 0.2);
}
</style>

<style scoped>
.cite-popover {
  position: absolute;
  z-index: 9999;
  width: 360px;
  max-width: calc(100vw - 16px);
  background: white;
  border: 1px solid #e1e4e8;
  border-radius: 8px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12);
  padding: 0;
  animation: pop-in 0.15s ease-out;
}
.cite-pop-arrow {
  position: absolute;
  top: -6px;
  left: 18px;
  width: 12px;
  height: 12px;
  background: white;
  border-top: 1px solid #e1e4e8;
  border-left: 1px solid #e1e4e8;
  transform: rotate(45deg);
}
.cite-pop-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafbfc;
  border-radius: 8px 8px 0 0;
}
.cite-file-icon { color: #1890ff; font-size: 16px; flex-shrink: 0; }
.cite-filename {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cite-close {
  border: none;
  background: none;
  font-size: 18px;
  line-height: 1;
  color: #999;
  cursor: pointer;
  padding: 0 4px;
}
.cite-close:hover { color: #333; }
.cite-pop-body {
  padding: 10px 12px;
  font-size: 12.5px;
  line-height: 1.6;
  color: #444;
  max-height: 160px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
@keyframes pop-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
