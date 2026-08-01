<template>
  <div v-if="text" class="perf-ai-inline" :class="toneClass">
    <span v-if="displayLabel" class="perf-ai-inline__label">{{ displayLabel }}</span>
    <span class="perf-ai-inline__text" v-html="richText" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import {
  colorizePctPhrases,
  humanizeMetricKey,
  noteToneFromText,
} from '@/views/Perf/perfMetricSemantics.js'

const props = defineProps({
  text: { type: String, default: '' },
  label: { type: String, default: '' },
  /** 指标 key，用于百分比好坏着色与中文名回退 */
  metricKey: { type: String, default: '' },
  /** key → 中文 label */
  labelMap: { type: Object, default: () => ({}) },
  lowerIsBetter: { type: Boolean, default: undefined },
  /** info | warn | success | auto */
  tone: { type: String, default: 'auto' },
})

const displayLabel = computed(() => {
  const raw = String(props.label || '').trim()
  if (raw && !/^[a-z][a-z0-9_]*$/i.test(raw)) return raw
  if (props.metricKey) {
    const h = humanizeMetricKey(props.metricKey, props.labelMap)
    if (h && h !== props.metricKey) return h
  }
  if (raw) return humanizeMetricKey(raw, props.labelMap)
  return raw
})

const richText = computed(() =>
  colorizePctPhrases(props.text, {
    metricKey: props.metricKey || props.label,
    lowerIsBetter: props.lowerIsBetter,
  })
)

const toneClass = computed(() => {
  let t = props.tone || 'auto'
  if (t === 'auto') t = noteToneFromText(props.text, props.metricKey || props.label)
  return `tone-${t || 'info'}`
})
</script>

<style scoped>
.perf-ai-inline {
  font-size: 13px;
  color: #334155;
  background: #f8fafc;
  border-left: 3px solid #3b82f6;
  padding: 10px 14px;
  margin: 0 0 12px;
  line-height: 1.55;
  border-radius: 0 6px 6px 0;
}
.perf-ai-inline.tone-warn {
  border-left-color: #dd6b20;
  background: #fffbeb;
}
.perf-ai-inline.tone-success {
  border-left-color: #38a169;
  background: #f0fdf4;
}
.perf-ai-inline__label {
  font-weight: 600;
  color: #1e40af;
  margin-right: 6px;
}
.perf-ai-inline__text {
  color: #475569;
}
.perf-ai-inline__text :deep(.pct-better) {
  color: #15803d !important;
  font-weight: 600;
}
.perf-ai-inline__text :deep(.pct-worse) {
  color: #b91c1c !important;
  font-weight: 600;
}
.perf-ai-inline__text :deep(.pct-flat),
.perf-ai-inline__text :deep(.pct-emphasis) {
  color: #475569 !important;
  font-weight: 600;
}
</style>
