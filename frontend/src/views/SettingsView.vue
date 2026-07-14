<template>
  <div class="settings-page">
    <h3 style="margin: 0 0 20px;">系统设置</h3>

    <!-- 嵌入模型配置 -->
    <el-card style="margin-bottom: 20px;">
      <template #header><span>嵌入模型配置</span></template>
      <el-form label-width="140px" style="max-width: 600px;">
        <el-form-item label="提供者">
          <el-radio-group v-model="form.embedding_provider">
            <el-radio-button value="local">local</el-radio-button>
            <el-radio-button value="openai">openai</el-radio-button>
            <el-radio-button value="ollama">ollama</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="form.embedding_model" placeholder="nomic-embed-text" />
        </el-form-item>
        <el-form-item label="Ollama 地址" v-if="form.embedding_provider === 'ollama'">
          <el-input v-model="form.ollama_base_url" placeholder="http://localhost:11434" />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- LLM 配置 -->
    <el-card style="margin-bottom: 20px;">
      <template #header><span>LLM 配置</span></template>
      <el-form label-width="140px" style="max-width: 600px;">
        <el-form-item label="提供者">
          <el-select v-model="form.llm_provider" style="width: 100%;">
            <el-option label="OpenAI Compatible" value="openai-compatible" />
            <el-option label="OpenAI" value="openai" />
            <el-option label="Anthropic" value="anthropic" />
            <el-option label="Ollama" value="ollama" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="form.llm_model" placeholder="step-3.7-flash" />
        </el-form-item>
        <el-form-item label="Base URL" v-if="form.llm_provider !== 'ollama'">
          <el-input v-model="form.openai_base_url" placeholder="https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="Ollama 地址" v-if="form.llm_provider === 'ollama'">
          <el-input v-model="form.ollama_base_url" placeholder="http://localhost:11434" />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 检索与分块参数 -->
    <el-card style="margin-bottom: 20px;">
      <template #header><span>检索与分块参数</span></template>
      <el-form label-width="140px" style="max-width: 600px;">
        <el-form-item label="分块大小">
          <el-input-number v-model="form.chunk_size" :min="100" :max="4000" />
        </el-form-item>
        <el-form-item label="分块重叠">
          <el-input-number v-model="form.chunk_overlap" :min="0" :max="500" />
        </el-form-item>
        <el-form-item label="检索 Top-K">
          <el-input-number v-model="form.top_k" :min="1" :max="20" />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 存储配置 -->
    <el-card style="margin-bottom: 20px;">
      <template #header><span>存储配置</span></template>
      <el-form label-width="140px" style="max-width: 600px;">
        <el-form-item label="ChromaDB 持久化目录">
          <el-input v-model="form.chroma_persist_dir" placeholder="../chroma_db" />
        </el-form-item>
        <el-form-item label="集合名称">
          <el-input v-model="form.chroma_collection" placeholder="rag_collection" />
        </el-form-item>
        <el-form-item label="文档上传目录">
          <el-input v-model="form.documents_dir" placeholder="../documents" />
        </el-form-item>
      </el-form>
    </el-card>

    <el-alert
      type="info"
      :closable="false"
      description="以上配置读取自 .env 文件，修改后需重启后端服务生效。"
      style="margin-bottom: 20px;"
    />
  </div>
</template>

<script setup>
import { reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../api/request.js'

const form = reactive({
  embedding_provider: '',
  embedding_model: '',
  ollama_base_url: '',
  llm_provider: '',
  llm_model: '',
  openai_base_url: '',
  chunk_size: 500,
  chunk_overlap: 50,
  top_k: 4,
  chroma_persist_dir: '../chroma_db',
  chroma_collection: 'rag_collection',
  documents_dir: '../documents',
})

const loadSettings = async () => {
  try {
    const res = await request.get('/settings')
    Object.assign(form, res)
  } catch {
    // Backend may not expose /settings yet — show defaults
    console.info('Settings API not available, showing defaults.')
  }
}

onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.settings-page {
  padding: 20px;
}
</style>
