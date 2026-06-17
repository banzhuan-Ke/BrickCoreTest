<template>
  <el-popover placement="bottom-end" :width="320" trigger="click" popper-class="table-column-picker-popper">
    <template #reference>
      <el-button :icon="Setting" title="列显示">列显示</el-button>
    </template>
    <div class="table-column-picker">
      <div class="picker-head">
        <span class="picker-title">列显示与顺序</span>
        <el-button link type="primary" size="small" @click="handleReset">
          <el-icon><RefreshRight /></el-icon>
          恢复默认
        </el-button>
      </div>
      <draggable
        :model-value="items"
        item-key="key"
        handle=".drag-handle"
        animation="180"
        class="picker-list"
        @update:model-value="onReorder"
      >
        <template #item="{ element }">
          <div class="picker-row">
            <el-icon class="drag-handle" title="拖拽排序"><Rank /></el-icon>
            <el-checkbox
              :model-value="element.visible"
              :disabled="element.required"
              @change="(v) => onToggle(element.key, v)"
            />
            <span class="picker-label" :title="element.label">{{ element.label }}</span>
            <el-tag v-if="element.required" size="small" type="info" class="required-tag">固定</el-tag>
          </div>
        </template>
      </draggable>
    </div>
  </el-popover>
</template>

<script setup>
import { computed } from 'vue'
import draggable from 'vuedraggable'
import { Setting, RefreshRight, Rank } from '@element-plus/icons-vue'

const props = defineProps({
  items: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['toggle', 'reorder', 'reset'])

const items = computed(() => props.items)

function onToggle(key, visible) {
  emit('toggle', key, visible)
}

function onReorder(nextItems) {
  emit('reorder', nextItems.map(i => i.key))
}

function handleReset() {
  emit('reset')
}
</script>

<style scoped>
.table-column-picker {
  max-height: 420px;
  display: flex;
  flex-direction: column;
}
.picker-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.picker-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.picker-list {
  overflow-y: auto;
  max-height: 360px;
}
.picker-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  border-radius: 4px;
}
.picker-row:hover {
  background: var(--el-fill-color-light);
}
.drag-handle {
  cursor: grab;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.drag-handle:active {
  cursor: grabbing;
}
.picker-label {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.required-tag {
  flex-shrink: 0;
}
</style>
