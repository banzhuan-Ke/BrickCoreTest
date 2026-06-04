<template>
  <el-dialog
    v-model="dialogVisible"
    title="批量执行结果"
    width="1200px"
    top="4vh"
    class="batch-run-result-dialog"
    destroy-on-close
  >
    <!-- 统计头部 -->
    <div class="batch-summary" v-if="resultData">
      <div class="summary-item total">
        <span class="summary-num">{{ resultData.total || 0 }}</span>
        <span class="summary-label">总用例</span>
      </div>
      <div class="summary-item success">
        <span class="summary-num">{{ resultData.success || 0 }}</span>
        <span class="summary-label">成功</span>
      </div>
      <div class="summary-item failed">
        <span class="summary-num">{{ resultData.failed || 0 }}</span>
        <span class="summary-label">失败</span>
      </div>
      <div class="summary-item time" v-if="resultData.total_time">
        <span class="summary-num">{{ resultData.total_time.toFixed(2) }}s</span>
        <span class="summary-label">总耗时</span>
      </div>
    </div>

    <!-- 结果表格 -->
    <el-table
      :data="resultData?.results || []"
      stripe
      size="small"
      v-loading="loading"
      max-height="500"
    >
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column label="用例名称" min-width="160">
        <template #default="{ row }">
          <div class="case-name-cell">
            <span class="case-name-text">{{ row.case_name }}</span>
            <el-tag
              v-if="row.retry_info && row.retry_info.retry_count > 0"
              size="small"
              type="warning"
              class="retry-tag"
            >
              重试{{ row.retry_info.retry_count }}次
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
            {{ row.status === 'success' ? '通过' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="响应码" width="80" align="center">
        <template #default="{ row }">
          <span v-if="row.response_status">{{ row.response_status }}</span>
          <el-tag v-else-if="row.error" type="info" size="small">异常</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="接口耗时" width="100" align="center">
        <template #default="{ row }">
          <span v-if="getHttpResponseMs(row) != null" class="timing-http">
            {{ getHttpResponseMs(row).toFixed(2) }} ms
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="用例总耗时" width="100" align="center">
        <template #default="{ row }">
          <span v-if="row.response_time">{{ row.response_time.toFixed(2) }} ms</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="断言" width="100" align="center">
        <template #default="{ row }">
          <span v-if="row.assertions && row.assertions.length > 0">
            <span :class="getAssertionClass(row)">
              {{ getPassedCount(row) }}/{{ row.assertions.length }}
            </span>
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="重试历史" min-width="180">
        <template #default="{ row }">
          <div v-if="row.retry_info && row.retry_info.retry_count > 0" class="retry-history">
            <el-tooltip
              placement="top"
              :content="getRetryDetailTooltip(row.retry_info)"
            >
              <span class="retry-summary">{{ getRetrySummary(row.retry_info) }}</span>
            </el-tooltip>
          </div>
          <span v-else class="no-retry">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            size="small"
            @click="viewDetail(row)"
          >查看详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 单条详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      title="执行详情"
      width="1180px"
      top="4vh"
      class="run-detail-dialog"
      destroy-on-close
      append-to-body
    >
      <div v-if="detailData" class="run-detail-simple">
        <!-- 基本信息 -->
        <div class="detail-header">
          <el-tag :type="detailData.status === 'success' ? 'success' : 'danger'" size="large">
            {{ detailData.status === 'success' ? '执行成功' : '执行失败' }}
          </el-tag>
          <RunTimingBadges :result="detailData" />
          <span v-if="detailData.response_status" class="detail-meta">
            状态码: {{ detailData.response_status }}
          </span>
          <span v-if="detailData.retry_info && detailData.retry_info.retry_count > 0" class="detail-meta retry-badge">
            重试 {{ detailData.retry_info.retry_count }} 次 / 共 {{ detailData.retry_info.total_attempts }} 次尝试
          </span>
        </div>

        <div
          v-if="detailData.request_detail?.stage_timings"
          class="detail-section"
        >
          <CaseStageTimings
            :timings="detailData.request_detail.stage_timings"
            :result="detailData"
          />
        </div>

        <!-- 重试历史（增强版） -->
        <div v-if="detailData.retry_info && detailData.retry_info.retry_count > 0" class="detail-section">
          <div class="section-title">重试历史（{{ detailData.retry_info.total_attempts }} 次尝试）</div>
          <div class="retry-timeline">
            <div
              v-for="(attempt, idx) in detailData.retry_info.attempts"
              :key="idx"
              class="retry-item"
              :class="attempt.status"
            >
              <div class="retry-dot" :class="attempt.status"></div>
              <div class="retry-content">
                <div class="retry-title">
                  第 {{ idx + 1 }} 次尝试
                  <el-tag
                    :type="attempt.status === 'success' ? 'success' : (attempt.status === 'error' ? 'danger' : 'warning')"
                    size="small"
                  >
                    {{ attempt.status === 'success' ? '成功' : (attempt.status === 'error' ? '异常' : '失败') }}
                  </el-tag>
                  <span v-if="attempt.response_status" class="retry-status-code">HTTP {{ attempt.response_status }}</span>
                  <span v-if="attempt.response_time" class="retry-time">{{ attempt.response_time.toFixed(0) }}ms</span>
                </div>
                <div v-if="attempt.assertion_total > 0" class="retry-assertions">
                  断言: {{ attempt.assertion_passed }}/{{ attempt.assertion_total }} 通过
                  <template v-if="attempt.assertions && attempt.assertions.length > 0">
                    <span
                      v-for="(a, ai) in attempt.assertions"
                      :key="ai"
                      class="retry-assert-badge"
                      :class="a.passed ? 'pass' : 'fail'"
                    >
                      {{ a.type }}{{ a.target ? ':' + a.target : '' }} {{ a.passed ? '✓' : '✗' }}
                      <template v-if="!a.passed">（期望 {{ a.expected }}，实际 {{ a.actual }}）</template>
                    </span>
                  </template>
                </div>
                <div v-if="attempt.error" class="retry-error">{{ attempt.error }}</div>
                <div v-if="attempt.response_body !== undefined && attempt.response_body !== null" class="retry-body">
                  <span class="retry-body-label">响应Body:</span>
                  <pre class="retry-body-content">{{ formatJson(attempt.response_body) }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 错误信息 -->
        <div v-if="detailData.error" class="detail-section">
          <div class="section-title">错误信息</div>
          <pre class="error-text">{{ detailData.error }}</pre>
        </div>

        <!-- 断言结果 -->
        <div v-if="detailData.assertions && detailData.assertions.length > 0" class="detail-section">
          <div class="section-title">最终断言结果</div>
          <el-table :data="detailData.assertions" border size="small">
            <el-table-column label="类型" width="90" prop="type" />
            <el-table-column label="目标" min-width="140" prop="target" show-overflow-tooltip />
            <el-table-column label="操作符" width="80" prop="operator" />
            <el-table-column label="期望值" width="120" prop="expected" show-overflow-tooltip />
            <el-table-column label="实际值" min-width="200">
              <template #default="{ row }">
                <AssertionActualCell :row="row" />
              </template>
            </el-table-column>
            <el-table-column label="结果" width="70" align="center">
              <template #default="{ row }">
                <el-icon :color="row.passed ? '#67C23A' : '#F56C6C'">
                  <CircleCheck v-if="row.passed" />
                  <CircleClose v-else />
                </el-icon>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 提取变量 -->
        <div v-if="detailExtractorRows.length > 0" class="detail-section">
          <div class="section-title">变量提取详情</div>
          <el-table :data="detailExtractorRows" border size="small">
            <el-table-column label="变量名" prop="name" width="110" />
            <el-table-column label="来源" prop="source" width="70" />
            <el-table-column label="路径" prop="path" min-width="120" show-overflow-tooltip />
            <el-table-column label="状态" width="70" align="center">
              <template #default="{ row }">
                <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                  {{ row.success ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="值/说明" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.success ? formatActual(row.value) : (row.error || '—') }}
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div v-else-if="detailData.extracted_vars && Object.keys(detailData.extracted_vars).length > 0" class="detail-section">
          <div class="section-title">提取变量</div>
          <el-descriptions border size="small" :column="2">
            <el-descriptions-item
              v-for="(val, key) in detailData.extracted_vars"
              :key="key"
              :label="key"
            >{{ val }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 请求/响应详情 tab -->
        <div v-if="detailData.request_detail || detailData.response_detail" class="detail-section">
          <el-tabs v-model="detailActiveTab" size="small">
            <el-tab-pane label="请求详情" name="request" v-if="detailData.request_detail">
              <div class="compare-row" v-if="detailData.request_detail.url">
                <span class="label">原始URL:</span>
                <code class="original">{{ detailData.request_detail.url.original || '-' }}</code>
                <CopyTextButton :text="detailData.request_detail.url.original || ''" />
              </div>
              <div class="compare-row" v-if="detailData.request_detail.url">
                <span class="label">最终URL:</span>
                <code class="final">{{ detailData.request_detail.url.final || '-' }}</code>
                <CopyTextButton :text="detailData.request_detail.url.final || ''" />
              </div>
              <div v-if="Object.keys(detailData.request_detail.headers?.final || {}).length > 0" style="margin-top:8px">
                <div class="mini-title-row">
                  <div class="mini-title">请求 Headers</div>
                  <CopyTextButton :text="detailData.request_detail.headers?.final" />
                </div>
                <CopyablePre :text="detailData.request_detail.headers?.final" max-height="280px" wrap />
              </div>
              <div v-if="detailData.request_detail.body?.final" style="margin-top:8px">
                <div class="mini-title-row">
                  <div class="mini-title">请求 Body</div>
                  <CopyTextButton :text="detailData.request_detail.body?.final" />
                </div>
                <CopyablePre :text="detailData.request_detail.body?.final" max-height="320px" wrap />
              </div>
            </el-tab-pane>
            <el-tab-pane label="响应Body" name="response-body" v-if="detailData.response_detail">
              <ResponseBodyViewer
                :body="detailData.response_detail.body"
                :highlight-text="detailResponseHighlight"
                max-height="72vh"
                fill
                min-height="360px"
              />
            </el-tab-pane>
            <el-tab-pane label="响应Headers" name="response-headers" v-if="detailData.response_detail?.headers">
              <div class="mini-title-row">
                <div class="mini-title">响应 Headers</div>
                <CopyTextButton :text="detailData.response_detail.headers" />
              </div>
              <CopyablePre :text="detailData.response_detail.headers" max-height="320px" wrap />
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>
    </el-dialog>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { CircleCheck, CircleClose } from '@element-plus/icons-vue'
import RunTimingBadges from './RunTimingBadges.vue'
import CaseStageTimings from './CaseStageTimings.vue'
import CopyTextButton from '@/components/CopyTextButton.vue'
import CopyablePre from '@/components/CopyablePre.vue'
import ResponseBodyViewer from '@/components/ResponseBodyViewer.vue'
import AssertionActualCell from '@/components/AssertionActualCell.vue'
import { provideAssertionResponseLocate } from '@/composables/assertionResponseLocate.js'
import { getHttpResponseMs } from '../utils/runTiming'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  resultData: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue'])

const detailVisible = ref(false)
const detailData = ref(null)
const detailActiveTab = ref('request')
const detailResponseHighlight = ref('')

function locateExpectedInDetailResponse(expected) {
  const term = String(expected ?? '').trim()
  if (!term || !detailData.value?.response_detail) return false
  detailResponseHighlight.value = term
  detailActiveTab.value = 'response-body'
  return true
}

provideAssertionResponseLocate((expected) => {
  if (!detailVisible.value) return false
  return locateExpectedInDetailResponse(expected)
})

watch(detailVisible, (visible) => {
  if (!visible) {
    detailResponseHighlight.value = ''
    detailActiveTab.value = 'request'
  }
})

const detailExtractorRows = computed(() => {
  const d = detailData.value
  if (!d) return []
  const rows = d.extractor_results || d.request_detail?.extractor_results
  return Array.isArray(rows) ? rows : []
})

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const getPassedCount = (row) => {
  if (!row.assertions) return 0
  return row.assertions.filter(a => a.passed).length
}

const getAssertionClass = (row) => {
  const total = row.assertions?.length || 0
  const passed = getPassedCount(row)
  if (passed === total) return 'assert-all-pass'
  if (passed === 0) return 'assert-all-fail'
  return 'assert-partial'
}

const getRetrySummary = (retryInfo) => {
  if (!retryInfo || !retryInfo.attempts || retryInfo.attempts.length === 0) {
    return ''
  }
  const count = retryInfo.retry_count
  const last = retryInfo.attempts[retryInfo.attempts.length - 1]
  const lastStatus = last.status || 'unknown'
  return `重试${count}次，最终${lastStatus === 'success' ? '成功' : '失败'}`
}

const getRetryDetailTooltip = (retryInfo) => {
  if (!retryInfo || !retryInfo.attempts) return ''
  const lines = retryInfo.attempts.map((a, idx) => {
    const statusText = a.status === 'success' ? '成功' : '失败'
    const codeText = a.response_status ? `(${a.response_status})` : ''
    return `第${idx + 1}次：${statusText}${codeText}`
  })
  return lines.join('\n')
}

const viewDetail = (row) => {
  // 直接展示本地详情，不跳转报告页
  detailData.value = row
  detailVisible.value = true
}

const formatJson = (data) => {
  if (data === null || data === undefined) return ''
  try {
    if (typeof data === 'string') return JSON.stringify(JSON.parse(data), null, 2)
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

const formatActual = (val) => {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}
</script>

<style scoped lang="scss">
.batch-run-result-dialog {
  .batch-summary {
    display: flex;
    gap: 20px;
    margin-bottom: 16px;
    padding: 12px 16px;
    background: #f5f7fa;
    border-radius: 8px;

    .summary-item {
      display: flex;
      flex-direction: column;
      align-items: center;
      min-width: 60px;

      .summary-num {
        font-size: 20px;
        font-weight: bold;
        line-height: 1.2;
      }

      .summary-label {
        font-size: 12px;
        color: #909399;
        margin-top: 4px;
      }

      &.total .summary-num { color: #409EFF; }
      &.success .summary-num { color: #67C23A; }
      &.failed .summary-num { color: #F56C6C; }
      &.time .summary-num { color: #E6A23C; }
    }
  }

  .case-name-cell {
    display: flex;
    flex-direction: column;
    gap: 2px;

    .case-name-text {
      font-size: 13px;
    }

    .retry-tag {
      align-self: flex-start;
    }
  }

  .assert-all-pass {
    color: #67C23A;
    font-weight: bold;
  }

  .assert-all-fail {
    color: #F56C6C;
    font-weight: bold;
  }

  .assert-partial {
    color: #E6A23C;
    font-weight: bold;
  }

  .retry-history {
    .retry-summary {
      font-size: 12px;
      color: #E6A23C;
      cursor: help;
    }
  }

  .no-retry {
    color: #C0C4CC;
  }
}

.run-detail-simple {
  max-height: 70vh;
  overflow-y: auto;

  .detail-header {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 16px;
    padding: 12px;
    background: #f5f7fa;
    border-radius: 6px;

    .detail-meta {
      font-size: 13px;
      color: #606266;
    }

    .retry-badge {
      color: #E6A23C;
      font-weight: 500;
    }
  }

  .detail-section {
    margin-bottom: 16px;

    .section-title {
      font-weight: bold;
      font-size: 14px;
      margin-bottom: 8px;
      padding: 4px 0 6px 8px;
      border-left: 3px solid #409EFF;
      border-bottom: 1px solid #ebeef5;
    }
  }

  .retry-timeline {
    padding-left: 8px;

    .retry-item {
      padding: 10px 0 10px 16px;
      border-left: 2px solid #dcdfe6;
      position: relative;
      margin-bottom: 2px;

      &.success { border-left-color: #67C23A; }
      &.failed { border-left-color: #F56C6C; }
      &.error { border-left-color: #F56C6C; }

      .retry-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #dcdfe6;
        position: absolute;
        left: -6px;
        top: 14px;

        &.success { background: #67C23A; }
        &.failed { background: #F56C6C; }
        &.error { background: #F56C6C; }
      }

      .retry-content {
        .retry-title {
          display: flex;
          align-items: center;
          flex-wrap: wrap;
          gap: 6px;
          font-size: 13px;
          font-weight: 500;

          .retry-status-code {
            color: #909399;
            font-size: 12px;
          }

          .retry-time {
            color: #909399;
            font-size: 12px;
          }
        }

        .retry-assertions {
          margin-top: 6px;
          font-size: 12px;
          color: #606266;
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
          align-items: center;

          .retry-assert-badge {
            display: inline-block;
            padding: 1px 6px;
            border-radius: 3px;
            font-size: 11px;
            font-family: monospace;

            &.pass {
              background: #f0f9eb;
              color: #67C23A;
              border: 1px solid #c2e7b0;
            }

            &.fail {
              background: #fef0f0;
              color: #F56C6C;
              border: 1px solid #fbc4c4;
            }
          }
        }

        .retry-error {
          margin-top: 4px;
          font-size: 12px;
          color: #F56C6C;
        }

        .retry-body {
          margin-top: 6px;

          .retry-body-label {
            font-size: 11px;
            color: #909399;
            margin-right: 4px;
          }

          .retry-body-content {
            background: #f5f7fa;
            border-radius: 3px;
            padding: 6px 8px;
            font-size: 11px;
            font-family: monospace;
            max-height: 80px;
            overflow: auto;
            white-space: pre-wrap;
            word-break: break-all;
            margin: 4px 0 0;
          }
        }
      }
    }
  }

  .actual-fail {
    color: #F56C6C;
  }

  .compare-row {
    display: flex;
    align-items: center;
    margin-bottom: 6px;

    .label {
      width: 70px;
      flex-shrink: 0;
      color: #909399;
      font-size: 12px;
    }

    code {
      flex: 1;
      padding: 3px 8px;
      border-radius: 3px;
      font-family: monospace;
      font-size: 12px;
      word-break: break-all;

      &.original {
        background: #f5f5f5;
        color: #999;
        text-decoration: line-through;
      }

      &.final {
        background: #e6f7ff;
        color: #1890ff;
      }
    }
  }

  .mini-title {
    font-size: 12px;
    font-weight: 600;
    color: #606266;
    margin-bottom: 4px;
  }

  .mini-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 6px;
  }

  .error-text {
    background: #fef0f0;
    color: #F56C6C;
    padding: 10px;
    border-radius: 4px;
    font-size: 13px;
    white-space: pre-wrap;
    word-break: break-all;
  }

  .json-block {
    background: #f5f7fa;
    padding: 10px;
    border-radius: 4px;
    font-size: 12px;
    max-height: 240px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
    margin: 0;
    font-family: monospace;
  }
}
</style>
