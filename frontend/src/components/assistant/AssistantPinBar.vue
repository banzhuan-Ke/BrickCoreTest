<template>
  <div v-if="items.length || pinCandidate" class="assistant-pin-bar">
    <div class="pin-row">
      <span class="pin-label">钉住</span>
      <el-tag
        v-for="it in items"
        :key="`${it.type}-${it.id}`"
        size="small"
        closable
        type="warning"
        effect="plain"
        class="pin-tag"
        @close="$emit('unpin', it)"
      >
        {{ it.label || `${it.type}#${it.id}` }}
      </el-tag>
      <el-button
        v-if="pinCandidate && !alreadyPinned"
        size="small"
        text
        type="primary"
        :disabled="disabled"
        @click="$emit('pin-page', pinCandidate)"
      >
        钉住当前页
      </el-button>
      <span v-if="!items.length && !pinCandidate" class="pin-empty">暂无钉住实体</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  pinCandidate: { type: Object, default: null },
  disabled: { type: Boolean, default: false }
})

defineEmits(['unpin', 'pin-page'])

const alreadyPinned = computed(() => {
  const c = props.pinCandidate
  if (!c) return false
  return (props.items || []).some(
    (it) => it.type === c.type && String(it.id) === String(c.id)
  )
})
</script>

<style scoped lang="scss">
.assistant-pin-bar {
  margin-bottom: 8px;
  flex-shrink: 0;
}

.pin-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.pin-label {
  color: #909399;
  flex-shrink: 0;
}

.pin-tag {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pin-empty {
  color: #c0c4cc;
}
</style>
