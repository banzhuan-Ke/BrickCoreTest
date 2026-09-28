<template>
  <div class="entity-card">
    <el-tag size="small" type="info" effect="plain">{{ card.entity_type }}</el-tag>
    <span class="entity-label">{{ card.label || `${card.entity_type}#${card.entity_id}` }}</span>
    <span class="entity-id">id={{ card.entity_id }}</span>
  </div>
</template>

<script setup>
defineProps({
  card: { type: Object, required: true }
})
</script>

<style scoped lang="scss">
.entity-card {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #606266;
}

.entity-label {
  font-weight: 500;
}

.entity-id {
  color: #909399;
}
</style>
