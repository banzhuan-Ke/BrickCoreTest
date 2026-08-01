<template>
  <section v-if="rows.length" class="perf-metric-glossary">
    <h3 class="glossary-title">{{ heading }}</h3>
    <p class="glossary-intro">
      下列释义适用于本报告中的同名指标；若某节未出现对应字段可忽略。
    </p>
    <el-table :data="rows" border size="small" class="glossary-table">
      <el-table-column prop="name" label="指标" width="200" />
      <el-table-column prop="meaning" label="含义" min-width="360" />
    </el-table>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { METRIC_GLOSSARY_ROWS } from '@/views/Perf/perfMetricSemantics.js'

defineProps({
  heading: { type: String, default: '附录：指标说明' },
})

const rows = computed(() => METRIC_GLOSSARY_ROWS)
</script>

<style scoped>
.perf-metric-glossary {
  margin-top: 8px;
}
.glossary-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  padding-bottom: 8px;
  border-bottom: 2px solid #e2e8f0;
}
.glossary-intro {
  margin: 0 0 10px;
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
}
.glossary-table {
  width: 100%;
}
</style>
