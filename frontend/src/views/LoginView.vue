<template>
  <div class="auth-page">
    <div class="auth-bg"></div>
    <div class="auth-container">
      <div class="auth-header">
        <div class="auth-logo">
          <el-icon :size="28"><DataAnalysis /></el-icon>
        </div>
        <h2>RAG 智能问答</h2>
        <p class="auth-subtitle">基于检索增强生成的企业级知识库问答系统</p>
      </div>

      <el-card class="auth-card" shadow="never">
        <template #header>
          <div class="card-title">登录</div>
        </template>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <el-form-item prop="credential">
            <el-input
              v-model="form.credential"
              placeholder="邮箱或用户名"
              :prefix-icon="User"
              size="large"
            />
          </el-form-item>
          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="密码"
              :prefix-icon="Lock"
              size="large"
              show-password
              @keydown.enter="handleLogin"
            />
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              @click="handleLogin"
              :loading="loading"
              size="large"
              class="auth-btn"
            >
              登录
            </el-button>
          </el-form-item>
        </el-form>
        <div class="auth-footer">
          还没有账号？<router-link to="/register">立即注册</router-link>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { login } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const formRef = ref(null)
const form = reactive({ credential: '', password: '' })
const rules = {
  credential: [{ required: true, message: '请输入邮箱或用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const handleLogin = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    const res = await login(form.credential, form.password)
    authStore.setAuth(res.access_token, res.user)
    ElMessage.success(`欢迎回来，${res.user.username}`)
    router.push('/')
  } catch (e) {
    ElMessage.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  background: #f0f2f5;
}

.auth-bg {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  opacity: 0.85;
}

.auth-container {
  position: relative;
  z-index: 1;
  width: 400px;
}

.auth-header {
  text-align: center;
  margin-bottom: 32px;
  color: #fff;
}

.auth-logo {
  width: 56px;
  height: 56px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,0.2);
  border-radius: 14px;
  margin-bottom: 16px;
  color: #fff;
}

.auth-header h2 {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 600;
}

.auth-subtitle {
  margin: 0;
  font-size: 14px;
  opacity: 0.8;
}

.auth-card {
  border: none !important;
  border-radius: 12px !important;
  box-shadow: 0 8px 32px rgba(0,0,0,0.12) !important;
}

.card-title {
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.auth-btn {
  width: 100%;
}

.auth-footer {
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
}

.auth-footer a {
  color: var(--color-primary);
  text-decoration: none;
  font-weight: 500;
}
</style>
