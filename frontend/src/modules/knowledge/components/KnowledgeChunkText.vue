<template>
  <div class="knowledge-chunk-text">
    <template v-if="parsed.kind === 'mixed'">
      <pre v-if="parsed.plainText" class="chunk-plain">{{ parsed.plainText }}</pre>
      <div v-if="parsed.table?.rows?.length" class="chunk-table-wrap chunk-table-after-plain">
        <div v-if="parsed.table.sheetName" class="chunk-sheet-name">{{ parsed.table.sheetName }}</div>
        <el-table
          :data="parsed.table.rows"
          stripe
          border
          size="small"
          class="chunk-table"
          :max-height="tableMaxHeight"
        >
          <el-table-column
            v-for="col in parsed.table.columns"
            :key="col.prop"
            :prop="col.prop"
            :label="col.label"
            :min-width="columnMinWidth(col.label)"
            show-overflow-tooltip
          />
        </el-table>
        <div class="chunk-table-foot">{{ parsed.table.rows.length }} 行</div>
      </div>
    </template>
    <template v-else>
      <div v-if="sheetName" class="chunk-sheet-name">{{ sheetName }}</div>
      <div v-if="parsed.kind === 'table'" class="chunk-table-wrap">
        <el-table
          :data="parsed.rows"
          stripe
          border
          size="small"
          class="chunk-table"
          :max-height="tableMaxHeight"
        >
          <el-table-column
            v-for="col in parsed.columns"
            :key="col.prop"
            :prop="col.prop"
            :label="col.label"
            :min-width="columnMinWidth(col.label)"
            show-overflow-tooltip
          />
        </el-table>
        <div v-if="parsed.rows.length" class="chunk-table-foot">{{ parsed.rows.length }} 行</div>
      </div>
      <pre v-else class="chunk-plain">{{ parsed.text }}</pre>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { parseChunkDisplay } from '@/modules/knowledge/utils/chunkTextFormat.js'

const props = defineProps({
  text: { type: String, default: '' },
  /** 0 / 'none' 表示不限制表格高度（全文抽屉） */
  maxHeight: { type: [Number, String], default: 320 }
})

const parsed = computed(() => parseChunkDisplay(props.text))
const sheetName = computed(() => (parsed.value.kind === 'table' ? parsed.value.sheetName : null))

const tableMaxHeight = computed(() => {
  const h = props.maxHeight
  if (h === 0 || h === 'none' || h == null) return undefined
  return h
})

function columnMinWidth(label) {
  const len = String(label || '').length
  return Math.min(Math.max(len * 14 + 24, 88), 200)
}
</script>

<style scoped>
.knowledge-chunk-text {
  width: 100%;
}
.chunk-sheet-name {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.chunk-table-wrap {
  width: 100%;
  overflow-x: auto;
}
.chunk-table-after-plain {
  margin-top: 12px;
}
.chunk-table {
  width: 100%;
  min-width: 480px;
}
.chunk-table-foot {
  margin-top: 6px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  text-align: right;
}
.chunk-plain {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.65;
  margin: 0;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  max-height: 70vh;
  overflow: auto;
}
</style>
