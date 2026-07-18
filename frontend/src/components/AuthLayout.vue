<template>
  <div class="auth-page">
    <!-- 动态背景 -->
    <div class="auth-bg">
      <div class="gradient-overlay"></div>
      <div class="noise-overlay"></div>
      <div class="orb orb-1"></div>
      <div class="orb orb-2"></div>
      <div class="orb orb-3"></div>
      <div class="grid-lines"></div>
    </div>

    <div class="auth-container">
      <!-- 左侧品牌区 -->
      <div class="brand-panel">
        <div class="brand-content">
          <div class="brand-logo">
            <div class="logo-ring">
              <el-icon :size="32"><DataAnalysis /></el-icon>
            </div>
          </div>
          <h1 class="brand-title">{{ title }}</h1>
          <p class="brand-subtitle">{{ subtitle }}</p>

          <div class="feature-list">
            <div class="feature-item">
              <div class="feature-icon feature-icon-blue">
                <el-icon><Document /></el-icon>
              </div>
              <div class="feature-text">
                <div class="feature-title">多格式文档解析</div>
                <div class="feature-desc">支持 PDF、Word、Markdown、TXT 等格式自动切分与向量化</div>
              </div>
            </div>
            <div class="feature-item">
              <div class="feature-icon feature-icon-purple">
                <el-icon><Search /></el-icon>
              </div>
              <div class="feature-text">
                <div class="feature-title">语义检索增强</div>
                <div class="feature-desc">基于向量数据库的精准召回，答案有据可依</div>
              </div>
            </div>
            <div class="feature-item">
              <div class="feature-icon feature-icon-pink">
                <el-icon><ChatDotRound /></el-icon>
              </div>
              <div class="feature-text">
                <div class="feature-title">自然语言交互</div>
                <div class="feature-desc">像聊天一样提问，系统自动理解上下文并给出专业回答</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧卡片区 -->
      <div class="form-panel">
        <div class="glass-card">
          <div class="card-header">
            <div class="card-logo">
              <el-icon :size="22"><DataAnalysis /></el-icon>
            </div>
            <h2 class="card-title">{{ cardTitle }}</h2>
            <p v-if="cardSubtitle" class="card-subtitle">{{ cardSubtitle }}</p>
          </div>

          <slot />

          <div class="card-footer" v-if="$slots.footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { DataAnalysis, Document, Search, ChatDotRound } from '@element-plus/icons-vue'

defineProps({
  title: { type: String, default: 'RAG 智能问答' },
  subtitle: { type: String, default: '基于检索增强生成的企业级知识库问答系统，让文档开口说话。' },
  cardTitle: { type: String, default: '欢迎回来' },
  cardSubtitle: { type: String, default: '' },
})
</script>

<style scoped>
/* ===== 页面基础 ===== */
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ===== 动态背景 ===== */
.auth-bg {
  position: fixed;
  inset: 0;
  background: linear-gradient(135deg, #1a1f3d 0%, #2d1b4e 50%, #1a1f3d 100%);
  z-index: 0;
}

.gradient-overlay {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 20% 30%, rgba(99, 102, 241, 0.35) 0%, transparent 40%),
    radial-gradient(circle at 80% 70%, rgba(168, 85, 247, 0.3) 0%, transparent 40%),
    radial-gradient(circle at 50% 50%, rgba(59, 130, 246, 0.15) 0%, transparent 60%);
}

.noise-overlay {
  position: absolute;
  inset: 0;
  opacity: 0.04;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  opacity: 0.5;
  animation: float 18s ease-in-out infinite;
}

.orb-1 {
  width: 400px;
  height: 400px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  top: -120px;
  right: 10%;
  animation-delay: 0s;
}

.orb-2 {
  width: 300px;
  height: 300px;
  background: linear-gradient(135deg, #ec4899, #f43f5e);
  bottom: -80px;
  left: 5%;
  animation-delay: -6s;
}

.orb-3 {
  width: 240px;
  height: 240px;
  background: linear-gradient(135deg, #3b82f6, #06b6d4);
  top: 40%;
  left: 35%;
  animation-delay: -12s;
  opacity: 0.35;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0) scale(1);
  }
  33% {
    transform: translate(30px, -40px) scale(1.05);
  }
  66% {
    transform: translate(-20px, 25px) scale(0.95);
  }
}

.grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  mask-image: radial-gradient(circle at center, black 0%, transparent 70%);
  -webkit-mask-image: radial-gradient(circle at center, black 0%, transparent 70%);
}

/* ===== 主容器 ===== */
.auth-container {
  position: relative;
  z-index: 1;
  display: flex;
  width: 1100px;
  max-width: 95vw;
  min-height: 640px;
  border-radius: 24px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow:
    0 24px 80px rgba(0, 0, 0, 0.35),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

/* ===== 左侧品牌区 ===== */
.brand-panel {
  flex: 1.2;
  padding: 64px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  color: #fff;
  background:
    linear-gradient(135deg, rgba(99, 102, 241, 0.12), transparent 60%),
    linear-gradient(225deg, rgba(168, 85, 247, 0.08), transparent 50%);
  position: relative;
  overflow: hidden;
}

.brand-panel::before {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 1px;
  background: linear-gradient(180deg, transparent, rgba(255, 255, 255, 0.12), transparent);
}

.brand-content {
  position: relative;
  z-index: 1;
  max-width: 440px;
}

.brand-logo {
  margin-bottom: 32px;
}

.logo-ring {
  width: 72px;
  height: 72px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  box-shadow:
    0 12px 32px rgba(99, 102, 241, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  position: relative;
}

.logo-ring::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 24px;
  border: 2px solid rgba(99, 102, 241, 0.3);
  animation: pulse-ring 2.5s ease-out infinite;
}

@keyframes pulse-ring {
  0% {
    transform: scale(1);
    opacity: 0.6;
  }
  100% {
    transform: scale(1.25);
    opacity: 0;
  }
}

.brand-title {
  font-size: 40px;
  font-weight: 700;
  margin: 0 0 16px;
  letter-spacing: -0.5px;
  background: linear-gradient(135deg, #fff 0%, #c7d2fe 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.brand-subtitle {
  font-size: 16px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.65);
  margin: 0 0 48px;
}

.feature-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.feature-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  transition: all 0.3s ease;
}

