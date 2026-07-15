<template>
  <div class="knowledge-page">
    <div class="page-header">
      <h3>知识库概览</h3>
      <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">
        新建知识库
      </el-button>
    </div>

    <!-- 统计概览 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="8">
        <el-card shadow="hover">
          <el-statistic title="知识库数量" :value="kbs.length" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <el-statistic title="文档总数" :value="totalDocs" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <el-statistic title="分块总数" :value="totalChunks" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 卡片网格 -->
    <div v-loading="loading" class="kb-grid">
      <KbCard
        v-for="kb in kbs"
        :key="kb.id"
        :kb="kb"
        :doc-count="kb.doc_count || 0"
        :chunk-count="kb.chunk_count || 0"
        @view="goDetail(kb.id)"
        @delete="confirmDelete(kb)"
      />

      <el-empty
        v-if="!loading && kbs.length === 0"
        description="暂无知识库，点击上方按钮创建"
      />
    </div>

    <!-- 新建知识库弹窗 -->
    <el-dialog v-model="showCreateDialog" title="新建知识库" width="480px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" placeholder="请输入知识库名称" maxlength="50" show-word-limit />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="3"
            placeholder="可选：知识库描述"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 删除确认 -->
    <el-dialog v-model="showDeleteDialog" title="删除知识库" width="440px">
      <div v-if="pendingDelete" class="delete-confirm">
        <el-alert type="warning" :closable="false" show-icon>
          确定要删除知识库 <strong>{{ pendingDelete.name }}</strong> 吗？
          <br />该操作会删除该知识库下的所有文档、分块和向量数据，且不可恢复。
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="showDeleteDialog = false">取消</el-button>
        <el-button type="danger" :loading="deleting" @click="handleDelete">确认删除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import KbCard from '../components/KbCard.vue'
import {
  getKnowledgeBases,
  createKnowledgeBase,
  deleteKnowledgeBase,
} from '../api/index.js'

const router = useRouter()

const kbs = ref([])
const loading = ref(false)

// 新建
const showCreateDialog = ref(false)
const creating = ref(false)
const createForm = ref({ name: '', description: '' })

// 删除
const showDeleteDialog = ref(false)
const deleting = ref(false)
const pendingDelete = ref(null)

const totalDocs = computed(() =>
  kbs.value.reduce((s, kb) => s + (kb.doc_count || 0), 0)
)
const totalChunks = computed(() =>
  kbs.value.reduce((s, kb) => s + (kb.chunk_count || 0), 0)
)

const loadKbs = async () => {
  loading.value = true
  try {
    kbs.value = await getKnowledgeBases()
  } catch (e) {
    ElMessage.error('加载知识库失败：' + (e.message || ''))
  } finally {
    loading.value = false
  }
}

const goDetail = (kbId) => {
  router.push(`/knowledge/${kbId}`)
}

const handleCreate = async () => {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  creating.value = true
  try {
    const kb = await createKnowledgeBase(
      createForm.value.name.trim(),
      createForm.value.description?.trim() || null
    )
    ElMessage.success('创建成功')
    showCreateDialog.value = false
    createForm.value = { name: '', description: '' }
    await loadKbs()
  } catch (e) {
    ElMessage.error('创建失败：' + (e.message || ''))
  } finally {
    creating.value = false
  }
}

const confirmDelete = (kb) => {
  pendingDelete.value = kb
  showDeleteDialog.value = true
}

const handleDelete = async () => {
  if (!pendingDelete.value) return
  deleting.value = true
  try {
    await deleteKnowledgeBase(pendingDelete.value.id)
    ElMessage.success('删除成功')
    showDeleteDialog.value = false
    pendingDelete.value = null
    await loadKbs()
  } catch (e) {
    ElMessage.error('删除失败：' + (e.message || ''))
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  loadKbs()
})
</script>

<style scoped>
.knowledge-page {
  padding: 20px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-header h3 {
  margin: 0;
}
.stats-row {
  margin-bottom: 24px;
}
.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  min-height: 200px;
}
.delete-confirm {
  margin: 0;
}
</style>
