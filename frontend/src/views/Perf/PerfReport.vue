<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">
        📈 性能测试报告 — {{ reportData.scene_name || '' }}
      </div>
    </template>
    <template #main>
      <!-- 返回按钮 -->
      <div class="back-bar">
        <el-button @click="goBack" :icon="ArrowLeft">返回记录列表</el-button>
        <div class="right-actions">
          <el-button type="primary" :icon="Message" @click="handleSendReport" :loading="sending" :disabled="reportData.status === 'running'">发送报告</el-button>
          <el-button type="success" :icon="Download" @click="handleExport" :loading="exporting">导出报告</el-button>
          <el-button v-if="hasStreamPhaseMetrics" type="warning" :icon="Download" @click="handleExportExcel" :loading="exportingExcel">导出 Excel</el-button>
          <div class="tag-group">
            <el-tag v-if="reportData.status" :type="getStatusType(reportData.status)">
              {{ getStatusLabel(reportData.status) }}
            </el-tag>
            <el-tag v-if="reportData.mode" :type="getModeType(reportData.mode)">
              {{ getModeLabel(reportData.mode) }}
            </el-tag>
            <el-tag v-if="configSummary.execution_type" type="info" size="small">
              {{ configSummary.execution_type }}
            </el-tag>
          </div>
        </div>
      </div>

      <el-alert
        v-if="reportData.stop_reason"
        :title="reportData.stop_reason"
        type="warning"
        show-icon
        :closable="false"
        style="margin-bottom: 16px;"
      />

      <!-- 压测配置摘要 -->
      <div class="config-section">
        <div class="section-header"><h3>⚙️ 压测配置</h3></div>
        <div class="config-grid">
          <div class="config-item"><span class="label">压测模式</span><span class="value">{{ configSummary.mode_label }}</span></div>
          <div class="config-item"><span class="label">并发用户</span><span class="value">{{ configSummary.concurrent_users ?? '-' }}</span></div>
          <div class="config-item"><span class="label">Ramp-up</span><span class="value">{{ configSummary.ramp_up_seconds }}s</span></div>
          <div class="config-item"><span class="label">持续/循环</span><span class="value">{{ configSummary.duration_label }}</span></div>
          <div class="config-item"><span class="label">分配模式</span><span class="value">{{ configSummary.distribution_mode_label }}</span></div>
          <div class="config-item"><span class="label">目标 Host</span><span class="value">{{ configSummary.target_host }}</span></div>
          <div class="config-item"><span class="label">执行方式</span><span class="value">{{ configSummary.execution_type }}</span></div>
          <div class="config-item"><span class="label">触发方式</span><span class="value">{{ reportData.trigger_type_label || '手动' }}</span></div>
          <div class="config-item"><span class="label">执行人</span><span class="value">{{ reportData.run_by || '-' }}</span></div>
          <div class="config-item"><span class="label">开始时间</span><span class="value">{{ reportData.started_at || '-' }}</span></div>
          <div class="config-item"><span class="label">结束时间</span><span class="value">{{ reportData.ended_at || '-' }}</span></div>
          <div class="config-item"><span class="label">峰值/平均并发</span><span class="value">{{ reportData.peak_concurrent }} / {{ reportData.avg_concurrent }}</span></div>
          <div class="config-item"><span class="label">接口明细</span><span class="value">{{ configSummary.request_detail_level_label || '简略（失败仍含接口详情）' }}</span></div>
        </div>
      </div>

      <!-- 与上次对比 -->
      <div v-if="previousComparison" class="table-section">
        <div class="section-header"><h3>📊 与上次同场景执行对比</h3></div>
        <div class="compare-hint">对比记录 #{{ previousComparison.record_id }}（{{ previousComparison.started_at }}）</div>
        <el-table :data="comparisonRows" size="small" border>
          <el-table-column prop="label" label="指标" width="140" />
          <el-table-column prop="previous" label="上次" width="100" align="center" />
          <el-table-column prop="current" label="本次" width="100" align="center" />
          <el-table-column label="变化" width="120" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.changeColor }">{{ row.changeText }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 分布式执行机 -->
      <div v-if="distributedWorkers.length" class="table-section">
        <div class="section-header"><h3>🖥️ 分布式执行机</h3></div>
        <el-table :data="distributedWorkers" size="small" border>
          <el-table-column prop="worker_id" label="Worker ID" width="90" align="center" />
          <el-table-column prop="host" label="主机" min-width="120" />
          <el-table-column prop="assigned_concurrent" label="分配并发" width="100" align="center" />
        </el-table>
      </div>

      <!-- 核心指标卡片 -->
      <div class="metrics-row">
        <el-tooltip placement="top" content="每秒请求数（HTTP 场景下等同 TPS）">
          <div class="metric-card primary">
            <div class="metric-value">{{ formatNum(reportData.qps) }}</div>
            <div class="metric-label">QPS</div>
          </div>
        </el-tooltip>
        <el-tooltip placement="top" content="仅统计成功请求的每秒吞吐">
          <div class="metric-card info">
            <div class="metric-value">{{ formatNum(reportData.success_qps) }}</div>
            <div class="metric-label">成功 QPS</div>
          </div>
        </el-tooltip>
        <el-tooltip placement="top" content="所有请求的平均响应时间">
          <div class="metric-card success">
            <div class="metric-value">{{ formatNum(reportData.avg_response_time) }}<span class="unit">ms</span></div>
            <div class="metric-label">平均响应时间</div>
          </div>
        </el-tooltip>
        <el-tooltip placement="top" content="95%的请求响应时间低于此值，反映大多数用户的体验">
          <div class="metric-card warning">
            <div class="metric-value">{{ formatNum(reportData.p95_response_time) }}<span class="unit">ms</span></div>
            <div class="metric-label">P95 响应时间</div>
          </div>
        </el-tooltip>
        <el-tooltip placement="top" content="失败请求占总请求的百分比">
          <div class="metric-card" :class="reportData.error_rate > 5 ? 'danger' : 'info'">
            <div class="metric-value">{{ formatNum(reportData.error_rate) }}<span class="unit">%</span></div>
            <div class="metric-label">错误率</div>
          </div>
        </el-tooltip>
      </div>

      <!-- 次要指标（可折叠） -->
      <el-collapse v-model="expandedPanels" class="detail-collapse">
        <el-collapse-item title="更多指标（请求统计 / 延迟分位 / 网络吞吐）" name="metrics">
          <div class="metrics-row secondary">
            <el-tooltip
              v-for="item in secondaryMetrics"
              :key="item.label"
              placement="top"
              :content="item.tip"
            >
              <div class="metric-card mini">
                <div class="metric-value">
                  {{ item.value }}<span v-if="item.unit" class="unit">{{ item.unit }}</span>
                </div>
                <div class="metric-label">{{ item.label }}</div>
              </div>
            </el-tooltip>
          </div>
          <div v-if="isThroughputZero" class="throughput-hint">
            接收/发送吞吐为 0 时，常见于 GET 无 Body、极小响应体，或分布式模式历史数据未统计；以 QPS 与 RT 为主即可。
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- 业务链路汇总 -->
      <div v-if="journeyPhaseRows.length" class="table-section">
        <div class="section-header"><h3>🔗 业务链路汇总</h3></div>
        <div class="config-grid" style="margin-bottom: 12px;">
          <div class="config-item"><span class="label">链路总数</span><span class="value">{{ journeySummary.total_journeys ?? '-' }}</span></div>
          <div class="config-item"><span class="label">链路成功率</span><span class="value">{{ journeySummary.journey_success_rate ?? '-' }}%</span></div>
          <div class="config-item"><span class="label">平均链路耗时</span><span class="value">{{ journeySummary.avg_journey_duration_ms ?? '-' }} ms</span></div>
          <div class="config-item"><span class="label">P95 链路耗时</span><span class="value">{{ journeySummary.p95_journey_duration_ms ?? '-' }} ms</span></div>
        </div>
        <el-table :data="journeyPhaseRows" size="small" border>
          <el-table-column prop="name" label="阶段" min-width="120" />
          <el-table-column prop="total" label="执行次数" width="90" align="center" />
          <el-table-column prop="success" label="成功" width="70" align="center" />
          <el-table-column prop="fail" label="失败" width="70" align="center" />
          <el-table-column prop="error_rate" label="失败率(%)" width="90" align="center" />
          <el-table-column prop="avg_duration_ms" label="平均耗时(ms)" width="110" align="center" />
          <el-table-column prop="p95_duration_ms" label="P95(ms)" width="90" align="center" />
        </el-table>
      </div>

      <!-- SSE 阶段指标汇总 -->
      <div v-if="phaseMetricsRows.length" class="table-section">
        <div class="section-header"><h3>⏱️ SSE 阶段计时汇总（正常请求）</h3></div>
        <el-table :data="phaseMetricsRows" size="small" border>
          <el-table-column prop="label" label="指标" min-width="140" />
          <el-table-column prop="normal_count" label="正常请求数" width="100" align="center" />
          <el-table-column prop="mean" label="平均(s)" width="90" align="center" />
          <el-table-column prop="median" label="中位数(s)" width="90" align="center" />
          <el-table-column prop="p90" label="P90(s)" width="80" align="center" />
          <el-table-column prop="p95" label="P95(s)" width="80" align="center" />
          <el-table-column prop="p99" label="P99(s)" width="80" align="center" />
          <el-table-column prop="min" label="最小(s)" width="80" align="center" />
          <el-table-column prop="max" label="最大(s)" width="80" align="center" />
        </el-table>
        <div class="field-tip" style="margin-top: 8px;">
          异常率 {{ phaseSummary.error_rate ?? 0 }}%（{{ phaseSummary.fail_count ?? 0 }}/{{ phaseSummary.total_requests ?? 0 }} 未返回答案）
        </div>
      </div>

      <!-- 流式请求阶段明细（分页懒加载） -->
      <div v-if="showStreamDetailSection" class="table-section">
        <div class="section-header detail-section-header">
          <div>
            <h3>📋 流式请求阶段明细</h3>
            <p class="field-tip">共 {{ streamDetailTotal }} 条，滚动加载更多；不影响上方 QPS/阶段汇总指标。</p>
          </div>
          <el-radio-group v-model="streamStatusFilter" size="small" @change="onStreamFilterChange">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="success">成功</el-radio-button>
            <el-radio-button value="fail">失败</el-radio-button>
          </el-radio-group>
        </div>
        <div ref="streamScrollRef" class="table-scroll stream-detail-scroll detail-lazy-scroll" @scroll="onStreamScroll">
          <el-table v-loading="streamLoading" :data="streamDetailRows" size="small" border stripe class="stream-detail-table">
            <el-table-column
              v-for="col in streamDetailColumns"
              :key="col"
              :prop="col"
              :label="col"
              :min-width="streamDetailColWidth(col)"
              :class-name="streamDetailColClass(col)"
            >
              <template #default="{ row }">
                <pre v-if="isStreamTextCol(col)" class="stream-text-pre">{{ row[col] ?? '-' }}</pre>
                <span v-else>{{ row[col] ?? '-' }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="streamLoading" class="lazy-load-hint">加载中…</div>
          <div v-else-if="!streamHasMore && streamDetailRows.length" class="lazy-load-hint">已加载全部</div>
        </div>
      </div>

      <!-- HTTP 请求明细（通用，分页懒加载） -->
      <div v-if="showHttpTraceSection" class="table-section">
        <div class="section-header detail-section-header">
          <div>
            <h3>🔗 HTTP 请求明细</h3>
            <p class="field-tip">共 {{ httpTraceTotal }} 条；详细模式含成功请求，失败始终保留采样。展开行查看请求/响应详情。</p>
          </div>
          <el-radio-group v-model="httpStatusFilter" size="small" @change="onHttpFilterChange">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="success">成功</el-radio-button>
            <el-radio-button value="fail">失败</el-radio-button>
          </el-radio-group>
        </div>
        <div ref="httpScrollRef" class="table-scroll detail-lazy-scroll" @scroll="onHttpScroll">
          <el-table v-loading="httpLoading" :data="httpTraceRows" size="small" border stripe>
            <el-table-column type="expand" width="40">
              <template #default="{ row }">
                <div class="trace-expand-panel">
                  <div class="trace-block" v-if="row.method || row.url">
                    <div class="trace-label">请求</div>
                    <div><span class="trace-k">Method</span> {{ row.method || '-' }}</div>
                    <div><span class="trace-k">URL</span> {{ row.url || '-' }}</div>
                  </div>
                  <div class="trace-block" v-if="row.request_headers_preview">
                    <div class="trace-label">请求头</div>
                    <pre class="trace-pre">{{ row.request_headers_preview }}</pre>
                  </div>
                  <div class="trace-block" v-if="row.request_params_preview">
                    <div class="trace-label">Query 参数</div>
                    <pre class="trace-pre">{{ row.request_params_preview }}</pre>
                  </div>
                  <div class="trace-block" v-if="row.request_body_preview">
                    <div class="trace-label">请求 Body</div>
                    <pre class="trace-pre">{{ row.request_body_preview }}</pre>
                  </div>
                  <div class="trace-block" v-if="row.thinking_preview">
                    <div class="trace-label">思考过程</div>
                    <pre class="trace-pre trace-pre-full">{{ row.thinking_preview }}</pre>
                  </div>
                  <div class="trace-block" v-if="row.response_body_preview">
                    <div class="trace-label">响应 / 流式内容</div>
                    <pre class="trace-pre trace-pre-full">{{ row.response_body_preview }}</pre>
                  </div>
                  <div class="trace-block" v-if="row.error_msg">
                    <div class="trace-label">错误信息</div>
                    <pre class="trace-pre error-text">{{ row.error_msg }}</pre>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column type="index" label="#" width="50" align="center" />
            <el-table-column prop="case_name" label="用例名称" min-width="120" show-overflow-tooltip />
            <el-table-column label="状态" width="72" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.success === false ? 'danger' : 'success'">
                  {{ row.success === false ? '失败' : '成功' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="user_id" label="用户ID" width="96" show-overflow-tooltip />
            <el-table-column prop="method" label="方法" width="64" align="center" />
            <el-table-column prop="url" label="URL" min-width="200" show-overflow-tooltip />
            <el-table-column prop="status_code" label="状态码" width="76" align="center" />
            <el-table-column prop="response_time" label="响应时间" width="96" align="center">
              <template #default="{ row }">{{ row.response_time }} ms</template>
            </el-table-column>
          </el-table>
          <div v-if="httpLoading" class="lazy-load-hint">加载中…</div>
          <div v-else-if="!httpHasMore && httpTraceRows.length" class="lazy-load-hint">已加载全部</div>
        </div>
      </div>

      <!-- 趋势图表 -->
      <div class="chart-section">
        <div class="section-header">
          <h3>📉 性能趋势图</h3>
        </div>
        <div v-if="!hasChartData" class="chart-empty">
          <el-empty description="暂无秒级时序数据（流式单次压测较短或分布式秒级上报未合并时可能出现；汇总 QPS/RT 仍有效）" :image-size="72" />
        </div>
        <div v-show="hasChartData" ref="chartRef" class="perf-chart"></div>
      </div>

      <!-- HTTP 状态码分布 -->
      <div v-if="statusCodeDistribution.length" class="table-section">
        <div class="section-header"><h3>📋 HTTP 状态码分布（全部请求）</h3></div>
        <el-table :data="statusCodeDistribution" size="small" border>
          <el-table-column prop="code" label="状态码" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.tagType">{{ row.code }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="count" label="次数" width="80" align="center" />
          <el-table-column prop="percentage" label="占比" width="90" align="center">
            <template #default="{ row }">{{ row.percentage }}%</template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 响应时间分布 -->
      <div v-if="rtHistogram.length" class="chart-section">
        <div class="section-header"><h3>📊 响应时间分布</h3></div>
        <div ref="histogramRef" class="perf-chart histogram-chart"></div>
      </div>

      <!-- 错误分类统计 -->
      <div v-if="hasErrors" class="table-section">
        <div class="section-header">
          <h3>❌ 错误分类统计</h3>
        </div>
        <div class="error-sections">
          <div class="error-panel" v-if="errorByType.length > 0">
            <h4>按错误类型</h4>
            <el-table :data="errorByType" size="small" border>
              <el-table-column prop="type" label="错误类型" min-width="140">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.tagType">{{ row.label }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="count" label="次数" width="80" align="center" />
              <el-table-column prop="percentage" label="占比" width="80" align="center">
                <template #default="{ row }">{{ row.percentage }}%</template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </div>

      <!-- 失败请求采样 -->
      <div v-if="failedSamples.length > 0" class="table-section">
        <div class="section-header">
          <h3>🔍 失败请求采样（前 {{ failedSamples.length }} 条）</h3>
        </div>
        <el-table :data="failedSamples" size="small" border stripe>
          <el-table-column type="index" label="#" width="50" align="center" />
          <el-table-column prop="case_name" label="用例名称" min-width="140" show-overflow-tooltip />
          <el-table-column prop="user_id" label="用户ID" width="100" show-overflow-tooltip />
          <el-table-column prop="question" label="问题" min-width="160" show-overflow-tooltip />
          <el-table-column prop="method" label="方法" width="70" align="center" />
          <el-table-column prop="url" label="URL" min-width="200" show-overflow-tooltip />
          <el-table-column prop="status_code" label="状态码" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status_code >= 500 ? 'danger' : row.status_code >= 400 ? 'warning' : row.status_code === 0 ? 'danger' : 'info'">
                {{ row.status_code === 0 ? '异常' : row.status_code }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="response_time" label="响应时间" width="100" align="center">
            <template #default="{ row }">{{ row.response_time }} ms</template>
          </el-table-column>
          <el-table-column prop="error_msg" label="错误详情" min-width="250" show-overflow-tooltip>
            <template #default="{ row }">
              <span style="color: #f56c6c;">{{ row.error_msg || '无详细信息' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 接口维度表格 -->
      <div class="table-section">
        <div class="section-header">
          <h3>🔍 接口维度详情</h3>
        </div>
        <el-alert
          v-if="caseAggregationList.length && caseRtSampleNote"
          :title="caseRtSampleNote"
          type="info"
          show-icon
          :closable="false"
          style="margin-bottom: 12px;"
        />
        <el-table :data="caseAggregationList" size="default" border stripe>
          <el-table-column prop="name" label="用例名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="total" label="总请求" width="75" align="center" />
          <el-table-column prop="success" label="成功" width="75" align="center" />
          <el-table-column prop="fail" label="失败" width="75" align="center" />
          <el-table-column prop="error_rate" label="错误率" width="85" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.error_rate > 5 ? '#f56c6c' : '#67c23a' }">{{ row.error_rate }}%</span>
            </template>
          </el-table-column>
          <el-table-column prop="qps" label="QPS" width="75" align="center" />
          <el-table-column prop="avg_rt" label="Avg" width="80" align="center" />
          <el-table-column prop="min_rt" label="Min" width="80" align="center" />
          <el-table-column prop="max_rt" label="Max" width="80" align="center" />
          <el-table-column prop="median_rt" label="Median" width="85" align="center" />
          <el-table-column prop="p90_rt" label="P90" width="80" align="center" />
          <el-table-column prop="p95_rt" label="P95" width="80" align="center" />
          <el-table-column prop="p99_rt" label="P99" width="80" align="center" />
          <el-table-column prop="std_dev" label="StdDev" width="85" align="center" />
        </el-table>
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Download, Message } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { perfRecordApi, perfExecApi } from '@/api'

// echarts 按需导入
import * as echarts from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
  DataZoomComponent, MarkLineComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart, BarChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
  DataZoomComponent, MarkLineComponent,
  CanvasRenderer
])

const route = useRoute()
const router = useRouter()
const recordId = route.params.recordId

const reportData = ref({})
const chartRef = ref(null)
const histogramRef = ref(null)
let chartInstance = null
let histogramInstance = null
let pollTimer = null
const exporting = ref(false)
const exportingExcel = ref(false)
const sending = ref(false)
const expandedPanels = ref([])

const configSummary = computed(() => reportData.value.config_summary || {})

const caseRtSampleNote = computed(() => configSummary.value.case_rt_sample_note || '')

const distributedWorkers = computed(() => {
  const workers = reportData.value.distribution_info?.workers || configSummary.value.workers || []
  return workers.map(w => ({
    worker_id: w.worker_id,
    host: w.host || '-',
    assigned_concurrent: w.assigned_concurrent ?? '-'
  }))
})

const previousComparison = computed(() => reportData.value.previous_comparison || null)

const comparisonRows = computed(() => {
  const comp = previousComparison.value
  if (!comp?.changes) return []
  return Object.values(comp.changes).map(item => {
    const pct = item.change_pct
    const improved = item.lower_is_better ? pct < 0 : pct > 0
    const worsened = item.lower_is_better ? pct > 0 : pct < 0
    let changeColor = '#909399'
    if (improved) changeColor = '#67c23a'
    if (worsened) changeColor = '#f56c6c'
    const sign = pct > 0 ? '+' : ''
    return {
      label: item.label,
      previous: formatCompareValue(item.label, item.previous),
      current: formatCompareValue(item.label, item.current),
      changeText: `${sign}${pct}%`,
      changeColor
    }
  })
})

const caseAggregationList = computed(() => {
  const aggs = reportData.value.case_aggregations || {}
  return Object.values(aggs)
})

const rtHistogram = computed(() => reportData.value.rt_histogram || [])

const secondaryMetrics = computed(() => {
  const d = reportData.value
  return [
    { label: '总请求数', tip: '本次压测执行过程中发出的 HTTP 请求总次数', value: d.total_requests || 0, unit: '' },
    { label: '成功数', tip: 'HTTP 状态正常且断言全部通过的请求数', value: d.success_count || 0, unit: '' },
    { label: '失败数', tip: 'HTTP 异常或断言未通过的请求数', value: d.fail_count || 0, unit: '' },
    { label: 'Min RT', tip: '本次所有请求中的最短响应时间', value: formatNum(d.min_response_time), unit: 'ms' },
    { label: 'Max RT', tip: '本次所有请求中的最长响应时间', value: formatNum(d.max_response_time), unit: 'ms' },
    { label: 'Median RT', tip: '响应时间中位数，50% 的请求低于此值', value: formatNum(d.median_response_time), unit: 'ms' },
    { label: 'P95 RT', tip: '95% 的请求响应时间低于此值，与趋势图中 P95 RT 曲线一致', value: formatNum(d.p95_response_time), unit: 'ms' },
    { label: 'P90 RT', tip: '90% 的请求响应时间低于此值', value: formatNum(d.p90_response_time), unit: 'ms' },
    { label: 'P99 RT', tip: '99% 的请求响应时间低于此值', value: formatNum(d.p99_response_time), unit: 'ms' },
    { label: 'StdDev RT', tip: '响应时间标准差，数值越大表示延迟波动越明显', value: formatNum(d.std_dev_response_time), unit: 'ms' },
    { label: '接收吞吐', tip: '每秒从服务端接收的数据量', value: formatThroughput(d.received_kb_per_sec), unit: '' },
    { label: '发送吞吐', tip: '每秒向服务端发送的数据量', value: formatThroughput(d.sent_kb_per_sec), unit: '' },
    { label: '执行时长', tip: '压测从开始到结束的实际耗时', value: formatNum(d.duration), unit: 's' }
  ]
})

const statusCodeDistribution = computed(() => {
  const bd = reportData.value.error_breakdown || {}
  const dist = bd.status_code_distribution || {}
  const total = reportData.value.total_requests || 0
  const denominator = total > 0 ? total : 1
  const tag = (code) => {
    const c = parseInt(code, 10)
    if (c === 0) return 'danger'
    if (c >= 500) return 'danger'
    if (c >= 400) return 'warning'
    if (c >= 200 && c < 300) return 'success'
    return 'info'
  }
  return Object.entries(dist)
    .map(([code, count]) => ({
      code: code === '0' ? '异常' : code,
      count,
      percentage: Math.round(count / denominator * 1000) / 10,
      tagType: tag(code)
    }))
    .sort((a, b) => b.count - a.count)
})

const isThroughputZero = computed(() => {
  const r = reportData.value.received_kb_per_sec
  const s = reportData.value.sent_kb_per_sec
  return (!r || r === 0) && (!s || s === 0)
})

const hasErrors = computed(() => {
  const bd = reportData.value.error_breakdown || {}
  return (bd.by_type && Object.keys(bd.by_type).length > 0) ||
         (bd.by_status_code && Object.keys(bd.by_status_code).length > 0) ||
         (reportData.value.fail_count > 0)
})

const errorByType = computed(() => {
  const bd = reportData.value.error_breakdown || {}
  const byType = bd.by_type || {}
  const total = reportData.value.fail_count || 1
  const typeMap = {
    timeout: { label: '请求超时', tagType: 'warning' },
    connection_error: { label: '连接错误', tagType: 'danger' },
    network_error: { label: '网络错误', tagType: 'danger' },
    server_error: { label: '服务端错误(5xx)', tagType: 'danger' },
    client_error: { label: '客户端错误(4xx)', tagType: 'warning' },
    assertion_failed: { label: '断言失败', tagType: 'info' },
    unknown: { label: '未知错误', tagType: 'info' }
  }
  return Object.entries(byType).map(([type, count]) => ({
    type,
    label: typeMap[type]?.label || type,
    tagType: typeMap[type]?.tagType || 'info',
    count,
    percentage: Math.round(count / total * 100)
  })).sort((a, b) => b.count - a.count)
})

const failedSamples = computed(() => {
  const bd = reportData.value.error_breakdown || {}
  return bd.failed_samples || []
})

const STREAM_TEXT_COLS = new Set(['问题', '答案预览', '思考过程', '参考文件', '错误信息', '参考资料(全部)', '参考资料(高分)'])
const STREAM_FULL_TEXT_KEYS = new Set(['thinking', 'answer_preview', 'references_all', 'references_high', 'reference_files'])

const isStreamTextCol = (col) => STREAM_TEXT_COLS.has(col)

const streamDetailRows = ref([])
const streamDetailTotal = ref(0)
const streamHasMore = ref(false)
const streamLoading = ref(false)
const streamPage = ref(1)
const streamStatusFilter = ref('all')
const streamScrollRef = ref(null)

const httpTraceRows = ref([])
const httpTraceTotal = ref(0)
const httpHasMore = ref(false)
const httpLoading = ref(false)
const httpPage = ref(1)
const httpStatusFilter = ref('all')
const httpScrollRef = ref(null)

const showStreamDetailSection = computed(() =>
  (reportData.value.request_details_total || 0) > 0 || streamDetailTotal.value > 0
)
const showHttpTraceSection = computed(() =>
  (reportData.value.request_traces_total || 0) > 0 || httpTraceTotal.value > 0
)

const buildStreamDetailRow = (index, d) => {
  const row = {
    '序号': index,
    '用户ID': d.user_id || '',
    '问题': d.question || '',
    '是否成功': d.success ? '是' : '否',
    '整体耗时(s)': d.total_time_s ?? '',
    '响应状态码': d.status_code ?? '',
    '错误信息': d.error || ''
  }
  const schema = d.phase_schema || []
  for (const s of schema) {
    if (s.key && s.label && row[s.label] === undefined) {
      row[s.label] = (d.phases || {})[s.key]
    }
  }
  for (const [key, val] of Object.entries(d.phases || {})) {
    const label = schema.find(s => s.key === key)?.label || key
    if (row[label] === undefined) row[label] = val
  }
  const extras = d.extras || {}
  const extraSchema = d.extra_schema || []
  const labelMap = Object.fromEntries(extraSchema.filter(s => s.key).map(s => [s.key, s.label]))
  const usedLabels = new Set(Object.keys(row))
  for (const [ek, ev] of Object.entries(extras)) {
    let col = labelMap[ek] || ek
    if (usedLabels.has(col)) col = `${labelMap[ek] || ek}(${ek})`
    usedLabels.add(col)
    if (typeof ev === 'string') {
      row[col] = STREAM_FULL_TEXT_KEYS.has(ek) ? ev : ev.replace(/\n/g, ' ').slice(0, 500)
    } else {
      row[col] = ev
    }
  }
  return row
}

const STREAM_COL_ORDER = ['序号', '用户ID', '问题', '是否成功', '整体耗时(s)', '响应状态码', '错误信息']

const streamDetailColumns = computed(() => {
  const keys = new Set()
  streamDetailRows.value.forEach(row => Object.keys(row).forEach(k => keys.add(k)))
  const rest = [...keys].filter(k => !STREAM_COL_ORDER.includes(k))
  return [...STREAM_COL_ORDER.filter(k => keys.has(k)), ...rest]
})

const loadStreamDetails = async (reset = false) => {
  if (streamLoading.value) return
  if (!reset && !streamHasMore.value && streamDetailRows.value.length > 0) return
  if (reset) {
    streamPage.value = 1
    streamDetailRows.value = []
    streamHasMore.value = true
  }
  streamLoading.value = true
  try {
    const res = await perfRecordApi.getRequestItems(recordId, {
      kind: 'stream',
      status: streamStatusFilter.value,
      page: streamPage.value,
      size: 50
    })
    const data = res.data || res
    streamDetailTotal.value = data.total || 0
    streamHasMore.value = !!data.has_more
    const base = reset ? 0 : streamDetailRows.value.length
    const rows = (data.items || []).map((d, i) => buildStreamDetailRow(base + i + 1, d))
    streamDetailRows.value = reset ? rows : [...streamDetailRows.value, ...rows]
    if (data.has_more) streamPage.value += 1
  } catch (e) {
    console.error(e)
    ElMessage.error('加载流式明细失败')
  } finally {
    streamLoading.value = false
  }
}

const loadHttpTraces = async (reset = false) => {
  if (httpLoading.value) return
  if (!reset && !httpHasMore.value && httpTraceRows.value.length > 0) return
  if (reset) {
    httpPage.value = 1
    httpTraceRows.value = []
    httpHasMore.value = true
  }
  httpLoading.value = true
  try {
    const res = await perfRecordApi.getRequestItems(recordId, {
      kind: 'http',
      status: httpStatusFilter.value,
      page: httpPage.value,
      size: 50
    })
    const data = res.data || res
    httpTraceTotal.value = data.total || 0
    httpHasMore.value = !!data.has_more
    const rows = data.items || []
    httpTraceRows.value = reset ? rows : [...httpTraceRows.value, ...rows]
    if (data.has_more) httpPage.value += 1
  } catch (e) {
    console.error(e)
    ElMessage.error('加载 HTTP 追踪明细失败')
  } finally {
    httpLoading.value = false
  }
}

const onStreamFilterChange = () => loadStreamDetails(true)
const onHttpFilterChange = () => loadHttpTraces(true)

const onLazyScroll = (e, loader) => {
  const el = e.target
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 100) loader()
}
const onStreamScroll = (e) => onLazyScroll(e, () => loadStreamDetails(false))
const onHttpScroll = (e) => onLazyScroll(e, () => loadHttpTraces(false))

const streamDetailColWidth = (col) => {
  if (col === '思考过程') return 360
  if (STREAM_TEXT_COLS.has(col)) return 220
  if (col.includes('时间') || col.endsWith('(s)')) return 110
  if (['序号', '用户ID', '是否成功', '响应状态码'].includes(col)) return 90
  return 100
}

const streamDetailColClass = (col) => (isStreamTextCol(col) ? 'stream-text-col' : '')

const getStatusType = (status) => {
  const map = { running: 'warning', success: 'success', failed: 'danger', stopped: 'info', pending: 'info' }
  return map[status] || ''
}

const getStatusLabel = (status) => {
  const map = { running: '执行中', success: '成功', failed: '失败', stopped: '已停止', pending: '等待中' }
  return map[status] || status
}

const getModeType = (mode) => {
  const map = { fixed: 'primary', loop: 'success', stepping: 'warning', stream_burst: 'danger', sse_burst: 'danger', journey_fixed: 'success', journey_loop: 'success' }
  return map[mode] || ''
}

const getModeLabel = (mode) => {
  const map = { fixed: '固定', loop: '循环', stepping: '梯度', stream_burst: '流式阶段', sse_burst: '流式阶段', journey_fixed: '链路固定', journey_loop: '链路循环' }
  return map[mode] || mode
}

const journeySummary = computed(() => reportData.value.journey_aggregations || {})
const journeyPhaseRows = computed(() => {
  const phases = journeySummary.value.phases || {}
  return Object.entries(phases).map(([key, p]) => ({
    key,
    name: p.name || `阶段${Number(key) + 1}`,
    total: p.total ?? 0,
    success: p.success ?? 0,
    fail: p.fail ?? 0,
    error_rate: p.error_rate ?? 0,
    avg_duration_ms: p.avg_duration_ms ?? '-',
    p95_duration_ms: p.p95_duration_ms ?? '-'
  }))
})

const isStreamBurstMode = computed(() => ['stream_burst', 'sse_burst'].includes(reportData.value.mode))
const hasStreamPhaseMetrics = computed(() => isStreamBurstMode.value)

const hasChartData = computed(() => {
  const ts = reportData.value.time_series_data
  return Array.isArray(ts) && ts.length > 0
})

const phaseSummary = computed(() => reportData.value.phase_metrics || {})
const phaseMetricsRows = computed(() => {
  const metrics = phaseSummary.value.metrics || []
  return metrics.map(m => ({
    ...m,
    mean: m.mean ?? 'N/A',
    median: m.median ?? 'N/A',
    p90: m.p90 ?? 'N/A',
    p95: m.p95 ?? 'N/A',
    p99: m.p99 ?? 'N/A',
    min: m.min ?? 'N/A',
    max: m.max ?? 'N/A',
  }))
})

const formatNum = (val) => {
  if (val === undefined || val === null) return '-'
  if (typeof val === 'number') return val.toFixed(2)
  return val
}

const formatThroughput = (val) => {
  if (val === undefined || val === null) return '-'
  if (typeof val !== 'number' || val === 0) return '0.00 KB/s'
  if (val < 0.01) return '<0.01 KB/s'
  return `${val.toFixed(2)} KB/s`
}

const formatCompareValue = (label, val) => {
  if (val === undefined || val === null) return '-'
  if (label.includes('率')) return `${val}%`
  if (label.includes('时间')) return `${val} ms`
  return typeof val === 'number' ? val.toFixed(2) : val
}

const goBack = () => {
  router.push('/perf-records')
}

const handleExport = async () => {
  exporting.value = true
  try {
    const res = await perfRecordApi.exportReport(recordId)
    const blob = new Blob([res.data], { type: 'text/html' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `perf_report_${recordId}_${new Date().getTime()}.html`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (err) {
    console.error(err)
    ElMessage.error('报告导出失败')
  } finally {
    exporting.value = false
  }
}

const handleExportExcel = async () => {
  exportingExcel.value = true
  try {
    const res = await perfRecordApi.exportExcel(recordId)
    const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `sse_phase_report_${recordId}_${new Date().getTime()}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('Excel 导出成功')
  } catch (err) {
    console.error(err)
    ElMessage.error(err?.response?.data?.detail || 'Excel 导出失败')
  } finally {
    exportingExcel.value = false
  }
}

const handleSendReport = async () => {
  if (reportData.value.status === 'running') {
    ElMessage.warning('压测进行中，请稍后再发送报告')
    return
  }
  sending.value = true
  try {
    await perfRecordApi.sendReport(recordId)
    ElMessage.success('报告邮件已发送')
  } catch (err) {
    console.error(err)
    ElMessage.error(err?.response?.data?.detail || '报告发送失败，请检查 SMTP 与通知配置')
  } finally {
    sending.value = false
  }
}

/** 与后端 normalize_time_series_for_chart 一致，兼容旧数据 */
const normalizeChartTimeSeries = (series) => {
  if (!series?.length) return []
  const points = [...series].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
  const totals = points.map(p => Number(p.total_req) || 0)
  const looksCumulative = points.length > 1 && totals.every((t, i) => i === 0 || t >= totals[i - 1]) && totals[totals.length - 1] > 0
  return points.map((p, i) => {
    const item = { ...p }
    let secReq = Number(item.qps) || 0
    if (looksCumulative) {
      const prev = i > 0 ? totals[i - 1] : 0
      secReq = Math.max(0, totals[i] - prev)
      item.qps = Math.round(secReq * 100) / 100
      item.total_req = secReq
    } else if (secReq <= 0 && item.total_req) {
      secReq = Number(item.total_req)
      item.qps = secReq
    }
    if (item.p95_rt == null) item.p95_rt = item.avg_rt
    return item
  })
}

const loadReport = async () => {
  try {
    const res = await perfRecordApi.getReport(recordId)
    reportData.value = res.data || res
    if ((reportData.value.request_details_total || 0) > 0) {
      await loadStreamDetails(true)
    } else {
      streamDetailRows.value = []
      streamDetailTotal.value = 0
    }
    if ((reportData.value.request_traces_total || 0) > 0) {
      await loadHttpTraces(true)
    } else {
      httpTraceRows.value = []
      httpTraceTotal.value = 0
    }
    nextTick(() => {
      initChart()
      initHistogramChart()
    })
  } catch (err) {
    console.error(err)
    ElMessage.error('加载报告失败')
  }
}

const initChart = () => {
  if (!chartRef.value) return
  if (chartInstance) {
    chartInstance.dispose()
  }

  const timeSeries = normalizeChartTimeSeries(reportData.value.time_series_data || [])
  if (timeSeries.length === 0) return

  chartInstance = echarts.init(chartRef.value)

  const summaryQps = reportData.value.qps
  const summaryP95 = reportData.value.p95_response_time

  const xData = timeSeries.map(d => d.timestamp + 's')
  const qpsData = timeSeries.map(d => d.qps)
  const avgRtData = timeSeries.map(d => d.avg_rt)
  const p95RtData = timeSeries.map(d => {
    if (!d.qps || d.qps <= 0) return null
    if (d.p95_rt != null) return d.p95_rt
    return d.avg_rt != null ? d.avg_rt : null
  })
  const p95MarkLine = summaryP95 != null ? {
    silent: true,
    symbol: 'none',
    lineStyle: { type: 'dotted', color: '#c9a227', opacity: 0.75 },
    label: { formatter: `全程 P95: ${summaryP95} ms`, position: 'insideEndTop', color: '#c9a227' },
    data: [{ yAxis: summaryP95 }]
  } : undefined
  const usersData = timeSeries.map(d => d.active_users)
  const errorRateData = timeSeries.map(d => d.error_rate || 0)

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter (params) {
        if (!params?.length) return ''
        const axis = params[0].axisValue
        const lines = [axis]
        params.forEach(p => {
          let val = p.value
          if (p.seriesName === 'QPS') {
            val = `${val}（该秒瞬时）`
          } else if (String(p.seriesName).includes('RT')) {
            val = `${val} ms`
          } else if (p.seriesName === '错误率') {
            val = `${val}%`
          }
          lines.push(`${p.marker}${p.seriesName}: ${val}`)
        })
        if (summaryQps != null) {
          lines.push(`<span style="color:#909399">全程平均 QPS: ${summaryQps}</span>`)
        }
        if (summaryP95 != null) {
          lines.push(`<span style="color:#909399">全程 P95 RT: ${summaryP95} ms</span>`)
        }
        return lines.join('<br/>')
      }
    },
    legend: {
      data: ['QPS', '平均RT', 'P95 RT', '错误率', '并发用户数'],
      bottom: 0
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: true,
      data: xData,
      name: '时间(秒)'
    },
    yAxis: [
      {
        type: 'value',
        name: '响应时间(ms)',
        position: 'left',
        axisLine: { show: true, lineStyle: { color: '#5470c6' } },
        axisLabel: { formatter: '{value} ms' }
      },
      {
        type: 'value',
        name: 'QPS',
        position: 'right',
        axisLine: { show: true, lineStyle: { color: '#91cc75' } },
        axisLabel: { formatter: '{value}' }
      }
    ],
    series: [
      {
        name: 'QPS',
        type: 'bar',
        yAxisIndex: 1,
        data: qpsData,
        itemStyle: { color: '#91cc75', opacity: 0.7 },
        barMaxWidth: 20
      },
      {
        name: '平均RT',
        type: 'line',
        yAxisIndex: 0,
        data: avgRtData,
        smooth: true,
        itemStyle: { color: '#5470c6' },
        lineStyle: { width: 2 }
      },
      {
        name: 'P95 RT',
        type: 'line',
        yAxisIndex: 0,
        data: p95RtData,
        connectNulls: false,
        smooth: true,
        itemStyle: { color: '#fac858' },
        lineStyle: { width: 2, type: 'dashed' },
        markLine: p95MarkLine
      },
      {
        name: '错误率',
        type: 'line',
        yAxisIndex: 1,
        data: errorRateData,
        smooth: true,
        itemStyle: { color: '#e6a23c' },
        lineStyle: { width: 1 }
      },
      {
        name: '并发用户数',
        type: 'line',
        yAxisIndex: 1,
        data: usersData,
        smooth: true,
        itemStyle: { color: '#ee6666' },
        lineStyle: { width: 1, type: 'dotted' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(238,102,102,0.2)' },
            { offset: 1, color: 'rgba(238,102,102,0.02)' }
          ])
        }
      }
    ]
  }

  chartInstance.setOption(option)
}

const initHistogramChart = () => {
  if (!histogramRef.value || !rtHistogram.value.length) return
  if (histogramInstance) histogramInstance.dispose()
  histogramInstance = echarts.init(histogramRef.value)
  const sorted = [...rtHistogram.value].sort((a, b) => (a.min || 0) - (b.min || 0))
  histogramInstance.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      data: sorted.map(h => `${h.label} ms`),
      axisLabel: { rotate: 35, fontSize: 11 }
    },
    yAxis: { type: 'value', name: '请求数' },
    series: [{
      name: '请求数',
      type: 'bar',
      data: sorted.map(h => h.count),
      itemStyle: { color: '#5470c6', opacity: 0.85 },
      barMaxWidth: 40
    }]
  })
}

// 轮询
const startPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    if (reportData.value.status === 'running') {
      try {
        const res = await perfExecApi.getStatus(recordId)
        const data = res.data || res
        const patch = { ...data }
        if (Array.isArray(data.time_series) && data.time_series.length > 0) {
          patch.time_series_data = data.time_series
        }
        reportData.value = { ...reportData.value, ...patch }
        if (patch.time_series_data?.length) {
          nextTick(() => {
            initChart()
            initHistogramChart()
          })
        }
        if (data.status !== 'running') {
          loadReport()
        }
      } catch (e) {
        console.error(e)
      }
    }
  }, 3000)
}

onMounted(() => {
  loadReport()
  startPolling()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (chartInstance) chartInstance.dispose()
  if (histogramInstance) histogramInstance.dispose()
})

window.addEventListener('resize', () => {
  chartInstance && chartInstance.resize()
  histogramInstance && histogramInstance.resize()
})
</script>

<style scoped>
.back-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.tag-group {
  display: flex;
  gap: 8px;
}
.right-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.config-section {
  background: #fff;
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
}
.config-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.config-item {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 10px 12px;
}
.config-item .label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.config-item .value {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  word-break: break-all;
}
.compare-hint {
  font-size: 13px;
  color: #909399;
  margin-bottom: 10px;
}
.detail-collapse {
  margin-bottom: 16px;
}
.throughput-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
  line-height: 1.6;
}
.histogram-chart {
  height: 280px;
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.metrics-row.secondary {
  grid-template-columns: repeat(6, 1fr);
}

.metric-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  padding: 18px;
  color: #fff;
  text-align: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

.metric-card.success {
  background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
}

.metric-card.warning {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.metric-card.info {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.metric-card.danger {
  background: linear-gradient(135deg, #ff416c 0%, #ff4b2b 100%);
}

.metric-card.mini {
  padding: 12px;
}

.metric-card.mini .metric-value {
  font-size: 18px;
}

.metric-card.mini .metric-label {
  font-size: 12px;
}

.metric-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}

.metric-value .unit {
  font-size: 14px;
  font-weight: 400;
  margin-left: 4px;
  opacity: 0.9;
}

.metric-label {
  font-size: 13px;
  margin-top: 6px;
  opacity: 0.95;
}

.chart-section {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
}

.table-section {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
}

.section-header {
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  color: #333;
}

.perf-chart {
  width: 100%;
  height: 400px;
}

.chart-empty {
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.error-sections {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.error-panel h4 {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: #666;
}

@media (max-width: 1200px) {
  .config-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .metrics-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .metrics-row.secondary {
    grid-template-columns: repeat(3, 1fr);
  }
  .error-sections {
    grid-template-columns: 1fr;
  }
}

.table-scroll {
  overflow-x: auto;
  max-width: 100%;
}

.stream-detail-scroll :deep(.el-table__cell) {
  white-space: nowrap;
}

.stream-detail-table :deep(.stream-text-col .cell) {
  white-space: normal;
  align-items: flex-start;
}

.stream-text-pre {
  margin: 0;
  padding: 0;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  max-height: none;
}

.stream-detail-table :deep(.cell) {
  white-space: nowrap;
}

.detail-section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.detail-lazy-scroll {
  max-height: 480px;
  overflow-y: auto;
}

.lazy-load-hint {
  text-align: center;
  padding: 10px;
  font-size: 12px;
  color: #909399;
}

.trace-expand-panel {
  padding: 8px 12px 12px 48px;
  background: #fafafa;
}

.trace-block {
  margin-bottom: 10px;
}

.trace-label {
  font-weight: 600;
  font-size: 13px;
  color: #303133;
  margin-bottom: 4px;
}

.trace-k {
  color: #909399;
  margin-right: 6px;
}

.trace-pre {
  margin: 0;
  padding: 8px 10px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow: auto;
}

.trace-pre.trace-pre-full {
  max-height: none;
  overflow: visible;
}

.trace-pre.error-text {
  color: #f56c6c;
}
</style>
