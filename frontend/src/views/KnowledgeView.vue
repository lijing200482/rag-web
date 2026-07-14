<template>
  <div class="knowledge-page">
    <h3 style="margin: 0 0 20px;">知识库概览</h3>

    <el-row :gutter="16" style="margin-bottom: 20px;">
      <el-col :span="8">
        <el-card shadow="hover">
          <el-statistic title="文档总数" :value="stats.documentCount" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <el-statistic title="总分块数" :value="stats.chunkCount" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <el-statistic title="向量库状态" :value="statusLabel" />
        </el-card>
      </el-col>
    </el-row>

    <el-card>
      <template #header>
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span>文档明细</span>
          <el-button size="small" :icon="Refresh" circle @click="loadStats" />
        </div>
      </template>
      <el-table :data="documents" v-loading="loading">
        <el-table-column prop="source" label="文件名" min-width="200" />
        <el-table-column prop="document_type" label="类型" width="120" />
        <el-table-column prop="chunk_count" label="分块数" width="100" align="right" />
        <el-table-column label="上传时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.uploaded_at) }}
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && documents.length === 0" description="知识库为空，请先上传文档" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { getDocuments } from '../api/index.js'

const documents = ref([])
const loading = ref(false)

const stats = computed(() => {
  const docCount = documents.value.length
  const chunkCount = documents.value.reduce((sum, d) => sum + (d.chunk_count || 0), 0)
  return { documentCount: docCount, chunkCount }
})

const statusLabel = computed(() => {
  const total = stats.value.chunkCount
  if (total === 0) return '空闲'
  if (total < 100) return '较小'
  if (total < 10000) return '正常'
  return '较大'
})

const loadStats = async () => {
  loading.value = true
  try {
    const res = await getDocuments()
    documents.value = res
  } catch {
    // silently fail — stats will show 0
  } finally {
    loading.value = false
  }
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  loadStats()
})
</script>

<style scoped>
.knowledge-page {
  padding: 20px;
}
</style>
