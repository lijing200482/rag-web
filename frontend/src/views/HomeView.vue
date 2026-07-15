<template>
  <div class="home-page">
    <!-- 顶部 Hero 横幅 -->
    <section class="hero-banner">
      <div class="hero-content">
        <h1 class="hero-title">知识助手</h1>
        <p class="hero-desc">
          您的个人 AI 知识中心。上传文档、创建知识库，
          通过自然对话获取即时、准确的回答。
        </p>
      </div>
      <el-button
        type="primary"
        size="large"
        :icon="Plus"
        class="hero-cta"
        @click="onCreateKb"
      >
        新建知识库
      </el-button>
    </section>

    <!-- 统计概览 -->
    <section class="stats-section">
      <div class="stat-card" @click="$router.push('/knowledge')">
        <div class="stat-icon stat-icon-blue">
          <el-icon :size="22"><Document /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ kbCount }}</div>
          <div class="stat-label">知识库数量</div>
        </div>
        <div class="stat-link">
          查看所有知识库
          <el-icon><ArrowRight /></el-icon>
        </div>
      </div>

      <div class="stat-card" @click="$router.push('/chat')">
        <div class="stat-icon stat-icon-purple">
          <el-icon :size="22"><ChatDotRound /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ sessionCount }}</div>
          <div class="stat-label">对话数量</div>
        </div>
        <div class="stat-link">
          查看所有对话
          <el-icon><ArrowRight /></el-icon>
        </div>
      </div>
    </section>

    <!-- 快捷操作 -->
    <section class="quick-actions">
      <h2 class="section-title">快捷操作</h2>
      <div class="action-grid">
        <div class="action-card" @click="onCreateKb">
          <div class="action-icon action-icon-blue">
            <el-icon :size="24"><DataAnalysis /></el-icon>
          </div>
          <div class="action-name">创建知识库</div>
          <div class="action-desc">构建新的 AI 知识库，上传文档并自动索引</div>
        </div>

        <div class="action-card" @click="onUploadDocuments">
          <div class="action-icon action-icon-purple">
            <el-icon :size="24"><UploadFilled /></el-icon>
          </div>
          <div class="action-name">上传文档</div>
          <div class="action-desc">向知识库中添加 PDF、DOCX、MD 或 TXT 文件</div>
        </div>

        <div class="action-card" @click="$router.push('/chat')">
          <div class="action-icon action-icon-pink">
            <el-icon :size="24"><MagicStick /></el-icon>
          </div>
          <div class="action-name">开始对话</div>
          <div class="action-desc">基于知识库内容，通过 AI 获取即时回答</div>
        </div>
      </div>
    </section>

    <!-- 工作原理 -->
    <section class="how-it-works">
      <h2 class="section-title">
        <el-icon><Search /></el-icon>
        工作原理
      </h2>
      <div class="steps-list">
        <div v-for="(step, idx) in howItWorks" :key="idx" class="step-item">
          <div class="step-number">{{ idx + 1 }}</div>
          <div class="step-content">
            <div class="step-title">{{ step.title }}</div>
            <div class="step-desc">{{ step.desc }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 新建知识库弹窗（复用 KnowledgeView 的同款） -->
    <el-dialog v-model="showCreateDialog" title="新建知识库" width="480px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="名称" required>
          <el-input
            v-model="createForm.name"
            placeholder="请输入知识库名称"
            maxlength="50"
            show-word-limit
          />
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
        <el-button type="primary" :loading="creating" @click="handleCreate">
          创建
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Plus,
  Document,
  ChatDotRound,
  ArrowRight,
  DataAnalysis,
  UploadFilled,
  MagicStick,
  Search,
} from '@element-plus/icons-vue'
import {
  getKnowledgeBases,
  listSessions,
  createKnowledgeBase,
} from '../api/index.js'

const router = useRouter()

// 统计数据
const kbCount = ref(0)
const sessionCount = ref(0)

// 新建知识库
const showCreateDialog = ref(false)
const creating = ref(false)
const createForm = ref({ name: '', description: '' })

// 工作原理步骤
const howItWorks = [
  {
    title: '创建知识库',
    desc: '首先创建一个新的知识库。每个知识库都是一个独立的向量空间，专注于特定领域。',
  },
  {
    title: '上传文档',
    desc: '将 PDF、DOCX、Markdown 或纯文本文件放入知识库。系统会自动解析、分块并生成向量嵌入。',
  },
  {
    title: '与知识对话',
    desc: '用自然语言提问，系统会基于检索增强生成（RAG）技术，从您的知识库中检索相关内容并生成带引用来源的准确回答。',
  },
]

