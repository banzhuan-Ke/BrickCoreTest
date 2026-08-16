<template>
  <div v-if="result" class="db-assert-result">
    <div class="result-summary" :class="result.all_passed ? 'is-pass' : 'is-fail'">
      <div class="summary-left">
        <el-icon class="summary-icon">
          <SuccessFilled v-if="result.all_passed" />
          <CircleCloseFilled v-else />
        </el-icon>
        <div class="summary-text">
          <div class="summary-title">{{ result.all_passed ? '全部通过' : '存在失败' }}</div>
          <div class="summary-sub">
            通过 {{ passCount }} / {{ totalCount }}
            <span v-if="failCount" class="fail-count">· 失败 {{ failCount }}</span>
          </div>
        </div>
      </div>
      <div class="summary-hint">
        <template v-if="hasEnvMismatch">
          失败原因多为<strong>数据源与调试环境不一致</strong>：请切换顶部环境，或改选当前环境下的数据源
        </template>
        <template v-else>
          字段等于/不等比较仅取查询<strong>首行</strong>；下方最多展示近 10 条结果便于核对
        </template>
      </div>
    </div>

    <div
      v-for="(item, idx) in results"
      :key="idx"
      class="result-item"
      :class="item.passed ? 'item-pass' : 'item-fail'"
    >
      <div class="item-head">
        <el-tag :type="item.passed ? 'success' : 'danger'" size="small" effect="dark">
          {{ item.passed ? '通过' : '失败' }}
        </el-tag>
        <span class="item-name">{{ item.target || `断言 ${idx + 1}` }}</span>
        <el-tag v-if="item.operator" size="small" type="info" effect="plain">
          {{ operatorLabel(item.operator) }}
        </el-tag>
        <el-tag v-if="item.field" size="small" effect="plain">字段 {{ item.field }}</el-tag>
        <el-tag v-if="isEnvMismatch(item)" size="small" type="warning" effect="plain">环境不一致</el-tag>
        <span class="item-rowcount">
          {{ item.error ? '未执行查询' : `${item.row_count ?? 0} 行` }}
        </span>
      </div>

      <div v-if="item.error" class="error-box" :class="{ 'is-env': isEnvMismatch(item) }">
        <div class="error-title">{{ isEnvMismatch(item) ? '环境/数据源不匹配' : '执行失败' }}</div>
        <p class="item-error">{{ item.error }}</p>
      </div>
      <p v-else-if="item.message" class="item-message">{{ item.message }}</p>

      <div class="compare-row" v-if="!item.error">
        <div class="compare-cell">
          <span class="compare-label">实际</span>
          <code class="compare-value">{{ formatValue(item.actual) }}</code>
        </div>
        <div class="compare-cell">
          <span class="compare-label">期望</span>
          <code class="compare-value">{{ formatValue(item.expected) }}</code>
        </div>
      </div>

      <div v-if="item.sql" class="sql-block">
        <span class="sql-label">SQL</span>
        <pre class="sql-text">{{ item.sql }}</pre>
      </div>

      <div v-if="previewRows(item).length" class="preview-block">
        <div class="preview-title">
          查询结果预览
          <span class="preview-meta">
            展示 {{ previewRows(item).length }}
            <template v-if="item.preview_truncated || (item.row_count || 0) > previewRows(item).length">
              / {{ item.row_count }} 行
            </template>
          </span>
        </div>
        <el-table
          :data="previewRows(item)"
          size="small"
          border
          stripe
          max-height="280"
          class="preview-table"
        >
          <el-table-column
            v-for="col in previewColumns(item)"
            :key="col"
            :prop="col"
            :label="col"
            min-width="110"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <span :class="{ 'hl-field': isHighlightField(item, col) }">
                {{ formatCell(row[col]) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-empty
        v-else-if="!item.error && (item.row_count === 0 || !item.rows_preview)"
        description="无查询行可预览"
        :image-size="48"
        class="preview-empty"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { SuccessFilled, CircleCloseFilled } from '@element-plus/icons-vue'

const props = defineProps({
  result: { type: Object, default: null },
})

const OPERATOR_LABELS = {
  equals: '等于',
  not_equals: '不等于',
  gt: '大于',
  gte: '大于等于',
  lt: '小于',
  lte: '小于等于',
  contains: '包含',
  row_count_equals: '行数等于',
  exists: '存在记录',
  not_exists: '不存在',
}

const results = computed(() => props.result?.results || [])
const totalCount = computed(() => results.value.length)
const passCount = computed(() => results.value.filter((r) => r.passed).length)
const failCount = computed(() => totalCount.value - passCount.value)

function isEnvMismatch(item) {
  const text = `${item?.error || ''} ${item?.message || ''}`
  return /环境不一致|未绑定当前环境|绑定在/.test(text)
}

const hasEnvMismatch = computed(() => results.value.some((r) => !r.passed && isEnvMismatch(r)))

function operatorLabel(op) {
  return OPERATOR_LABELS[op] || op
}

function formatValue(val) {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'object') {
    try {
      return JSON.stringify(val)
    } catch {
      return String(val)
    }
  }
  return String(val)
}

function formatCell(val) {
  if (val === null || val === undefined) return ''
  if (typeof val === 'object') {
    try {
      return JSON.stringify(val)
    } catch {
      return String(val)
    }
  }
  return String(val)
}

function previewRows(item) {
  const rows = item?.rows_preview
  return Array.isArray(rows) ? rows : []
}

function previewColumns(item) {
  const rows = previewRows(item)
  if (!rows.length) return []
  const keys = new Set()
  rows.forEach((row) => {
    if (row && typeof row === 'object') {
      Object.keys(row).forEach((k) => keys.add(k))
    }
  })
  const list = [...keys]
  const field = (item?.field || '').trim()
  if (field && list.includes(field)) {
    return [field, ...list.filter((k) => k !== field)]
  }
  return list
}

function isHighlightField(item, col) {
  const field = (item?.field || '').trim()
  return field && field === col
}
</script>

<style scoped lang="scss">
.db-assert-result {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.result-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid transparent;

  &.is-pass {
    background: var(--el-color-success-light-9);
    border-color: var(--el-color-success-light-5);
    .summary-icon { color: var(--el-color-success); }
  }

  &.is-fail {
    background: var(--el-color-danger-light-9);
    border-color: var(--el-color-danger-light-5);
    .summary-icon { color: var(--el-color-danger); }
  }
}

.summary-left {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.summary-icon {
  font-size: 22px;
  margin-top: 1px;
}

.summary-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.3;
}

.summary-sub {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.fail-count {
  color: var(--el-color-danger);
}

.summary-hint {
  flex: 1;
  max-width: 420px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
  text-align: right;
}

.result-item {
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);

  &.item-pass {
    border-left: 3px solid var(--el-color-success);
  }

  &.item-fail {
    border-left: 3px solid var(--el-color-danger);
  }
}

.item-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.item-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.item-rowcount {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.item-message {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--el-text-color-regular);
}

.error-box {
  margin: 0 0 10px;
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--el-color-danger-light-9);
  border: 1px solid var(--el-color-danger-light-5);

  &.is-env {
    background: var(--el-color-warning-light-9);
    border-color: var(--el-color-warning-light-5);

    .error-title { color: var(--el-color-warning-dark-2); }
    .item-error { color: var(--el-text-color-regular); }
  }
}

.error-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-danger);
  margin-bottom: 4px;
}

.item-error {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--el-color-danger);
  white-space: pre-wrap;
  word-break: break-word;
}

.compare-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 10px;
}

.compare-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  min-width: 0;
}

.compare-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.compare-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  color: var(--el-text-color-primary);
  word-break: break-all;
  white-space: pre-wrap;
}

.sql-block {
  margin-bottom: 10px;
}

.sql-label {
  display: block;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.sql-text {
  margin: 0;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 96px;
  overflow: auto;
}

.preview-block {
  margin-top: 4px;
}

.preview-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.preview-meta {
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

.preview-table {
  width: 100%;
}

.hl-field {
  color: var(--el-color-primary);
  font-weight: 600;
}

.preview-empty {
  padding: 8px 0;
}

@media (max-width: 720px) {
  .result-summary {
    flex-direction: column;
  }

  .summary-hint {
    text-align: left;
    max-width: none;
  }

  .compare-row {
    grid-template-columns: 1fr;
  }

  .item-rowcount {
    margin-left: 0;
  }
}
</style>
