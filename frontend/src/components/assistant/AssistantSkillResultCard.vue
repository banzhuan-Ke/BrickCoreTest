<template>
  <div class="skill-result-card">
    <div class="skill-title">
      Skill 结果 · {{ label }}
      <el-tag size="small" :type="statusType">{{ card.status || 'success' }}</el-tag>
    </div>
    <div v-if="card.summary" class="skill-summary">{{ card.summary }}</div>
    <div v-if="card.run_record_id" class="skill-meta">run_record_id={{ card.run_record_id }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  card: { type: Object, required: true },
  skillLabels: { type: Object, default: () => ({}) }
})

const label = computed(
  () => props.skillLabels[props.card.skill_code] || props.card.skill_code || 'Skill'
)
const statusType = computed(() => {
  const s = String(props.card.status || 'success').toLowerCase()
  if (s === 'failed' || s === 'error') return 'danger'
  if (s === 'cancelled') return 'info'
  return 'success'
})
</script>

<style scoped lang="scss">
.skill-result-card {
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px solid #e9e9eb;
  border-radius: 8px;
  background: #fafafa;
  font-size: 12px;
}

.skill-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 4px;
}

.skill-summary {
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
}

.skill-meta {
  margin-top: 4px;
  color: #909399;
}
</style>
