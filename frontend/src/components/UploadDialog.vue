<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(v) => $emit('update:modelValue', v)"
    width="640px"
    :show-close="step !== 'uploading'"
    :close-on-click-modal="step !== 'uploading'"
    :close-on-press-escape="step !== 'uploading'"
    align-center
    @closed="onClosed"
    class="upload-dialog"
  >
    <template #header>
      <div class="dialog-header">
        <h3 class="dialog-title">添加文档</h3>
        <p class="dialog-desc">
          上传文档到知识库。支持格式：PDF、DOCX、Markdown 和 Text 文件。
        </p>
      </div>
    </template>

    <!-- 步骤指示器 -->
    <div class="step-indicator">
      <div
        v-for="(s, idx) in steps"
        :key="idx"
        class="step"
        :class="{
          active: currentStepIdx === idx,
          done: currentStepIdx > idx,
        }"
      >
        <div class="step-circle">
          <el-icon v-if="currentStepIdx > idx"><Check /></el-icon>
          <span v-else>{{ idx + 1 }}</span>
        </div>
        <div class="step-icon-name">
          <el-icon v-if="idx === 0"><UploadFilled /></el-icon>
          <el-icon v-else-if="idx === 1"><View /></el-icon>
          <el-icon v-else><Cpu /></el-icon>
        </div>
        <span class="step-label">{{ s }}</span>
      </div>
      <div class="step-connector" v-if="currentStepIdx > 0"></div>
    </div>

    <!-- Step 1: 上传 -->
    <div v-if="step === 'select'" class="step-content">
      <div
        class="dropzone"
        :class="{ 'is-dragover': isDragover }"
        @click="triggerFileInput"
        @dragover.prevent="isDragover = true"
        @dragleave.prevent="isDragover = false"
        @drop.prevent="onDrop"
      >
        <el-icon :size="40" class="dropzone-icon"><UploadFilled /></el-icon>
        <div class="dropzone-title">将文件拖到此处，或点击选择</div>
        <div class="dropzone-hint">支持 PDF、DOCX、TXT、MD 格式</div>
        <input
          ref="fileInputRef"
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.md,.markdown,.txt"
          style="display: none"
          @change="onFileChange"
        />
      </div>

      <!-- 选中的文件列表 -->
      <div v-if="fileList.length > 0" class="file-list">
        <div
          v-for="(f, idx) in fileList"
          :key="idx"
          class="file-item"
        >
          <el-icon class="file-icon"><Document /></el-icon>
          <div class="file-meta">
            <div class="file-name">{{ f.name }}</div>
            <div class="file-size">{{ formatSize(f.size) }}</div>
          </div>
          <el-button
            type="danger"
            text
            :icon="Close"
            @click="removeFile(idx)"
          />
        </div>
      </div>
    </div>

    <!-- Step 2: 预览（上传成功后展示） -->
    <div v-else-if="step === 'preview'" class="step-content">
      <div class="success-banner">
        <el-icon :size="20" color="#67c23a"><CircleCheckFilled /></el-icon>
        <span>已成功上传 {{ uploadedResults.length }} 个文件</span>
      </div>
      <div class="file-list">
        <div
          v-for="(r, idx) in uploadedResults"
          :key="idx"
          class="file-item success"
        >
          <el-icon class="file-icon" color="#67c23a"><Document /></el-icon>
          <div class="file-meta">
            <div class="file-name">{{ r.file_name }}</div>
            <div class="file-size">任务 ID: {{ r.task_id }}</div>
          </div>
          <el-tag type="success" size="small">已上传</el-tag>
        </div>
      </div>
    </div>

    <!-- Step 3: 处理中 -->
    <div v-else-if="step === 'uploading'" class="step-content">
      <div class="processing">
        <el-icon :size="36" class="is-loading"><Loading /></el-icon>
        <div class="processing-title">正在上传并启动处理任务...</div>
        <div class="processing-desc">文件上传完成后，系统会自动解析、分块并生成向量</div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button
          v-if="step === 'select' && fileList.length > 0"
          @click="resetDialog"
        >
          清空
        </el-button>
        <el-button
          v-if="step === 'preview'"
          @click="resetDialog"
        >
          继续上传
        </el-button>
        <el-button
          v-if="step === 'preview'"
          type="primary"
          @click="handleClose"
        >
          完成
        </el-button>
        <el-button
          v-if="step === 'select'"
          type="primary"
          :disabled="fileList.length === 0"
          :loading="false"
          @click="handleUpload"
        >
          上传文件
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  UploadFilled,
  Document,
  Close,
  Check,
  View,
  Cpu,
  CircleCheckFilled,
  Loading,
} from '@element-plus/icons-vue'
import { uploadDocumentToKb } from '../api/index.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  kbId: { type: [Number, String], required: true },
})
const emit = defineEmits(['update:modelValue', 'uploaded'])

const steps = ['上传', '预览', '处理']
const step = ref('select') // 'select' | 'preview' | 'uploading'
const fileInputRef = ref(null)
const isDragover = ref(false)
const fileList = ref([])
const uploadedResults = ref([])

// 当前步骤的索引，用于 step-indicator
const currentStepIdx = computed(() => {
  if (step.value === 'select') return 0
  if (step.value === 'preview') return 1
  return 2
})

// 弹窗关闭时清理状态
const onClosed = () => {
  resetDialog()
}

const resetDialog = () => {
  step.value = 'select'
  fileList.value = []
  uploadedResults.value = []
  isDragover.value = false
}

const handleClose = () => {
  emit('update:modelValue', false)
}

// 触发隐藏的 file input
const triggerFileInput = () => {
  fileInputRef.value?.click()
}

const onFileChange = (e) => {
  const files = Array.from(e.target.files || [])
  addFiles(files)
  // 重置 input 以允许选择同一文件
  e.target.value = ''
}