// 加载统计
const loadStats = async () => {
  try {
    const [kbs, sessions] = await Promise.all([
      getKnowledgeBases(),
      listSessions().catch(() => []),
    ])
    kbCount.value = Array.isArray(kbs) ? kbs.length : 0
    sessionCount.value = Array.isArray(sessions) ? sessions.length : 0
  } catch (e) {
    // 单个失败不影响其他统计；静默
  }
}

const onCreateKb = () => {
  showCreateDialog.value = true
}

const onUploadDocuments = async () => {
  // 如果有知识库，跳到第一个；否则提示先创建
  try {
    const kbs = await getKnowledgeBases()
    if (kbs && kbs.length > 0) {
      router.push(`/knowledge/${kbs[0].id}`)
    } else {
      ElMessage.warning('请先创建一个知识库')
      showCreateDialog.value = true
    }
  } catch (e) {
    ElMessage.error('加载知识库失败：' + (e.message || ''))
  }
}

const handleCreate = async () => {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  creating.value = true
  try {
    await createKnowledgeBase(
      createForm.value.name.trim(),
      createForm.value.description?.trim() || null
    )
    ElMessage.success('创建成功')
    showCreateDialog.value = false
    createForm.value = { name: '', description: '' }
    await loadStats()
  } catch (e) {
    ElMessage.error('创建失败：' + (e.message || ''))
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  loadStats()
})
</script>

<style scoped>
.home-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 28px 48px;
}

/* ===== Hero Banner ===== */
.hero-banner {
  background: linear-gradient(135deg, #e6f0ff 0%, #f0f5ff 100%);
  border: 1px solid #d6e4ff;
  border-radius: 16px;
  padding: 32px 36px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
}
.hero-content { max-width: 620px; }
.hero-title {
  margin: 0 0 10px;
  font-size: 28px;
  font-weight: 700;
  color: #1890ff;
  letter-spacing: -0.3px;
}
.hero-desc {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: #4a5568;
}
.hero-cta {
  flex-shrink: 0;
  border-radius: 10px;
  padding: 12px 22px;
  font-weight: 600;
  font-size: 14px;
  box-shadow: 0 4px 12px rgba(24, 144, 255, 0.25);
}

/* ===== 统计卡片 ===== */
.stats-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 36px;
}
.stat-card {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 14px;
  padding: 22px 24px;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}
.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.06);
  border-color: #d0dff7;
}
.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  margin-bottom: 14px;
}
.stat-icon-blue { background: linear-gradient(135deg, #5b8def, #4a7ce8); }
.stat-icon-purple { background: linear-gradient(135deg, #8b5cf6, #7c3aed); }
.stat-body { margin-bottom: 12px; }
.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: #1f1f1f;
  line-height: 1.1;
}
.stat-label {
  font-size: 13px;
  color: #8c8c8c;
  margin-top: 4px;
}
.stat-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #1890ff;
  font-weight: 500;
}
.stat-link .el-icon { font-size: 12px; }

/* ===== Section Title ===== */
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
  color: #1f1f1f;
  margin: 0 0 18px;
}
.section-title .el-icon { color: #1890ff; }

/* ===== Quick Actions ===== */
.quick-actions { margin-bottom: 36px; }
.action-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.action-card {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 14px;
  padding: 28px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
}
.action-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
  border-color: #d0dff7;
}
.action-icon {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  margin: 0 auto 16px;
}
.action-icon-blue { background: linear-gradient(135deg, #5b8def, #4a7ce8); }
.action-icon-purple { background: linear-gradient(135deg, #a78bfa, #8b5cf6); }
.action-icon-pink { background: linear-gradient(135deg, #f472b6, #ec4899); }
.action-name {
  font-size: 15px;
  font-weight: 600;
  color: #1f1f1f;
  margin-bottom: 6px;
}
.action-desc {
  font-size: 12px;
  color: #8c8c8c;
  line-height: 1.5;
}

/* ===== How It Works ===== */
.how-it-works {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 14px;
  padding: 24px 28px;
}
.steps-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.step-item {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  padding: 12px 0;
}
.step-item + .step-item {
  border-top: 1px solid #f0f0f0;
}
.step-number {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 50%;
  background: #1890ff;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}
.step-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f1f1f;
  margin-bottom: 4px;
}
.step-desc {
  font-size: 13px;
  color: #595959;
  line-height: 1.6;
}

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .hero-banner { flex-direction: column; align-items: flex-start; }
  .stats-section { grid-template-columns: 1fr; }
  .action-grid { grid-template-columns: 1fr; }
}
</style>
