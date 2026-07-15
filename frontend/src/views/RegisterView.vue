<template>
  <div class="auth-page">
    <div class="auth-bg"></div>
    <div class="auth-container">
      <div class="auth-header">
        <div class="auth-logo">
          <el-icon :size="28"><DataAnalysis /></el-icon>
        </div>
        <h2>创建账号</h2>
        <p class="auth-subtitle">注册 RAG 智能问答系统账号</p>
      </div>

      <el-card class="auth-card" shadow="never">
        <template #header>
          <div class="card-title">注册</div>
        </template>
        <el-form :model="form" :rules="rules" label-position="top" ref="formRef">
          <el-form-item prop="email">
            <el-input v-model="form.email" placeholder="邮箱" :prefix-icon="Message" size="large" />
          </el-form-item>
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" size="large" />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="密码" :prefix-icon="Lock" size="large" show-password />
          </el-form-item>
          <el-form-item prop="confirmPwd">
            <el-input v-model="form.confirmPwd" type="password" placeholder="确认密码" :prefix-icon="Lock" size="large" show-password @keydown.enter="handleRegister" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleRegister" :loading="loading" size="large" class="auth-btn">
              注册
            </el-button>
          </el-form-item>
        </el-form>
        <div class="auth-footer">
          已有账号？<router-link to="/login">立即登录</router-link>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Message, User, Lock } from '@element-plus/icons-vue'
import { register } from '../api/index.js'

const router = useRouter()
const loading = ref(false)
const formRef = ref(null)
const form = reactive({ email: '', username: '', password: '', confirmPwd: '' })
const rules = {
  email: [{ required: true, type: 'email', message: '请输入有效邮箱', trigger: 'blur' }],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少 6 位', trigger: 'blur' }],
  confirmPwd: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_, v) => v === form.password ? Promise.resolve() : Promise.reject(new Error('两次密码不一致')),
      trigger: 'blur'
    }
  ],
}

const handleRegister = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await register(form.email, form.username, form.password)
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch (e) {
    ElMessage.error(e.message || '注册失败')
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
  width: 420px;
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
