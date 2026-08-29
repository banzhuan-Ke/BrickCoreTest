<template>
  <el-card class="publish-checklist" shadow="never">
    <div class="pc-header">
      <div>
        <h3 class="pc-title">发布前检查</h3>
        <p class="pc-sub">{{ readyHint }}</p>
      </div>
      <div class="pc-actions">
        <el-button size="small" :loading="loading" @click="emit('refresh')">刷新质量</el-button>
        <el-button
          v-if="canEdit"
          size="small"
          type="success"
          :loading="snapshotLoading"
          @click="emit('snapshot')"
        >生成快照</el-button>
        <el-tag v-if="allPass" type="success" size="small">可收口</el-tag>
        <el-tag v-else type="warning" size="small">待处理</el-tag>
      </div>
    </div>
    <div class="pc-grid">
      <div
        v-for="item in items"
        :key="item.id"
        class="pc-item"
        :class="item.status"
        @click="emit('goto', item.action)"
      >
        <div class="pc-item-top">
          <span class="pc-item-title">{{ item.title }}</span>
          <el-tag :type="checklistStatusTagType(item.status)" size="small" effect="dark">
            {{ checklistStatusLabel(item.status) }}
          </el-tag>
        </div>
        <div class="pc-item-detail">{{ item.detail }}</div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import {
  checklistStatusLabel,
  checklistStatusTagType,
  computePublishChecklist
} from '@/utils/releasePublishChecklist'

const props = defineProps({
  qualityPreview: { type: Object, default: null },
  canEdit: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  snapshotLoading: { type: Boolean, default: false }
})

const emit = defineEmits(['refresh', 'snapshot', 'goto'])

const computedList = computed(() => computePublishChecklist(props.qualityPreview))
const items = computed(() => computedList.value.items)
const allPass = computed(() => computedList.value.allPass)
const readyHint = computed(() => computedList.value.readyHint)
</script>

<style scoped>
.publish-checklist {
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-lighter);
}
.pc-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.pc-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
}
.pc-sub {
  margin: 0;
  color: #909399;
  font-size: 13px;
}
.pc-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.pc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}
.pc-item {
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: #fafafa;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.pc-item:hover {
  border-color: var(--el-color-primary-light-5);
}
.pc-item.pass {
  background: #f6ffed;
  border-color: #e1f3d8;
}
.pc-item.fail {
  background: #fff2f0;
  border-color: #ffccc7;
}
.pc-item.warn {
  background: #fffbe6;
  border-color: #ffe58f;
}
.pc-item-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.pc-item-title {
  font-weight: 500;
  font-size: 13px;
}
.pc-item-detail {
  font-size: 12px;
  color: #606266;
  line-height: 1.4;
}
</style>
