<template>
  <div v-if="groups.length" class="lcg">
    <div v-if="title" class="lcg-title">{{ title }}</div>
    <div v-for="group in groups" :key="group.source" class="lcg-group">
      <div class="lcg-head">
        <span class="lcg-label">{{ group.label }}</span>
        <el-tooltip
          v-if="group.tip"
          :content="group.tip"
          placement="top"
          :show-after="200"
          popper-class="lcg-tip-popper"
        >
          <el-icon class="lcg-help" :size="14"><QuestionFilled /></el-icon>
        </el-tooltip>
        <span class="lcg-count">{{ group.items.length }}</span>
      </div>
      <div class="lcg-tags">
        <el-tag
          v-for="(item, idx) in group.items"
          :key="`${group.source}-${idx}-${candidateLocatorOf(item)}`"
          size="small"
          :type="isActive(item) ? 'primary' : tagType(group.source)"
          :effect="isActive(item) ? 'dark' : 'plain'"
          class="lcg-tag"
          @click="emit('select', item)"
        >{{ formatItemLabel(item) }}</el-tag>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import {
  candidateLocatorOf,
  groupCandidatesBySource,
  normalizeLocatorValue,
} from '@/utils/locatorCandidates.js'
import { isInputShellLocator } from '@/utils/debugLocator.js'

const props = defineProps({
  candidates: { type: Array, default: () => [] },
  /** 当前选中的定位串（可多值，如完整 locator + element_locator） */
  activeLocators: { type: Array, default: () => [] },
  title: { type: String, default: '候选定位器（点击选用）' },
})

const emit = defineEmits(['select'])

const groups = computed(() => groupCandidatesBySource(props.candidates))

const activeSet = computed(() => {
  const set = new Set()
  for (const v of props.activeLocators || []) {
    const n = normalizeLocatorValue(v)
    if (n) set.add(n)
  }
  return set
})

function isActive(item) {
  const loc = candidateLocatorOf(item)
  return loc && activeSet.value.has(loc)
}

function tagType(source) {
  if (source === 'elevated' || source === 'neighbor') return 'success'
  if (source === 'ai') return 'warning'
  return 'info'
}

/** 组内不再重复「当前所选 ·」前缀，只保留语义/可填/外壳提示 */
function formatItemLabel(item) {
  const c = candidateLocatorOf(item)
  if (c.startsWith('get_by_role=textbox') || c.startsWith('get_by_placeholder=')) {
    return `语义 · ${c}`
  }
  if (c.includes('input.el-input__inner') || c.includes('textarea.el-textarea__inner')) {
    return `可填 · ${c}`
  }
  if (isInputShellLocator(c)) {
    return `外壳 · ${c}`
  }
  return c
}
</script>

<style scoped>
.lcg {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.lcg-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.lcg-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
}
.lcg-head {
  display: flex;
  align-items: center;
  gap: 4px;
  line-height: 1;
}
.lcg-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.lcg-help {
  color: var(--el-text-color-secondary);
  cursor: help;
  vertical-align: middle;
}
.lcg-help:hover {
  color: var(--el-color-primary);
}
.lcg-count {
  margin-left: 2px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
.lcg-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: flex-start;
}
.lcg-tag {
  cursor: pointer;
  max-width: 100%;
  height: auto;
  white-space: normal;
  line-height: 1.4;
  padding: 4px 8px;
  text-align: left;
}
.lcg-tag:hover {
  opacity: 0.92;
}
</style>
