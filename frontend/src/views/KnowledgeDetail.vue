<template>
  <div class="kb-detail-page" v-loading="loading">
    <!-- 顶部：返回 + 知识库信息 -->
    <div class="detail-header">
      <el-button :icon="ArrowLeft" text @click="$router.push('/knowledge')">返回列表</el-button>
      <div class="kb-info" v-if="kb">
        <h3>{{ kb.name }}</h3>
        <span class="desc">{{ kb.description || '暂无描述' }}</span>
      </div>
      <el-button :icon="Refresh" circle @click="loadAll" />
    </div>

    <!-- 统计 -->
    <el-row :gutter="16" class="stats-row" v-if="kb">
      <el-col :span="8">
        <el-card shadow="hover">
          <el-statistic title="文档总数" :value="documents.length" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <el-statistic title="分块总数" :value="chunkCount" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <el-statistic title="向量库状态" :value="statusLabel" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 文档管理 -->
    <el-card class="section-card">
      <template #header>
        <div class="section-header">
          <span>文档管理</span>
          <el-button type="primary" :icon="Upload" @click="showUploadDialog = true">
            上传文档
          </el-button>
        </div>
      </template>

      <el-table :data="documents" v-loading="loadingDocs" empty-text="暂无文档，请先上传">
        <el-table-column prop="file_name" label="文件名" min-width="200" />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column prop="content_type" label="类型" width="140" />
        <el-table-column label="上传时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="handleDeleteDoc(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 处理任务 -->
    <el-card class="section-card">
      <template #header>
        <div class="section-header">
          <span>处理任务</span>
          <el-button text size="small" @click="loadTasks">刷新</el-button>
        </div>
      </template>
      <el-table :data="tasks" v-loading="loadingTasks" empty-text="暂无处理任务">
        <el-table-column label="任务 ID" prop="id" width="100" />
        <el-table-column label="文档 ID" width="100">
          <template #default="{ row }">{{ row.document_id || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-tag :type="taskStatusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="200">
          <template #default="{ row }">
            <el-progress
              :percentage="taskProgress(row.status)"
              :status="taskProgressStatus(row.status)"
            />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="错误信息" min-width="200">
          <template #default="{ row }">
            <span v-if="row.error_message" class="error-text">{{ row.error_message }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'failed'"
              size="small"
              type="primary"
              text
              @click="handleRetryTask(row)"
            >
              重试
            </el-button>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 上传记录 -->
    <el-card class="section-card">
      <template #header>
        <div class="section-header">
          <span>上传记录</span>
          <el-button text size="small" @click="loadUploads">刷新</el-button>
        </div>
      </template>
      <el-table :data="uploads" v-loading="loadingUploads" empty-text="暂无上传记录">
        <el-table-column prop="file_name" label="文件名" min-width="200" />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="taskStatusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="错误信息" min-width="200">
          <template #default="{ row }">
            <span v-if="row.error_message" class="error-text">{{ row.error_message }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 上传弹窗（替代 el-upload） -->
    <UploadDialog
      v-model="showUploadDialog"
      :kb-id="kbId"
      @uploaded="onUploaded"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Upload, Refresh } from '@element-plus/icons-vue'
import UploadDialog from '../components/UploadDialog.vue'
import {
  getKnowledgeBase,
  getDocumentsByKb,
  deleteDocument,
  getChunksByKb,
  getTasksByKb,
  getUploadsByKb,
  getTask,
  retryTask,
} from '../api/index.js'

const route = useRoute()
const kbId = computed(() => Number(route.params.kbId))

const kb = ref(null)
const loading = ref(false)
const documents = ref([])
const loadingDocs = ref(false)
const tasks = ref([])
const loadingTasks = ref(false)
const uploads = ref([])
const loadingUploads = ref(false)

// 上传弹窗
const showUploadDialog = ref(false)

// 组件卸载标志：阻止 pollTasksUntilDone 在离开页面后继续打接口/弹消息
const isUnmounted = ref(false)

const chunkCount = computed(() => {
  // 简化：文档列表返回多少条就有多少 chunk（实际应单独查询）
  return documents.value.length
})

const statusLabel = computed(() => {
  if (tasks.value.some(t => t.status === 'processing')) return '处理中'
  if (tasks.value.some(t => t.status === 'failed')) return '有失败'
  if (documents.value.length > 0) return '正常'
  return '空闲'
})

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const formatSize = (bytes) => {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const taskStatusType = (status) => {
  switch (status) {
    case 'completed': return 'success'
    case 'failed': return 'danger'
    case 'processing': return 'warning'
    case 'pending': return 'info'
    default: return 'info'
  }
}

const taskProgress = (status) => {
  switch (status) {
    case 'completed': return 100
    case 'processing': return 50
    case 'pending': return 0
    case 'failed': return 100
    default: return 0
  }
}

const taskProgressStatus = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  if (status === 'processing') return undefined
  return undefined
}

const loadKb = async () => {
  try {
    kb.value = await getKnowledgeBase(kbId.value)
  } catch (e) {
    ElMessage.error('加载知识库失败：' + (e.message || ''))
  }
}

const loadDocuments = async () => {
  loadingDocs.value = true
  try {
    const res = await getDocumentsByKb(kbId.value, { page: 1, limit: 100 })
    documents.value = res.items || []
  } catch (e) {
    ElMessage.error('加载文档失败：' + (e.message || ''))
  } finally {
    loadingDocs.value = false
  }
}

const loadTasks = async () => {
  loadingTasks.value = true
  try {
    const res = await getTasksByKb(kbId.value, { page: 1, limit: 50 })
    tasks.value = res.items || []
  } catch (e) {
    // 静默
  } finally {
    loadingTasks.value = false
  }
}

const loadUploads = async () => {
  loadingUploads.value = true
  try {
    const res = await getUploadsByKb(kbId.value, { page: 1, limit: 50 })
    uploads.value = res.items || []
  } catch (e) {
    // 静默
  } finally {
    loadingUploads.value = false
  }
}

const loadAll = async () => {
  loading.value = true
  await Promise.all([loadKb(), loadDocuments(), loadTasks(), loadUploads()])
  loading.value = false
}

// UploadDialog 上传成功后的回调：results 是 [{file_name, task_id}, ...]
// 设计：fire-and-forget 后台轮询，不阻塞 UI，不重载整个列表
const onUploaded = (results = []) => {
  // 立即关闭弹窗，让用户继续操作
  showUploadDialog.value = false

  const taskIds = (results || [])
    .map((r) => r.task_id)
    .filter((id) => id != null)

  if (taskIds.length === 0) return

  // 追加 pending 占位行到 tasks 表格（局部更新，不重载整个列表）
  taskIds.forEach((tid) => {
    if (!tasks.value.some((t) => t.id === tid)) {
      tasks.value.unshift({
        id: tid,
        document_id: null,
        status: 'pending',
        error_message: null,
        created_at: new Date().toISOString(),
      })
    }
  })

  // 后台异步轮询，不 await —— 用户可立即继续其他操作
  pollTasksUntilDone(taskIds).catch((e) => {
    console.error('[pollTasksUntilDone] uncaught:', e)
  })
}

// 后台轮询任务状态，局部更新单条 task 行，完成后追加新文档
// 不重载整个 tasks/documents 列表，避免表格闪烁和滚动位置重置
const pollTasksUntilDone = async (taskIds, intervalMs = 2000, maxAttempts = 60) => {
  const pendingIds = new Set(taskIds)
  let attempts = 0
  const completedTaskIds = new Set()

  while (pendingIds.size > 0 && attempts < maxAttempts) {
    // 组件已卸载：停止轮询，避免离开页面后继续打接口和弹消息
    if (isUnmounted.value) return
    attempts += 1
    await new Promise((r) => setTimeout(r, intervalMs))
    if (isUnmounted.value) return

    // 并行查询所有 pending task 的状态
    const checks = Array.from(pendingIds).map(async (tid) => {
      try {
        const task = await getTask(tid)
        // 局部更新 tasks 数组中对应行（不重载整个列表）
        const idx = tasks.value.findIndex((t) => t.id === tid)
        if (idx !== -1) {
          // 用 Object.assign 保持响应式，避免整个替换
          Object.assign(tasks.value[idx], task)
        }

        if (task.status === 'completed' || task.status === 'failed') {
          pendingIds.delete(tid)
          if (task.status === 'completed') {
            completedTaskIds.add(tid)
            ElMessage.success(`文档处理完成：任务 #${tid}`)
          } else {
            ElMessage.error(
              `任务 #${tid} 处理失败：${task.error_message || '未知错误'}`
            )
          }
        }
      } catch (e) {
        pendingIds.delete(tid)
        ElMessage.error(`任务 #${tid} 状态查询失败：${e.message || ''}`)
      }
    })

    await Promise.all(checks)
  }

  // 全部轮询结束后：若有完成的任务，只刷新文档列表（追加新文档）
  if (completedTaskIds.size > 0) {
    await loadDocuments()
  }

  if (pendingIds.size > 0) {
    ElMessage.warning(
      `${pendingIds.size} 个任务处理超时（${maxAttempts * intervalMs / 1000}s），请稍后手动刷新查看状态`
    )
  }
}

const handleDeleteDoc = async (doc) => {
  try {
    await ElMessageBox.confirm(
      `确定删除文档 ${doc.file_name} 吗？关联的分块和向量数据也会被删除。`,
      '删除确认',
      { type: 'warning' }
    )
  } catch {
    return // 用户取消
  }

  try {
    await deleteDocument(doc.id)
    ElMessage.success('删除成功')
    await loadDocuments()
  } catch (e) {
    ElMessage.error('删除失败：' + (e.message || ''))
  }
}

// 重试失败任务
const handleRetryTask = async (task) => {
  try {
    await ElMessageBox.confirm(
      `确定重试任务 #${task.id} 吗？将重新执行文档处理流程。`,
      '重试确认',
      { type: 'warning' }
    )
  } catch {
    return
  }

  try {
    const res = await retryTask(task.id)
    ElMessage.success(`已重新提交任务 #${res.task_id}，后台处理中...`)

    // 立即把这一行局部更新为 pending（不重载整个列表）
    const idx = tasks.value.findIndex((t) => t.id === res.task_id)
    if (idx !== -1) {
      Object.assign(tasks.value[idx], {
        status: 'pending',
        error_message: null,
      })
    }

    // 后台异步轮询，完成后自动追加新文档
    pollTasksUntilDone([res.task_id]).catch((e) => {
      console.error('[retry pollTasksUntilDone] uncaught:', e)
    })
  } catch (e) {
    ElMessage.error('重试失败：' + (e.message || ''))
  }
}

onMounted(() => {
  loadAll()
})

onBeforeUnmount(() => {
  isUnmounted.value = true
})
</script>

<style scoped>
.kb-detail-page {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}
.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}
.kb-info { flex: 1; }
.kb-info h3 { margin: 0; font-size: 20px; font-weight: 600; color: var(--text-primary); }
.kb-info .desc { font-size: 13px; color: var(--text-tertiary); margin-top: 4px; display: block; }
.stats-row { margin-bottom: 24px; }
.section-card { margin-bottom: 24px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.error-text { color: #f56c6c; font-size: 12px; }
</style>
