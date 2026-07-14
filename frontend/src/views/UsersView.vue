<template>
  <div>
    <el-card>
      <template #header>
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-size:18px; font-weight:bold;">用户管理</span>
          <el-button @click="loadUsers" :loading="loading">刷新</el-button>
        </div>
      </template>

      <el-table :data="users" v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" width="150" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.is_superuser" type="danger">管理员</el-tag>
            <el-tag v-else type="info">普通用户</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.is_active" type="success">正常</el-tag>
            <el-tag v-else type="danger">已禁用</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-popconfirm
              :title="`确认${row.is_active ? '禁用' : '启用'}用户 ${row.username}?`"
              @confirm="handleToggle(row)"
              v-if="!row.is_superuser"
            >
              <template #reference>
                <el-button
                  :type="row.is_active ? 'danger' : 'success'"
                  size="small"
                  :loading="togglingId === row.id"
                >
                  {{ row.is_active ? '禁用' : '启用' }}
                </el-button>
              </template>
            </el-popconfirm>
            <span v-else style="color:#999; font-size:12px;">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getUsers, toggleUserStatus } from '../api/index.js'

const users = ref([])
const loading = ref(false)
const togglingId = ref(null)

const loadUsers = async () => {
  loading.value = true
  try {
    users.value = await getUsers()
  } catch (e) {
    ElMessage.error(e.message || '获取用户列表失败')
  } finally {
    loading.value = false
  }
}

const handleToggle = async (row) => {
  togglingId.value = row.id
  try {
    const newStatus = !row.is_active
    await toggleUserStatus(row.id, newStatus)
    row.is_active = newStatus
    ElMessage.success(`${newStatus ? '启用' : '禁用'}成功`)
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    togglingId.value = null
  }
}

const formatDate = (str) => {
  if (!str) return '-'
  const d = new Date(str)
  return d.toLocaleString('zh-CN')
}

onMounted(() => {
  loadUsers()
})
</script>
