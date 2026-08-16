<template>
  <div class="case-detail">
    <div v-if="hasTimingSummary" class="case-timing-summary">
      <RunTimingBadges :result="item" />
    </div>

    <!-- 错误信息 -->
    <el-alert
      v-if="item.error_msg"
      :title="item.error_msg"
      type="error"
      :closable="false"
      show-icon
    />

    <!-- 重试信息 -->
    <div class="section" v-if="item.retry_info && item.retry_info.retry_count > 0">
      <h4>重试历史 <el-tag size="small" type="warning" style="margin-left:6px">重试 {{ item.retry_info.retry_count }} 次 / 共 {{ item.retry_info.total_attempts }} 次尝试</el-tag></h4>
      <div class="retry-timeline">
        <div
          v-for="(attempt, idx) in item.retry_info.attempts"
          :key="idx"
          class="retry-item"
          :class="attempt.status"
        >
          <div class="retry-dot" :class="attempt.status"></div>
          <div class="retry-content">
            <div class="retry-title">
              第 {{ idx + 1 }} 次尝试
              <el-tag :type="attempt.status === 'success' ? 'success' : (attempt.status === 'error' ? 'danger' : 'warning')" size="small">
                {{ attempt.status === 'success' ? '成功' : (attempt.status === 'error' ? '异常' : '失败') }}
              </el-tag>
              <span v-if="attempt.response_status" class="retry-status-code">
                HTTP {{ attempt.response_status }}
              </span>
              <span v-if="attempt.response_time != null" class="retry-time">
                {{ attempt.response_time.toFixed ? attempt.response_time.toFixed(0) : attempt.response_time }}ms
              </span>
            </div>
            <div v-if="attempt.error" class="retry-error">{{ attempt.error }}</div>
            <div v-if="attempt.assertion_total > 0" class="retry-assertions">
              断言: {{ attempt.assertion_passed }}/{{ attempt.assertion_total }} 通过
              <span
                v-for="(a, ai) in (attempt.assertions || [])"
                :key="ai"
                class="retry-assert-badge"
                :class="a.passed ? 'passed' : 'failed'"
              >
                {{ a.target || a.type }}
                <span class="assert-op">{{ a.operator }}</span>
                <span class="assert-expected">{{ a.expected }}</span>
                <span v-if="!a.passed" class="assert-actual">实际: {{ actualPreview(a.actual) }}</span>
              </span>
            </div>
            <div v-if="attempt.response_body !== undefined && attempt.response_body !== null" class="retry-body">
              <details>
                <summary style="cursor:pointer;font-size:12px;color:#909399;">响应 Body</summary>
                <div class="code-scroll-wrap" style="margin-top:6px;">
                  <pre class="json-viewer">{{ formatJson(attempt.response_body) }}</pre>
                </div>
              </details>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 断言结果 -->
    <div class="section" v-if="item.assertions?.length">
      <h4>断言结果</h4>
      <el-table :data="item.assertions" border size="small" class="assertion-result-table">
        <el-table-column prop="type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ getAssertionTypeText(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="target" label="目标" min-width="150" />
        <el-table-column prop="operator" label="操作" width="100" />
        <el-table-column prop="expected" label="预期值" min-width="100" />
        <el-table-column label="实际值" min-width="200">
          <template #default="{ row }">
            <AssertionActualCell :row="row" />
          </template>
        </el-table-column>
        <el-table-column prop="passed" label="结果" width="80">
          <template #default="{ row }">
            <el-icon :color="row.passed ? '#67c23a' : '#f56c6c'">
              <CircleCheck v-if="row.passed" />
              <CircleClose v-else />
            </el-icon>
          </template>
        </el-table-column>
      </el-table>
    </div>
    
    <!-- 变量提取 -->
    <div class="section" v-if="item.extracted_vars && Object.keys(item.extracted_vars).length">
      <h4>提取变量</h4>
      <el-table :data="formatExtractedVars(item)" size="small" border>
        <el-table-column prop="name" label="变量名" width="140" />
        <el-table-column prop="value" label="值" show-overflow-tooltip />
        <el-table-column label="被引用" width="180" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.usedBy.length" placement="top">
              <template #content>
                <div v-for="u in row.usedBy" :key="u.case_id">{{ u.case_name }}</div>
              </template>
              <el-tag size="small" type="success">
                {{ row.usedBy.length }} 个用例
              </el-tag>
            </el-tooltip>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
    
    <!-- 阶段耗时 -->
    <div
      class="section"
      v-if="item.request_detail?.stage_timings && Object.keys(item.request_detail.stage_timings).length"
    >
      <CaseStageTimings
        :timings="item.request_detail.stage_timings"
        :result="item"
      />
    </div>

    <!-- 响应摘要：状态码 / 耗时 / Headers（套件、计划报告也复用本组件） -->
    <div class="section" v-if="hasResponseSummary">
      <h4>响应信息</h4>
      <el-descriptions border size="small" class="response-info-desc">
        <el-descriptions-item label="状态码">{{ responseStatusCode ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="接口耗时">{{ formatTimingMs(getHttpResponseMs(item)) }}</el-descriptions-item>
        <el-descriptions-item label="用例总耗时">{{ formatTimingMs(getCaseTotalMs(item)) }}</el-descriptions-item>
      </el-descriptions>
      <div class="detail-block" v-if="hasEffectiveResponseHeaders" style="margin-top: 12px;">
        <div class="detail-title">响应 Headers</div>
        <CopyablePre :text="effectiveResponseHeaders" max-height="240px" wrap />
      </div>
    </div>

    <!-- 请求详情和变量替换 -->
    <div class="section" v-if="item.request_detail && Object.keys(item.request_detail).length">
      <el-tabs v-model="detailActiveTab">
        <!-- 请求详情 -->
        <el-tab-pane label="请求详情" name="request">
          <div class="detail-block">
            <div class="detail-title">请求 URL</div>
            <div class="detail-content">
              <div class="compare-row">
                <span class="label">原始:</span>
                <code class="original">{{ item.request_detail.url?.original || '-' }}</code>
              </div>
              <div class="compare-row">
                <span class="label">最终:</span>
                <code class="final">{{ item.request_detail.url?.final || '-' }}</code>
              </div>
            </div>
          </div>
          <div class="detail-block" v-if="Object.keys(item.request_detail.headers?.final || {}).length">
            <div class="detail-title">请求 Headers</div>
            <CopyablePre :text="item.request_detail.headers?.final" max-height="320px" wrap />
          </div>
          <div class="detail-block" v-if="hasRequestParams">
            <div class="detail-title">请求参数</div>
            <CopyablePre :text="item.request_detail.params?.final" max-height="280px" wrap />
          </div>
          <div
            class="detail-block"
            v-if="item.request_detail.body_type === 'form-data' && item.request_detail.body_fields?.final?.length"
          >
            <div class="detail-title">Form Data 字段</div>
            <CopyablePre :text="item.request_detail.body_fields.final" max-height="320px" wrap />
          </div>
          <div class="detail-block" v-else-if="hasRequestBody">
            <div class="detail-title">请求 Body</div>
            <CopyablePre :text="item.request_detail.body?.final" max-height="420px" fill min-height="180px" />
          </div>
          <div class="detail-block" v-if="item.request_detail.script_logs?.length">
            <div class="detail-title">脚本日志</div>
            <CopyablePre :text="item.request_detail.script_logs.join('\n')" max-height="240px" wrap />
          </div>
        </el-tab-pane>
        
        <!-- 变量替换 -->
        <el-tab-pane label="变量替换" name="variables">
          <div class="detail-block" v-if="Object.keys(item.request_detail.variables_used || {}).length">
            <div class="detail-title">环境变量</div>
            <div class="detail-content">
              <el-descriptions :column="2" border size="small">
                <el-descriptions-item 
                  v-for="(value, key) in item.request_detail.variables_used" 
                  :key="key"
                  :label="key"
                >{{ value }}</el-descriptions-item>
              </el-descriptions>
            </div>
          </div>
          <div class="detail-block">
            <div class="detail-title">替换详情</div>
            <div class="detail-content">
              <el-empty v-if="!item.request_detail.replacements?.length" description="没有变量替换"/>
              <el-table v-else :data="item.request_detail.replacements" size="small" border>
                <el-table-column label="变量名" prop="key" width="100"/>
                <el-table-column label="来源用例" width="120" align="center">
                  <template #default="{ row }">
                    <el-tag v-if="row.source_case_name" size="small" type="warning">
                      {{ row.source_case_name }}
                    </el-tag>
                    <el-tag v-else size="small" type="info">环境变量</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="原始值" prop="original" width="130">
                  <template #default="{ row }">
                    <code class="original">{{ row.original }}</code>
                  </template>
                </el-table-column>
                <el-table-column label="替换后" prop="replaced" width="130">
                  <template #default="{ row }">
                    <code class="final">{{ row.replaced }}</code>
                  </template>
                </el-table-column>
                <el-table-column label="位置" prop="path" width="80"/>
              </el-table>
            </div>
          </div>
        </el-tab-pane>
        
        <el-tab-pane label="响应Body" name="response-body">
          <ResponseBodyViewer
            v-if="effectiveResponseBody != null"
            ref="responseBodyPreRef"
            :body="effectiveResponseBody"
            :highlight-text="responseBodyHighlight"
            max-height="480px"
            fill
            min-height="200px"
          >
            <template #extra>
              <span v-if="responseBodyHighlight" class="highlight-tip">正在高亮断言期望值</span>
            </template>
          </ResponseBodyViewer>
          <el-empty v-else description="暂无响应 Body" :image-size="60" />
        </el-tab-pane>
        
        <!-- 响应Headers：摘要区已展示时仍保留完整 Tab，便于定位 -->
        <el-tab-pane label="响应Headers" name="response-headers">
          <CopyablePre
            v-if="hasEffectiveResponseHeaders"
            :text="effectiveResponseHeaders"
            max-height="320px"
            wrap
          />
          <el-empty v-else description="暂无响应 Headers" :image-size="60" />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 无 request_detail 时仍展示响应 Body -->
    <div class="section" v-else-if="effectiveResponseBody != null">
      <h4>响应 Body</h4>
      <ResponseBodyViewer
        :body="effectiveResponseBody"
        max-height="480px"
        fill
        min-height="200px"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { formatResponseJson } from '../utils/formatResponse'
import CaseStageTimings from './CaseStageTimings.vue'
import RunTimingBadges from './RunTimingBadges.vue'
import CopyablePre from '@/components/CopyablePre.vue'
import ResponseBodyViewer from '@/components/ResponseBodyViewer.vue'
import AssertionActualCell from '@/components/AssertionActualCell.vue'
import { getAssertionActualPreview } from '@/utils/assertionDisplay.js'
import { provideAssertionResponseLocate } from '@/composables/assertionResponseLocate.js'
import { getHttpResponseMs, getCaseTotalMs, formatTimingMs } from '../utils/runTiming'
import { assertionTypeLabel } from '../utils/httpExtractAssertUi.js'

const props = defineProps({
  item: {
    type: Object,
    required: true
  }
})

const detailActiveTab = ref('request')
const responseBodyHighlight = ref('')
const responseBodyPreRef = ref(null)

function locateExpectedInResponseBody(expected) {
  const term = String(expected ?? '').trim()
  if (!term) return false
  if (effectiveResponseBody.value == null || effectiveResponseBody.value === '') return false
  responseBodyHighlight.value = term
  detailActiveTab.value = 'response-body'
  return true
}

provideAssertionResponseLocate(locateExpectedInResponseBody)

const hasTimingSummary = computed(() => {
  return getHttpResponseMs(props.item) != null || getCaseTotalMs(props.item) != null
})

const hasRequestParams = computed(() => {
  const params = props.item.request_detail?.params?.final
  if (Array.isArray(params)) return params.length > 0
  return params && typeof params === 'object' && Object.keys(params).length > 0
})

const hasRequestBody = computed(() => {
  const body = props.item.request_detail?.body?.final
  if (body === null || body === undefined || body === '') return false
  if (typeof body === 'object' && !Array.isArray(body)) {
    return Object.keys(body).length > 0
  }
  return true
})

/** 计划执行等场景可能只有 response_detail，无顶层 response_body */
const effectiveResponseBody = computed(() => {
  const item = props.item
  if (item.response_body !== undefined && item.response_body !== null && item.response_body !== '') {
    return item.response_body
  }
  if (item.response_detail?.body !== undefined && item.response_detail?.body !== null) {
    return item.response_detail.body
  }
  const attempts = item.request_detail?.retry_info?.attempts || item.retry_info?.attempts
  if (attempts?.length) {
    const last = attempts[attempts.length - 1]
    if (last.response_body !== undefined && last.response_body !== null) {
      return last.response_body
    }
  }
  return null
})

const effectiveResponseHeaders = computed(() => {
  const item = props.item
  const candidates = [
    item.response_headers,
    item.response_detail?.headers,
  ]
  const attempts = item.request_detail?.retry_info?.attempts || item.retry_info?.attempts
  if (attempts?.length) {
    const last = attempts[attempts.length - 1]
    candidates.push(last.response_headers, last.headers)
  }
  for (const headers of candidates) {
    if (!headers) continue
    if (Array.isArray(headers) && headers.length) return headers
    if (typeof headers === 'object' && Object.keys(headers).length) return headers
    if (typeof headers === 'string' && headers.trim()) return headers
  }
  return null
})

const hasEffectiveResponseHeaders = computed(() => {
  const headers = effectiveResponseHeaders.value
  if (!headers) return false
  if (Array.isArray(headers)) return headers.length > 0
  if (typeof headers === 'object') return Object.keys(headers).length > 0
  return String(headers).trim().length > 0
})

const responseStatusCode = computed(() => {
  const item = props.item
  return item.response_status
    ?? item.response_detail?.status_code
    ?? item.request_detail?.retry_info?.attempts?.slice(-1)?.[0]?.response_status
    ?? null
})

const hasResponseSummary = computed(() => {
  return responseStatusCode.value != null
    || getHttpResponseMs(props.item) != null
    || getCaseTotalMs(props.item) != null
    || hasEffectiveResponseHeaders.value
})

const getAssertionTypeText = (type) => assertionTypeLabel(type)

const formatJson = (data) => formatResponseJson(data)

const actualPreview = (val) => getAssertionActualPreview(val)

const formatExtractedVars = (item) => {
  const meta = item.extracted_meta || {}
  return Object.entries(item.extracted_vars || {}).map(([name, value]) => ({
    name,
    value: String(value),
    usedBy: meta[name]?.used_by || []
  }))
}

</script>

<style lang="scss" scoped>
.case-detail {
  padding: 15px;

  .case-timing-summary {
    margin-bottom: 12px;
    padding-bottom: 12px;
    border-bottom: 1px dashed var(--el-border-color-lighter);
  }
  
  :deep(.assertion-result-table) {
    .el-table__cell {
      vertical-align: top;
    }
  }

  .section {
    margin-bottom: 20px;
    
    h4 {
      margin: 0 0 10px;
      color: #333;
      font-size: 14px;
    }
  }
}

.code-scroll-wrap {
  max-width: 100%;
  max-height: 400px;
  overflow: auto;
  background: #f5f7fa;
  border-radius: 4px;
}

.json-viewer {
  padding: 12px;
  margin: 0;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  white-space: pre;
  word-break: normal;
  min-width: min-content;
}

  .detail-block {
  margin-bottom: 15px;
  
  .detail-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
  }

  .detail-title {
    font-weight: 600;
    font-size: 13px;
    color: #333;
    margin-bottom: 0;
    padding-left: 8px;
    border-left: 3px solid #409eff;
  }
  
  .detail-content {
    background: #f5f7fa;
    border-radius: 4px;
    padding: 10px;
    
    .compare-row {
      display: flex;
      align-items: center;
      margin-bottom: 6px;
      
      &:last-child {
        margin-bottom: 0;
      }
      
      .label {
        width: 50px;
        color: #666;
        font-size: 12px;
      }
      
      code {
        flex: 1;
        padding: 3px 6px;
        border-radius: 3px;
        font-family: monospace;
        font-size: 12px;
        word-break: break-all;
        
        &.original {
          background: #eee;
          color: #999;
          text-decoration: line-through;
        }
        
        &.final {
          background: #e6f7ff;
          color: #1890ff;
        }
      }
    }
  }
}

.response-tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.highlight-tip {
  font-size: 12px;
  color: var(--el-color-warning);
}

.retry-timeline {
  padding-left: 8px;

  .retry-item {
    display: flex;
    gap: 12px;
    padding: 10px 0;
    border-left: 2px solid #dcdfe6;
    padding-left: 16px;
    position: relative;

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
        gap: 8px;
        font-size: 13px;

        .retry-status-code {
          color: #909399;
          font-size: 12px;
        }

        .retry-time {
          color: #67c23a;
          font-size: 12px;
        }
      }

      .retry-error {
        margin-top: 4px;
        font-size: 12px;
        color: #F56C6C;
      }

      .retry-assertions {
        margin-top: 4px;
        font-size: 12px;
        color: #606266;
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 6px;
      }

      .retry-assert-badge {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 11px;
        border: 1px solid;

        &.passed {
          background: #f0f9eb;
          border-color: #b3e19d;
          color: #67c23a;
        }

        &.failed {
          background: #fef0f0;
          border-color: #fbc4c4;
          color: #f56c6c;
        }

        .assert-op { color: #909399; margin: 0 2px; }
        .assert-expected { font-weight: 600; }
        .assert-actual { color: #f56c6c; margin-left: 4px; }
      }

      .retry-body {
        margin-top: 6px;
      }
    }
  }
}
</style>
