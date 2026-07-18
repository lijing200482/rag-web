<template>
  <AuthLayout title="RAG 智能问答" subtitle="基于检索增强生成的企业级知识库问答系统，让文档开口说话。" card-title="欢迎回来" card-subtitle="请登录您的账户">
    <el-form ref="formRef" :model="form" :rules="rules" class="auth-form" @keydown.enter="handleLogin">
      <el-form-item prop="credential">
        <el-input v-model="form.credential" placeholder="邮箱或用户名" :prefix-icon="User" size="large" class="auth-input" />
      </el-form-item>

      <el-form-item prop="password">
        <el-input v-model="form.password" type="password" placeholder="密码" :prefix-icon="Lock" size="large" show-password class="auth-input" />
      </el-form-item>

      <div class="form-options">
        <el-checkbox v-model="rememberMe" class="remember-checkbox">记住我</el-checkbox>
        <a class="auth-link" @click.prevent>忘记密码？</a>
      </div>

      <el-form-item>
        <el-button type="primary" @click="handleLogin" :loading="loading" size="large" class="auth-btn">
          登录
        </el-button>
      </el-form-item>
    </el-form>

    <template #footer>
      <span class="footer-text">还没有账号？</span>
      <router-link to="/register">立即注册</router-link>
    </template>
  </AuthLayout>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { login } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import AuthLayout from '../components/AuthLayout.vue'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const rememberMe = ref(false)
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
.remember-checkbox :deep(.el-checkbox__label) {
  color: rgba(255, 255, 255, 0.6) !important;
  font-size: 13px;
  font-weight: 400;
}

.remember-checkbox :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: #6366f1;
  border-color: #6366f1;
}
</style>
