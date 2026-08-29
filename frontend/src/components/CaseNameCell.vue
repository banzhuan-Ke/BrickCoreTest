<template>
  <span class="case-name-cell">
    <span class="case-name-text">{{ name }}</span>
    <CaseStabilityBadges :quarantine="showQuarantine" :unstable="unstable" />
  </span>
</template>

<script setup>
import { computed } from 'vue'
import CaseStabilityBadges from '@/components/CaseStabilityBadges.vue'
import { isCaseQuarantined } from '@/utils/caseStability.js'

const props = defineProps({
  name: { type: String, default: '' },
  tags: { default: () => [] },
  quarantine: { type: Boolean, default: false },
  unstable: { type: Boolean, default: false },
  stability: { type: Object, default: null },
})

const showQuarantine = computed(() =>
  isCaseQuarantined(
    { tags: props.tags, quarantine: props.quarantine },
    props.stability,
  ),
)
</script>

<style scoped>
.case-name-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  vertical-align: middle;
  line-height: 1.4;
}
.case-name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
</style>
