<template>
  <el-aside :width="width" class="keyword-sidebar">
    <div class="sidebar-header">
      <h3>{{ title }}</h3>
      <p v-if="hint" class="sidebar-hint">{{ hint }}</p>
      <el-input
        v-model="query"
        clearable
        size="small"
        class="keyword-search"
        placeholder="搜索关键字 / method"
        :prefix-icon="Search"
      />
    </div>
    <div class="keyword-list">
      <el-collapse v-model="activeGroups" class="keyword-collapse">
        <el-collapse-item
          v-for="group in filteredGroups"
          :key="group.groupId"
          :name="group.groupId"
          class="keyword-group"
        >
          <template #title>
            <div class="group-title">
              <el-icon><component :is="group.icon" /></el-icon>
              <span>{{ group.name }}</span>
              <el-tag
                v-if="query.trim()"
                size="small"
                type="info"
                effect="plain"
                class="match-count"
              >
                {{ group.items.length }}
              </el-tag>
            </div>
          </template>

          <VueDraggable
            :modelValue="group.items"
            :group="{ name: 'steps', pull: 'clone', put: false }"
            :sort="false"
            :clone="cloneKeyword"
            :animation="200"
            target=".keyword-items"
            class="draggable-source"
          >
            <div class="keyword-items">
              <div
                v-for="(item, itemIndex) in group.items"
                :key="`${group.groupId}_${item.method}_${itemIndex}`"
                class="keyword-item"
                :data-step="serializeKeywordForDrag(item)"
                :title="item.method ? `${item.name} (${item.method})` : item.name"
                @dblclick="onDblclick(item)"
              >
                <el-icon><component :is="item.icon" /></el-icon>
                <span>{{ item.name }}</span>
                <el-icon class="drag-icon"><Rank /></el-icon>
              </div>
            </div>
          </VueDraggable>
        </el-collapse-item>
      </el-collapse>
      <div v-if="filteredGroups.length === 0" class="keyword-empty">
        无匹配关键字
      </div>
    </div>
  </el-aside>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Rank, Search } from '@element-plus/icons-vue'
import { VueDraggable } from 'vue-draggable-plus'
import { cloneKeywordForDrag, serializeKeywordForDrag } from '@/utils/stepHelper'

const props = defineProps({
  title: { type: String, default: '操作选项' },
  hint: { type: String, default: '' },
  groups: { type: Array, required: true },
  /** 展开的分组 id 列表 */
  modelValue: { type: Array, default: () => [] },
  width: { type: String, default: '280px' },
  /** 是否启用双击添加（App 用例等） */
  enableDblclick: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'add'])

const query = ref('')
const activeGroups = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const cloneKeyword = cloneKeywordForDrag

const filteredGroups = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return props.groups
  return props.groups
    .map((group) => ({
      ...group,
      items: (group.items || []).filter((item) => {
        const name = String(item.name || item.keyword || '').toLowerCase()
        const method = String(item.method || '').toLowerCase()
        const groupName = String(group.name || '').toLowerCase()
        return name.includes(q) || method.includes(q) || groupName.includes(q)
      }),
    }))
    .filter((group) => group.items.length > 0)
})

watch(
  () => [query.value, filteredGroups.value],
  () => {
    if (!query.value.trim()) return
    // 搜索时自动展开所有命中分组，避免结果被折叠藏住
    activeGroups.value = filteredGroups.value.map((g) => g.groupId)
  },
  { deep: true },
)

function onDblclick(item) {
  if (!props.enableDblclick) return
  emit('add', item)
}
</script>

<style scoped lang="scss">
@use '@/styles/case-step-editor-layout.scss';

.sidebar-hint {
  margin: 6px 0 0;
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}

.keyword-search {
  margin-top: 10px;
}

.match-count {
  margin-left: 6px;
}

.keyword-empty {
  padding: 24px 16px;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
