<template>
  <div class="step-selector">
    <div class="category-filter">
      <el-radio-group v-model="selectedCategory" size="small">
        <el-radio-button label="all">全部</el-radio-button>
        <el-radio-button
          v-for="cat in categories"
          :key="cat.id"
          :label="cat.id"
        >{{ cat.label }}</el-radio-button>
      </el-radio-group>
    </div>

    <div class="keyword-grid">
      <div
        v-for="keyword in filteredKeywords"
        :key="keyword.method"
        class="keyword-card"
        @click="selectKeyword(keyword)"
      >
        <div class="keyword-icon">
          <el-icon :size="24">
            <component :is="keyword.icon" />
          </el-icon>
        </div>
        <div class="keyword-info">
          <div class="keyword-name">{{ keyword.name }}</div>
          <div class="keyword-desc">{{ keyword.desc }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import {
  Document,
  Edit,
  Mouse,
  Clock,
  Search,
  MessageBox,
  MoreFilled,
  Share
} from '@element-plus/icons-vue'
import ActionGroup from '@/datas/ActionGroup.js'

const emit = defineEmits(['select'])

const iconMap = {
  Document,
  Edit,
  Mouse,
  Clock,
  Search,
  MessageBox,
  MoreFilled,
  Share
}

const categoryMap = {
  '页面操作': { id: 'page', label: '页面' },
  '元素操作': { id: 'element', label: '元素' },
  '鼠标键盘': { id: 'mouse', label: '鼠标' },
  '等待操作': { id: 'wait', label: '等待' },
  '断言处理': { id: 'assertion', label: '断言' },
  'iframe操作': { id: 'iframe', label: 'iframe' },
  '其他操作': { id: 'other', label: '其他' },
  '条件分支': { id: 'control', label: '流程' },
}

const categories = ActionGroup
  .map((group) => categoryMap[group.name])
  .filter(Boolean)

const keywords = ActionGroup.flatMap((group) => {
  const category = categoryMap[group.name]?.id || 'other'
  const icon = iconMap[group.groupIcon] || Document
  return group.items.map((item) => ({
    name: item.keyword,
    method: item.method,
    category,
    icon,
    desc: item.keyword,
    params: { ...item.params },
    isContainer: item.method === 'condition_branch',
  }))
})

const selectedCategory = ref('all')

const filteredKeywords = computed(() => {
  if (selectedCategory.value === 'all') {
    return keywords
  }
  return keywords.filter((k) => k.category === selectedCategory.value)
})

function selectKeyword(keyword) {
  emit('select', {
    keyword: keyword.name,
    desc: keyword.desc,
    method: keyword.method,
    params: { ...keyword.params },
    isContainer: keyword.isContainer || false,
  })
}
</script>

<style scoped lang="scss">
.step-selector {
  padding: 16px;
}

.category-filter {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--el-border-color);
}

.keyword-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.keyword-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }
}

.keyword-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: white;
  border-radius: 8px;
  color: var(--el-color-primary);
}

.keyword-info {
  flex: 1;
  min-width: 0;
}

.keyword-name {
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}

.keyword-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
