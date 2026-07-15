<template>
  <el-card class="kb-card" shadow="hover" @click="$emit('view')">
    <div class="kb-card-header">
      <el-icon :size="22" color="#1890ff"><Folder /></el-icon>
      <span class="kb-name" :title="kb.name">{{ kb.name }}</span>
    </div>

    <div class="kb-desc" v-if="kb.description">{{ kb.description }}</div>
    <div class="kb-desc empty" v-else>暂无描述</div>

    <div class="kb-stats">
      <div class="stat">
        <el-icon><Document /></el-icon>
        <span>{{ docCount }} 文档</span>
      </div>
      <div class="stat">
        <el-icon><Connection /></el-icon>
        <span>{{ chunkCount }} 块</span>
      </div>
    </div>

    <div class="kb-time">{{ formatDate(kb.created_at) }}</div>

    <div class="kb-actions">
      <el-button size="small" type="primary" plain @click.stop="$emit('view')">查看</el-button>
      <el-button size="small" type="danger" plain @click.stop="$emit('delete')">删除</el-button>
    </div>
  </el-card>
</template>

<script setup>
import { Folder, Document, Connection } from '@element-plus/icons-vue'

const props = defineProps({
  kb: { type: Object, required: true },
  docCount: { type: Number, default: 0 },
  chunkCount: { type: Number, default: 0 },
})

defineEmits(['view', 'delete'])

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.kb-card {
  cursor: pointer;
  transition: transform 0.15s;
}
.kb-card:hover {
  transform: translateY(-2px);
}
.kb-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.kb-name {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.kb-desc {
  font-size: 13px;
  color: #666;
  margin-bottom: 12px;
  min-height: 20px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.kb-desc.empty {
  color: #bbb;
  font-style: italic;
}
.kb-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
  font-size: 13px;
  color: #555;
}
.stat {
  display: flex;
  align-items: center;
  gap: 4px;
}
.kb-time {
  font-size: 12px;
  color: #999;
  margin-bottom: 12px;
}
.kb-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  border-top: 1px solid #f0f0f0;
  padding-top: 10px;
}
</style>
