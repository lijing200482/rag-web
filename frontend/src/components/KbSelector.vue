<template>
  <div class="kb-selector" v-if="chatId">
    <span class="label">检索范围：</span>
    <div class="tags-area">
      <!-- 已选知识库 tag -->
      <el-tag
        v-for="kb in selectedKbs"
        :key="kb.id"
        closable
        size="small"
        type="primary"
        effect="light"
        @close="removeKb(kb)"
      >
        {{ kb.name }}
      </el-tag>

      <!-- 添加按钮 + 下拉 -->
      <el-dropdown
        v-if="availableKbs.length > 0"
        trigger="click"
        placement="bottom-start"
        @command="addKb"
      >
        <el-button size="small" text type="primary" :icon="Plus">
          添加知识库
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="kb in availableKbs"
              :key="kb.id"
              :command="kb.id"
            >
              {{ kb.name }}
              <span class="desc-hint" v-if="kb.description">
                — {{ kb.description }}
              </span>
            </el-dropdown-item>
            <el-dropdown-item v-if="availableKbs.length === 0" disabled>
              暂无可选知识库
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- 空状态提示 -->
      <span v-if="selectedKbs.length === 0" class="empty-hint">
        未选择，将检索全部知识库
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  getKnowledgeBases,
  getChatKnowledgeBases,
  addChatKnowledgeBase,
  removeChatKnowledgeBase,
} from '../api/index.js'

const props = defineProps({
  chatId: { type: [Number, String], default: null },
})
const emit = defineEmits(['change'])

const allKbs = ref([])       // 当前用户可访问的全部知识库
const selectedKbs = ref([])  // 当前会话已关联的知识库
const loading = ref(false)

// 可选知识库 = 全部 - 已选
const availableKbs = computed(() => {
  const selectedIds = new Set(selectedKbs.value.map((k) => k.id))
  return allKbs.value.filter((k) => !selectedIds.has(k.id))
})

// 加载用户全部知识库
const loadAllKbs = async () => {
  try {
    allKbs.value = await getKnowledgeBases()
  } catch (e) {
    allKbs.value = []
  }
}

// 加载当前会话已关联的知识库
const loadSelectedKbs = async () => {
  if (!props.chatId) {
    selectedKbs.value = []
    return
  }
  loading.value = true
  try {
    selectedKbs.value = await getChatKnowledgeBases(props.chatId)
  } catch (e) {
    selectedKbs.value = []
  } finally {
    loading.value = false
  }
}

// 添加关联
const addKb = async (kbId) => {
  if (!props.chatId) {
    ElMessage.warning('请先创建或选择一个会话')
    return
  }
  const kb = allKbs.value.find((k) => k.id === kbId)
  if (!kb) return
  try {
    await addChatKnowledgeBase(props.chatId, kbId)
    selectedKbs.value.push(kb)
    emit('change', selectedKbs.value.map((k) => k.id))
  } catch (e) {
    ElMessage.error('添加知识库失败：' + (e.message || ''))
  }
}

// 移除关联
const removeKb = async (kb) => {
  if (!props.chatId) return
  try {
    await removeChatKnowledgeBase(props.chatId, kb.id)
    selectedKbs.value = selectedKbs.value.filter((k) => k.id !== kb.id)
    emit('change', selectedKbs.value.map((k) => k.id))
  } catch (e) {
    ElMessage.error('移除知识库失败：' + (e.message || ''))
  }
}

// 初次挂载：加载全部知识库列表
loadAllKbs()

// chatId 变化时重新加载已关联知识库
watch(
  () => props.chatId,
  async (newId) => {
    if (newId) {
      await loadSelectedKbs()
    } else {
      selectedKbs.value = []
    }
  },
  { immediate: true }
)

// 暴露刷新方法，供外部调用
defineExpose({
  refresh: loadSelectedKbs,
  getSelectedIds: () => selectedKbs.value.map((k) => k.id),
})
</script>

<style scoped>
.kb-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  border-bottom: 1px solid var(--border-color, #e8e8e8);
  background: var(--card-bg, #fafafa);
  font-size: 13px;
  flex-wrap: wrap;
}

.label {
  color: var(--text-tertiary, #8c8c8c);
  flex-shrink: 0;
}

.tags-area {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.empty-hint {
  color: var(--text-tertiary, #bfbfbf);
  font-size: 12px;
  font-style: italic;
}

.desc-hint {
  color: #8c8c8c;
  font-size: 12px;
}
</style>
