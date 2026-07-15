<template>
  <div class="api-keys-page">
    <div class="page-header">
      <h3>API 密钥管理</h3>
      <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">
        创建密钥
      </el-button>
    </div>

    <el-card>
      <el-table :data="apiKeys" v-loading="loading" empty-text="暂无密钥，点击上方按钮创建第一个">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="key_prefix" label="密钥" min-width="160">
          <template #default="{ row }">
            <code class="key-text">{{ row.key_prefix }}</code>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后使用" width="180">
          <template #default="{ row }">{{ formatDate(row.last_used_at) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建密钥弹窗 -->
    <el-dialog v-model="showCreateDialog" title="创建 API 密钥" width="520px" @closed="onCreateDialogClosed">
      <!-- 步骤 1: 输入名称 -->
      <div v-if="!createdKey">
        <el-form label-width="80px">
          <el-form-item label="名称" required>
            <el-input v-model="createForm.name" placeholder="请输入密钥名称（如：开发环境）" maxlength="50" show-word-limit />
          </el-form-item>
        </el-form>
      </div>

      <!-- 步骤 2: 显示密钥 -->
      <div v-else class="created-key-box">
        <el-alert type="warning" :closable="false" show-icon>
          <strong>密钥创建后仅显示一次，请立即保存！</strong>
          <br />关闭后将无法再次查看完整密钥。
        </el-alert>
        <div class="key-display">
          <el-input :model-value="createdKey" readonly>
            <template #append>
              <el-button :icon="CopyDocument" @click="copyKey">复制</el-button>
            </template>
          </el-input>
        </div>
      </div>

      <template #footer>
        <el-button @click="showCreateDialog = false">关闭</el-button>
        <el-button
          v-if="!createdKey"
          type="primary"
          :loading="creating"
          @click="handleCreate"
        >
          创建
        </el-button>
        <el-button
          v-else
          type="primary"
          @click="copyKey"
        >
          复制密钥
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, CopyDocument } from '@element-plus/icons-vue'
import { getApiKeys, createApiKey, deleteApiKey } from '../api/index.js'

const apiKeys = ref([])
const loading = ref(false)

const showCreateDialog = ref(false)
const creating = ref(false)
const createForm = ref({ name: '' })
const createdKey = ref('') // 创建后完整密钥（仅显示一次）

const formatDate = (dateStr) => {
  if (!dateStr) return '从未使用'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const loadKeys = async () => {
  loading.value = true
  try {
    apiKeys.value = await getApiKeys()
  } catch (e) {
    ElMessage.error('加载密钥失败：' + (e.message || ''))
  } finally {
    loading.value = false
  }
}

const handleCreate = async () => {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请输入密钥名称')
    return
  }
  creating.value = true
  try {
    const res = await createApiKey(createForm.value.name.trim())
    createdKey.value = res.key
    ElMessage.success('密钥创建成功')
    await loadKeys()
  } catch (e) {
    ElMessage.error('创建失败：' + (e.message || ''))
  } finally {
    creating.value = false
  }
}

const copyKey = async () => {
  try {
    await navigator.clipboard.writeText(createdKey.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    // 降级方案
    const input = document.createElement('textarea')
    input.value = createdKey.value
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
    ElMessage.success('已复制到剪贴板')
  }
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定删除密钥 ${row.name} 吗？删除后使用该密钥的应用将无法访问 API。`,
      '删除确认',
      { type: 'warning' }
    )
  } catch {
    return
  }

  try {
    await deleteApiKey(row.id)
    ElMessage.success('删除成功')
    await loadKeys()
  } catch (e) {
    ElMessage.error('删除失败：' + (e.message || ''))
  }
}

const onCreateDialogClosed = () => {
  createdKey.value = ''
  createForm.value = { name: '' }
}

onMounted(() => {
  loadKeys()
})
</script>

<style scoped>
.api-keys-page { padding: 24px; max-width: 1000px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h3 { margin: 0; font-size: 20px; font-weight: 600; color: var(--text-primary); }
.key-text { font-family: 'Courier New', monospace; background: var(--page-bg); padding: 2px 6px; border-radius: 4px; font-size: 13px; color: var(--color-primary); }
.created-key-box { margin-top: 10px; }
.key-display { margin-top: 12px; }
</style>