const onDrop = (e) => {
  isDragover.value = false
  const files = Array.from(e.dataTransfer.files || [])
  addFiles(files)
}

const addFiles = (files) => {
  const allowed = ['.pdf', '.docx', '.doc', '.md', '.markdown', '.txt']
  const valid = files.filter((f) => {
    const ext = '.' + (f.name.split('.').pop() || '').toLowerCase()
    return allowed.includes(ext)
  })
  if (valid.length < files.length) {
    ElMessage.warning('部分文件类型不支持，已过滤')
  }
  if (valid.length === 0) return
  // 去重（同名）
  const existing = new Set(fileList.value.map((f) => f.name + f.size))
  valid.forEach((f) => {
    if (!existing.has(f.name + f.size)) {
      fileList.value.push(f)
    }
  })
}

const removeFile = (idx) => {
  fileList.value.splice(idx, 1)
}

const formatSize = (bytes) => {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const handleUpload = async () => {
  if (fileList.value.length === 0) return
  step.value = 'uploading'

  const results = []
  let failed = 0

  // 逐个上传（保留顺序），便于在 preview 中展示
  for (const file of fileList.value) {
    try {
      const res = await uploadDocumentToKb(props.kbId, file)
      results.push({
        file_name: file.name,
        task_id: res.task_id,
      })
    } catch (e) {
      failed++
      // 继续处理其他文件
    }
  }

  uploadedResults.value = results

  if (results.length > 0) {
    step.value = 'preview'
    emit('uploaded', results)
    if (failed > 0) {
      ElMessage.warning(`已上传 ${results.length} 个文件，${failed} 个失败`)
    } else {
      ElMessage.success(`已成功上传 ${results.length} 个文件`)
    }
  } else {
    ElMessage.error('所有文件上传失败')
    step.value = 'select'
  }
}

// 当弹窗打开时确保状态是 select
watch(
  () => props.modelValue,
  (v) => {
    if (v) resetDialog()
  }
)
</script>

<style scoped>
/* 覆盖 el-dialog 标题样式 */
:deep(.el-dialog__header) {
  padding: 24px 28px 0;
  margin-right: 0;
}
:deep(.el-dialog__body) {
  padding: 16px 28px 0;
}
:deep(.el-dialog__footer) {
  padding: 16px 28px 24px;
}

.dialog-header { padding: 0; }
.dialog-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 700;
  color: #1f1f1f;
}
.dialog-desc {
  margin: 0;
  font-size: 13px;
  color: #8c8c8c;
  line-height: 1.5;
}

/* ===== 步骤指示器 ===== */
.step-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 12px 0 24px;
  position: relative;
}
.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  width: 80px;
  color: #bfbfbf;
  transition: color 0.2s;
}
.step.active { color: #1f1f1f; }
.step.done { color: #52c41a; }
.step-circle {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f0f0f0;
  color: #bfbfbf;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  transition: all 0.2s;
}
.step.active .step-circle {
  background: #1f1f1f;
  color: #fff;
}
.step.done .step-circle {
  background: #52c41a;
  color: #fff;
}
.step-icon-name {
  position: absolute;
  top: 50px;
  font-size: 14px;
  color: inherit;
  opacity: 0.7;
}
.step-label {
  font-size: 12px;
  font-weight: 500;
  position: absolute;
  top: 76px;
}
.step-indicator { position: relative; padding-bottom: 96px; }

.step::before {
  content: '';
  position: absolute;
  top: 16px;
  left: calc(50% + 24px);
  width: 32px;
  height: 2px;
  background: #f0f0f0;
}
.step:last-child::before { display: none; }
.step.active::before { background: #1f1f1f; }
.step.done::before { background: #52c41a; }
.step-connector { display: none; } /* 不需要额外的 connector，依赖 ::before 即可 */

/* ===== 步骤内容 ===== */
.step-content { min-height: 200px; }

/* Dropzone */
.dropzone {
  border: 2px dashed #d9d9d9;
  border-radius: 12px;
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  background: #fafafa;
  transition: all 0.2s;
}
.dropzone:hover, .dropzone.is-dragover {
  border-color: #1890ff;
  background: #e6f7ff;
}
.dropzone-icon {
  color: #8c8c8c;
  margin-bottom: 12px;
}
.dropzone:hover .dropzone-icon,
.dropzone.is-dragover .dropzone-icon {
  color: #1890ff;
}
.dropzone-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f1f1f;
  margin-bottom: 4px;
}
.dropzone-hint {
  font-size: 12px;
  color: #8c8c8c;
}

/* 文件列表 */
.file-list {
  margin-top: 16px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
  max-height: 220px;
  overflow-y: auto;
}
.file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid #f0f0f0;
  background: #fff;
}
.file-item:last-child { border-bottom: none; }
.file-icon { color: #1890ff; font-size: 22px; flex-shrink: 0; }
.file-meta { flex: 1; min-width: 0; }
.file-name {
  font-size: 13px;
  font-weight: 500;
  color: #1f1f1f;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-size {
  font-size: 11px;
  color: #8c8c8c;
  margin-top: 2px;
}
.file-item.success { background: #f6ffed; }

/* 成功 Banner */
.success-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 8px;
  font-size: 13px;
  color: #389e0d;
  margin-bottom: 12px;
}

/* 处理中 */
.processing {
  text-align: center;
  padding: 48px 24px;
}
.processing .is-loading {
  color: #1890ff;
  font-size: 36px;
  animation: rotating 1.5s linear infinite;
  margin-bottom: 16px;
}
.processing-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f1f1f;
  margin-bottom: 6px;
}
.processing-desc {
  font-size: 12px;
  color: #8c8c8c;
}
@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
