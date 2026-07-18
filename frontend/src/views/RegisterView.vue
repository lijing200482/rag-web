<template>
  <AuthLayout title="创建账号" subtitle="注册 RAG 智能问答系统账号，开启企业级知识库问答体验。" card-title="创建账号" card-subtitle="填写以下信息完成注册">
    <el-form ref="formRef" :model="form" :rules="rules" class="auth-form" @keydown.enter="handleRegister">
      <el-form-item prop="email">
        <el-input v-model="form.email" placeholder="邮箱" :prefix-icon="Message" size="large" class="auth-input" />
      </el-form-item>

      <el-form-item prop="username">
        <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" size="large" class="auth-input" />
      </el-form-item>

      <el-form-item prop="password">
        <el-input v-model="form.password" type="password" placeholder="密码" :prefix-icon="Lock" size="large" show-password class="auth-input" />
      </el-form-item>

      <el-form-item prop="confirmPwd">
        <el-input v-model="form.confirmPwd" type="password" placeholder="确认密码" :prefix-icon="Lock" size="large" show-password class="auth-input" />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" @click="handleRegister" :loading="loading" size="large" class="auth-btn">
          注册
        </el-button>
      </el-form-item>
    </el-form>

    <template #footer>
      <span class="footer-text">已有账号？</span>
      <router-link to="/login">立即登录</router-link>
    </template>
  </AuthLayout>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Message, User, Lock } from '@element-plus/icons-vue'
import { register } from '../api/index.js'
import AuthLayout from '../components/AuthLayout.vue'

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
      validator: (_, v) => (v === form.password ? Promise.resolve() : Promise.reject(new Error('两次密码不一致'))),
      trigger: 'blur',
    },
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
/* 无额外样式，全部复用 AuthLayout */
</style>