.feature-item:hover {
  background: rgba(255, 255, 255, 0.08);
  transform: translateX(4px);
  border-color: rgba(255, 255, 255, 0.12);
}

.feature-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 18px;
}

.feature-icon-blue {
  background: rgba(59, 130, 246, 0.15);
  color: #60a5fa;
}

.feature-icon-purple {
  background: rgba(139, 92, 246, 0.15);
  color: #a78bfa;
}

.feature-icon-pink {
  background: rgba(236, 72, 153, 0.15);
  color: #f472b6;
}

.feature-title {
  font-size: 15px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.92);
  margin-bottom: 4px;
}

.feature-desc {
  font-size: 13px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.55);
}

/* ===== 右侧表单区 ===== */
.form-panel {
  flex: 1;
  padding: 48px 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.25);
}

.glass-card {
  width: 100%;
  max-width: 380px;
  padding: 40px 36px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow:
    0 24px 64px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
}

.card-header {
  text-align: center;
  margin-bottom: 32px;
}

.card-logo {
  width: 56px;
  height: 56px;
  margin: 0 auto 16px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.35);
  color: #fff;
}

.card-title {
  font-size: 26px;
  font-weight: 700;
  color: #fff;
  margin: 0 0 8px;
}

.card-subtitle {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.55);
  margin: 0;
}

.card-footer {
  margin-top: 28px;
  text-align: center;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.55);
}

.card-footer :deep(a) {
  color: #a5b4fc;
  text-decoration: none;
  font-weight: 600;
  transition: color 0.2s;
}

.card-footer :deep(a:hover) {
  color: #fff;
}

/* ===== 共享表单样式（通过 :deep 穿透到 LoginView/RegisterView 插槽） ===== */
:deep(.auth-form .el-form-item) {
  margin-bottom: 20px;
}

:deep(.auth-form .el-form-item__error) {
  padding-top: 4px;
  color: #fca5a5;
}

:deep(.auth-input .el-input__wrapper) {
  background: rgba(255, 255, 255, 0.05) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  border-radius: 12px !important;
  box-shadow: none !important;
  padding: 4px 14px !important;
  transition: all 0.25s ease;
}

:deep(.auth-input .el-input__wrapper:hover) {
  background: rgba(255, 255, 255, 0.08) !important;
  border-color: rgba(255, 255, 255, 0.18) !important;
}

:deep(.auth-input .el-input__wrapper.is-focus) {
  background: rgba(255, 255, 255, 0.1) !important;
  border-color: rgba(99, 102, 241, 0.6) !important;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15) !important;
}

:deep(.auth-input .el-input__inner) {
  color: #fff !important;
  font-size: 15px;
  height: 44px;
}

:deep(.auth-input .el-input__inner::placeholder) {
  color: rgba(255, 255, 255, 0.35) !important;
}

:deep(.auth-input .el-input__icon),
:deep(.auth-input .el-input__password) {
  color: rgba(255, 255, 255, 0.45) !important;
}

/* 去掉浏览器自动填充的蓝色高亮 */
:deep(.auth-input .el-input__inner:-webkit-autofill),
:deep(.auth-input .el-input__inner:-webkit-autofill:hover),
:deep(.auth-input .el-input__inner:-webkit-autofill:focus),
:deep(.auth-input .el-input__inner:-webkit-autofill:active) {
  -webkit-box-shadow: 0 0 0 1000px rgba(255, 255, 255, 0.05) inset !important;
  -webkit-text-fill-color: #fff !important;
  transition: background-color 5000s ease-in-out 0s;
}

:deep(.auth-btn) {
  width: 100%;
  height: 48px;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.5px;
  border: none !important;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4) !important;
  transition: all 0.3s ease !important;
}

:deep(.auth-btn:hover) {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(99, 102, 241, 0.5) !important;
  background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
}

:deep(.auth-btn:active) {
  transform: translateY(0);
}

:deep(.form-options) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: -4px 0 24px;
  font-size: 13px;
}

:deep(.form-options .el-checkbox__label) {
  color: rgba(255, 255, 255, 0.6) !important;
  font-size: 13px;
  font-weight: 400;
}

:deep(.form-options .el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: #6366f1;
  border-color: #6366f1;
}

:deep(.auth-link) {
  color: rgba(255, 255, 255, 0.6);
  text-decoration: none;
  transition: color 0.2s;
  cursor: pointer;
}

:deep(.auth-link:hover) {
  color: #a5b4fc;
}

:deep(.footer-text) {
  margin-right: 4px;
}

/* ===== 响应式 ===== */
@media (max-width: 900px) {
  .brand-panel {
    display: none;
  }

  .form-panel {
    flex: 1;
    padding: 32px 24px;
  }

  .auth-container {
    width: 100%;
    max-width: 440px;
    min-height: auto;
    border-radius: 20px;
  }
}
</style>
