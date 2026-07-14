<template>
  <div class="doc-page">
    <h3 style="margin: 0 0 20px;">文档管理</h3>

    <!-- 上传区域 -->
    <el-card style="margin-bottom: 20px;">
      <template #header>
        <span>上传文档</span>
      </template>
      <el-upload
        drag
        :auto-upload="false"
        :on-change="handleFileChange"
        v-model:file-list="fileList"
        accept=".pdf,.txt,.md,.markdown,.docx"
        multiple
      >
        <el-icon :size="48" color="#1890ff"><Upload /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或 <em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 PDF / TXT / MD / DOCX 格式，可一次选择多个文件</div>
        </template>
      </el-upload>
      <div style="margin-top: 12px; text-align: right;">
        <el-button
          type="primary"
          :loading="uploading"
          :disabled="fileList.length === 0"
          @click="handleUpload"
        >
          开始上传（逐个串行，避免并发冲突）
        </el-button>
      </div>
    </el-card>

    <!-- 文档列表 -->
    <el-card>
      <template #header>
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span>已入库文档</span>
          <el-button size="small" :icon="Refresh" circle @click="loadDocuments" />
        </div>
      </template>
      <el-table :data="documents" style="width:100%" v-loading="loading">
        <el-table-column prop="source" label="文件名" min-width="200" />
        <el-table-column prop="document_type" label="类型" width="120" />
        <el-table-column prop="chunk_count" label="分块数" width="100" align="right" />
        <el-table-column label="上传时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.uploaded_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-popconfirm
              title="确定删除此文档？"
              @confirm="handleDelete(row.source)"
            >
              <template #reference>
                <el-button type="danger" size="small" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && documents.length === 0" description="暂无文档，请先上传" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, Refresh } from '@element-plus/icons-vue'
import { uploadDocument, getDocuments, deleteDocument } from '../api/index.js'

const fileList = ref([])
const uploading = ref(false)
const documents = ref([])
const loading = ref(false)

const handleFileChange = (file, fileList) => {
  const validExtensions = ['.pdf', '.txt', '.md', '.markdown', '.docx']
  const ext = file.name.toLowerCase().substring(file.name.lastIndexOf('.'))
  if (!validExtensions.includes(ext)) {
    ElMessage.warning(`不支持的文件格式: ${file.name}`)
    return false
  }
}

const handleUpload = async () => {
  if (fileList.value.length === 0) return
  uploading.value = true
  let success = 0
  let failed = 0
  try {
    for (const fileItem of fileList.value) {
      try {
        await uploadDocument(fileItem.raw)
        success++
      } catch (e) {
        failed++
        ElMessage.error(`上传失败: ${fileItem.name} — ${e.message}`)
      }
    }
    if (failed === 0) {
      ElMessage.success(`上传成功 ${success} 个文件`)
    } else {
      ElMessage.warning(`上传完成：成功 ${success}，失败 ${failed}`)
    }
    fileList.value = []
    await loadDocuments()
  } catch {
    ElMessage.error('上传失败')
  } finally {
    uploading.value = false
  }
}

const loadDocuments = async () => {
  loading.value = true
  try {
    const res = await getDocuments()
    documents.value = res
  } catch {
    ElMessage.error('获取文档列表失败')
  } finally {
    loading.value = false
  }
}

const handleDelete = async (source) => {
  try {
    await deleteDocument(source)
    ElMessage.success('删除成功')
    await loadDocuments()
  } catch {
    ElMessage.error('删除失败')
  }
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  loadDocuments()
})
</script>

<style scoped>
.doc-page {
  padding: 20px;
}
.el-upload__tip {
  color: #999;
  font-size: 12px;
  margin-top: 8px;
}
</style>
