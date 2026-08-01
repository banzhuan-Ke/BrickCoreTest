<template>
  <div v-if="refs.length" class="knowledge-ref-cards">
    <div class="cards-head">
      <span class="cards-title">{{ title }}</span>
      <span v-if="strategyLabel" class="cards-strategy">{{ strategyLabel }}</span>
    </div>
    <div class="cards-grid">
      <div v-for="item in refs" :key="item.id" class="ref-card">
        <div class="ref-title">{{ item.title }}</div>
        <div class="ref-meta">
          <el-tag size="small" type="info">{{ docTypeLabel(item.doc_type) }}</el-tag>
          <span v-if="item.folder_name" class="ref-folder">{{ item.folder_name }}</span>
          <span class="ref-chars">{{ formatChars(item.char_count) }} 字</span>
        </div>
      </div>
    </div>
    <div v-if="bugHintText" class="bug-hint">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ bugHintText }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'

const props = defineProps({
  refs: { type: Array, default: () => [] },
  bugHints: { type: Object, default: null },
  strategyLabel: { type: String, default: '' },
  title: { type: String, default: '引用资料溯源' }
})

const bugHintText = computed(() => {
  const h = props.bugHints
  if (!h?.has_hints) return ''
  return h.hint_text || ''
})

function formatChars(n) {
  const v = Number(n) || 0
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`
  return v.toLocaleString()
}

function docTypeLabel(t) {
  const map = {
    requirement: '需求',
    iteration_plan: '迭代计划',
    test_plan: '测试计划',
    bug_export: 'Bug导出',
    task_export: '任务导出',
    summary: '总结',
    other: '其他'
  }
  return map[t] || t || '文档'
}
</script>

<style scoped>
.knowledge-ref-cards {
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}
.cards-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.cards-title {
  font-size: 13px;
  font-weight: 600;
}
.cards-strategy {
  font-size: 12px;
  color: var(--el-color-primary);
}
.cards-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.ref-card {
  flex: 1 1 180px;
  max-width: 280px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
}
.ref-title {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  margin-bottom: 4px;
}
.ref-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.ref-folder {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bug-hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning-dark-2);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
}
</style>
