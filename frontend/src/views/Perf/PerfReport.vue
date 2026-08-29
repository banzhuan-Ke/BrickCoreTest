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
          <el-button
            v-if="canPinBaseline"
            type="warning"
            plain
            :loading="pinningBaseline"
            :disabled="isCurrentBaseline"
            @click="handlePinBaseline"
          >{{ isCurrentBaseline ? '已是基线' : '设为基线' }}</el-button>
          <el-button type="primary" :icon="Message" @click="handleSendReport" :loading="sending" :disabled="reportData.status === 'running'">发送报告</el-button>
          <el-button type="success" :icon="Download" @click="handleExport" :loading="exporting">导出报告</el-button>
          <el-button v-if="hasStreamPhaseMetrics" type="warning" :icon="Download" @click="handleExportExcel" :loading="exportingExcel">导出 Excel</el-button>
          <div class="tag-group">
            <el-tag v-if="reportData.status" :type="getStatusType(reportData.status)">
              {{ getStatusLabel(reportData.status) }}
            </el-tag>
            <el-tag v-if="isCurrentBaseline" type="warning" size="small">基线</el-tag>
            <el-tag v-if="executionModeTag" type="info" size="small">{{ executionModeTag }}</el-tag>
            <el-tag v-if="reportData.mode" :type="getModeType(reportData.mode)">
              {{ getModeLabel(reportData.mode) }}
            </el-tag>
          </div>
        </div>
      </div>

      <el-alert
        v-if="caseDrift.has_drift"
        type="warning"
        show-icon
        :closable="false"
        style="margin-bottom: 16px;"
      >
        <template #title>用例已变更（指标仍反映执行当时行为）</template>
        <div style="font-size: 13px; line-height: 1.6;">
          <div v-for="item in caseDrift.items" :key="item.case_id">
            <template v-if="item.status === 'missing'">
              #{{ item.case_id }} {{ item.name || '' }} — 已删除或不存在
            </template>
            <template v-else>
              #{{ item.case_id }} {{ item.name || '' }} — 执行时 {{ item.snapshotted_at }}，当前 {{ item.current_update_time }}
            </template>
          </div>
        </div>
      </el-alert>

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
          <div class="config-item">
            <span class="label">{{ configSummary.concurrent_users_label || '并发用户' }}</span>
            <span class="value">{{ configSummary.concurrent_users_display ?? configSummary.concurrent_users ?? '-' }}</span>
          </div>
          <div class="config-item"><span class="label">Ramp-up</span><span class="value">{{ configSummary.ramp_up_seconds }}s</span></div>
          <div class="config-item"><span class="label">热身 Warmup</span><span class="value">{{ configSummary.warmup_seconds ?? 0 }}s</span></div>
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
        <PerfAiInlineNote
          v-if="liveAi?.overview"
          :text="liveAi.overview"
          label="概览"
          style="margin-top: 12px"
        />
        <div v-if="steppingStages.length" class="stepping-stages" style="margin-top: 16px;">
          <div class="section-header" style="margin-bottom: 8px;"><h4 style="margin:0;font-size:14px;">梯度阶段明细</h4></div>
          <p class="compare-hint" style="margin-bottom: 8px;">
            按配置阶段列出计划并发/时长；平均 QPS 含整段墙钟（无完成秒记 0）。
            平均 RT/P95 仅统计「有完成请求」的秒，避免被大量空闲秒稀释。
          </p>
          <p v-if="steppingStages.length" class="compare-hint" style="margin-bottom: 10px; color:#334155;">
            分阶段摘要（按阶段分行）：
          </p>
          <div v-if="steppingStages.length" class="stage-summary-list" style="margin-bottom:12px">
            <div
              v-for="st in steppingStages"
              :key="'ss-' + st.stage"
              class="stage-summary-card flat"
              style="margin-bottom:6px"
            >
              <div class="stage-sum-title">
                <span class="stage-idx">{{ st.stage }}</span>
                <span>第 {{ st.stage }} 阶段 · {{ st.users }} 并发</span>
              </div>
              <div class="stage-sum-meta" style="font-size:12.5px;color:#64748b;line-height:1.5">
                有完成 {{ st.completed_seconds ?? '-' }}s
                · QPS {{ st.avg_qps ?? '-' }}
                · RT {{ st.avg_rt ?? '-' }}ms
                <template v-if="st.avg_rt != null">（约 {{ Math.round((Number(st.avg_rt) / 1000) * 10) / 10 }}s）</template>
                · P95 {{ st.avg_p95 ?? '-' }}ms
              </div>
            </div>
          </div>
          <el-table :data="steppingStages" size="small" border :fit="false" style="width: max-content; max-width: 100%;">
            <el-table-column prop="stage" label="阶段" width="88" align="center">
              <template #default="{ row }">第 {{ row.stage }} 阶段</template>
            </el-table-column>
            <el-table-column prop="users" label="并发" width="72" align="center" />
            <el-table-column prop="planned_duration" label="计划时长(s)" width="104" align="center">
              <template #default="{ row }">{{ row.planned_duration ?? '-' }}</template>
            </el-table-column>
            <el-table-column prop="observed_seconds" label="观察秒数" width="88" align="center">
              <template #default="{ row }">{{ row.observed_seconds ?? '-' }}</template>
            </el-table-column>
            <el-table-column prop="completed_seconds" label="有完成秒数" width="100" align="center">
              <template #default="{ row }">{{ row.completed_seconds ?? '-' }}</template>
            </el-table-column>
            <el-table-column prop="avg_qps" label="平均 QPS" width="96" align="center">
              <template #default="{ row }">{{ row.avg_qps ?? '-' }}</template>
            </el-table-column>
            <el-table-column prop="avg_rt" label="平均 RT(ms)" width="140" align="center">
              <template #default="{ row }">
                <span v-if="row.avg_rt == null">-</span>
                <span v-else>{{ row.avg_rt }}（约 {{ (row.avg_rt / 1000).toFixed(1) }}s）</span>
              </template>
            </el-table-column>
            <el-table-column prop="avg_p95" label="平均 P95(ms)" width="140" align="center">
              <template #default="{ row }">
                <span v-if="row.avg_p95 == null">-</span>
                <span v-else>{{ row.avg_p95 }}（约 {{ (row.avg_p95 / 1000).toFixed(1) }}s）</span>
              </template>
            </el-table-column>
            <el-table-column prop="avg_error_rate" label="错误率(%)" width="96" align="center">
              <template #default="{ row }">{{ row.avg_error_rate ?? '-' }}</template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <!-- 与钉选基线对比 -->
      <div v-if="baselineComparison" class="table-section">
        <div class="section-header"><h3>📌 与场景基线对比</h3></div>
        <div class="compare-hint">
          基线记录 #{{ baselineComparison.record_id }}（{{ baselineComparison.started_at }}）
          <span v-if="baselineComparison.has_phase_changes">；含 SSE 阶段均值/P95 对比</span>
        </div>
        <el-alert
          v-for="(alert, idx) in baselineAlerts"
          :key="'ba-' + idx"
          :title="alert.message || alert"
          type="error"
          :closable="false"
          show-icon
          style="margin-bottom: 10px"
        />
        <el-alert
          v-for="(msg, idx) in baselineWarnings"
          :key="'bw-' + idx"
          :title="msg"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 10px"
        />
        <el-table v-if="baselineRows.length" :data="baselineRows" size="small" border>
          <el-table-column prop="label" label="指标" width="140" />
          <el-table-column prop="previous" label="基线" width="100" align="center" />
          <el-table-column prop="current" label="本次" width="100" align="center" />
          <el-table-column label="变化" width="120" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.changeColor }">{{ row.changeText }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 相对基线趋势：有钉选即可展示（含当前记录本身就是基线的情况） -->
      <div v-if="baselineTrend.points?.length" class="table-section">
        <div class="section-header"><h3>📈 相对基线趋势</h3></div>
        <div class="compare-hint">
          近期成功记录的 QPS / P95 / 错误率
          <span v-if="baselineTrend.baseline">（基线 #{{ baselineTrend.baseline.record_id }}）</span>
        </div>
        <div ref="baselineTrendChartRef" class="baseline-trend-chart"></div>
      </div>

      <!-- 与上次对比 -->
      <div v-if="previousComparison" class="table-section">
        <div class="section-header"><h3>📊 与上次同场景执行对比</h3></div>
        <div class="compare-hint">
          对比记录 #{{ previousComparison.record_id }}（{{ previousComparison.started_at }}）
          <span v-if="previousComparison.has_phase_changes">；含 SSE 阶段均值/P95 对比</span>
        </div>
        <el-alert
          v-for="(msg, idx) in comparisonWarnings"
          :key="'cw-' + idx"
          :title="msg"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 10px"
        />
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
      <el-alert
        v-if="metricsMetaTip"
        :title="metricsMetaTip"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />
      <el-alert
        v-if="sustainedStreamTip"
        :title="sustainedStreamTip"
        type="success"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />
      <el-alert
        v-if="showTargetTrustBox"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #title>可信度：偏低</template>
        <ul v-if="targetTrustWarnings.length" class="trust-warn-list">
          <li v-for="(w, idx) in targetTrustWarnings" :key="idx">{{ w }}</li>
        </ul>
        <div v-else>样本偏少，结论仅供参考</div>
      </el-alert>
      <div class="metrics-row">
        <el-tooltip placement="top" content="每秒请求数（HTTP 场景下等同 TPS）">
          <div class="metric-card" :class="metricCardClass('qps', 'primary')">
            <div class="metric-value">{{ formatNum(reportData.qps) }}</div>
            <div class="metric-label">QPS</div>
            <div v-if="metricCardNotes.qps" class="metric-sys-note">{{ metricCardNotes.qps }}</div>
          </div>
        </el-tooltip>
        <el-tooltip placement="top" content="仅统计成功请求的每秒吞吐">
          <div class="metric-card" :class="metricCardClass('success_qps', 'info')">
            <div class="metric-value">{{ formatNum(reportData.success_qps) }}</div>
            <div class="metric-label">成功 QPS</div>
            <div v-if="metricCardNotes.success_qps" class="metric-sys-note">{{ metricCardNotes.success_qps }}</div>
          </div>
        </el-tooltip>
        <el-tooltip placement="top" content="本次压测发出的 HTTP 请求总次数">
          <div class="metric-card" :class="metricCardClass('total_requests', 'info')">
            <div class="metric-value">{{ reportData.total_requests || 0 }}<span class="unit">次</span></div>
            <div class="metric-label">总请求数</div>
            <div v-if="metricCardNotes.total_requests" class="metric-sys-note">{{ metricCardNotes.total_requests }}</div>
          </div>
        </el-tooltip>
        <el-tooltip placement="top" content="所有请求的平均响应时间">
          <div class="metric-card" :class="metricCardClass('avg_response_time', 'success')">
            <div class="metric-value">{{ formatNum(reportData.avg_response_time) }}<span class="unit">ms</span></div>
            <div class="metric-label">平均响应时间</div>
            <div v-if="metricCardNotes.avg_response_time" class="metric-sys-note">{{ metricCardNotes.avg_response_time }}</div>
          </div>
        </el-tooltip>
        <el-tooltip placement="top" content="95%的请求响应时间低于此值，反映大多数用户的体验">
          <div class="metric-card" :class="metricCardClass('p95_response_time', 'warning')">
            <div class="metric-value">{{ formatNum(reportData.p95_response_time) }}<span class="unit">ms</span></div>
            <div class="metric-label">P95 响应时间</div>
            <div v-if="metricCardNotes.p95_response_time" class="metric-sys-note">{{ metricCardNotes.p95_response_time }}</div>
          </div>
        </el-tooltip>
        <el-tooltip
          v-if="successLatency.avg_response_time != null"
          placement="top"
          content="仅成功请求的平均响应时间（不含失败）"
        >
          <div class="metric-card" :class="metricCardClass('success_avg_response_time', 'success')">
            <div class="metric-value">{{ formatNum(successLatency.avg_response_time) }}<span class="unit">ms</span></div>
            <div class="metric-label">成功 Avg RT</div>
            <div v-if="metricCardNotes.success_avg_response_time" class="metric-sys-note">{{ metricCardNotes.success_avg_response_time }}</div>
          </div>
        </el-tooltip>
        <el-tooltip
          v-if="successLatency.p95_response_time != null"
          placement="top"
          content="仅成功请求的 P95 响应时间"
        >
          <div class="metric-card" :class="metricCardClass('success_p95_response_time', 'warning')">
            <div class="metric-value">{{ formatNum(successLatency.p95_response_time) }}<span class="unit">ms</span></div>
            <div class="metric-label">成功 P95 RT</div>
            <div v-if="metricCardNotes.success_p95_response_time" class="metric-sys-note">{{ metricCardNotes.success_p95_response_time }}</div>
          </div>
        </el-tooltip>
        <el-tooltip placement="top" content="失败请求占总请求的百分比">
          <div class="metric-card" :class="metricCardClass('error_rate', reportData.error_rate > 5 ? 'danger' : 'info')">
            <div class="metric-value">{{ formatNum(reportData.error_rate) }}<span class="unit">%</span></div>
            <div class="metric-label">错误率</div>
            <div v-if="metricCardNotes.error_rate" class="metric-sys-note">{{ metricCardNotes.error_rate }}</div>
          </div>
        </el-tooltip>
      </div>
      <el-alert
        v-if="!hasPerfTargetsConfigured"
        type="info"
        :closable="false"
        show-icon
        style="margin-top: 12px"
        title="未配置性能目标，无法判定是否达标（可在场景「性能验收目标」中配置）"
      />

      <div v-if="targetEvalItems.length" class="table-section" style="margin-top: 16px">
        <div class="section-header">
          <h3>性能目标明细
            <el-tag size="small" :type="overallTargetTagType" style="margin-left:8px">{{ overallTargetLabel }}</el-tag>
          </h3>
        </div>
        <el-table :data="targetEvalItems" size="small" border>
          <el-table-column prop="label" label="指标" min-width="140" />
          <el-table-column label="实际值" width="120" align="center">
            <template #default="{ row }">{{ formatTargetNum(row.actual, row.unit) }}</template>
          </el-table-column>
          <el-table-column label="目标" width="140" align="center">
            <template #default="{ row }">
              <span v-if="row.expected != null">{{ row.op }} {{ formatTargetNum(row.expected, row.unit) }}</span>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="判定" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="说明" min-width="220" />
        </el-table>
      </div>

      <!-- 与导出 HTML「响应时间分布」对齐：百分位表 + 条形图（默认展开） -->
      <div v-if="hasRtPercentiles" class="table-section rt-distribution-section">
        <div class="section-header">
          <h3>响应时间分布</h3>
        </div>
        <el-table :data="[rtPercentileRow]" size="small" border style="margin-bottom: 14px">
          <el-table-column
            v-for="col in rtPercentileColumns"
            :key="col.key"
            :prop="col.key"
            :label="col.label"
            align="center"
            min-width="90"
          >
            <template #default="{ row }">
              <span v-if="row[col.key] == null">—</span>
              <span v-else>{{ formatNum(row[col.key]) }}<span class="rt-unit"> ms</span></span>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="rtBarItems.length" class="rt-bars">
          <div v-for="bar in rtBarItems" :key="bar.label" class="rt-bar-row">
            <div class="rt-bar-label">{{ bar.label }}（{{ formatNum(bar.value) }} ms）</div>
            <div class="rt-bar-track">
              <div class="rt-bar-fill" :class="bar.color" :style="{ width: bar.widthPct + '%' }">
                {{ formatNum(bar.value) }} ms
              </div>
            </div>
          </div>
        </div>
        <p v-else class="field-tip">暂无可视化分位数据</p>
      </div>

      <!-- 次要指标（可折叠） -->
      <el-collapse v-model="expandedPanels" class="detail-collapse">
        <el-collapse-item title="更多指标（成功失败 / 其它分位 / 网络吞吐）" name="metrics">
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

      <div v-if="orphanMetricNoteRows.length" class="metric-notes-strip">
        <PerfAiInlineNote
          v-for="row in orphanMetricNoteRows"
          :key="row.key"
          :label="`AI 解读 · ${row.label}`"
          :text="row.note"
        />
      </div>

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

      <!-- SSE 阶段指标：仅当次压测配置了流式（stream_profile / 流式阶段模式）时展示 -->
      <div v-if="showPhaseMetricsSection" class="table-section phase-report-section">
        <div class="section-header detail-section-header">
          <div>
            <h3>SSE 阶段指标摘要</h3>
            <p class="field-tip">
              按解析配置中的阶段规则与派生指标生成；默认全部展示，可勾选着重项置顶。
              <span v-if="isSustainedStreamRun">流式持续压测时请与上方 QPS/RT 对照阅读。</span>
            </p>
          </div>
          <el-select
            v-model="phaseHighlightKeys"
            multiple
            clearable
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="着重指标（本页临时）"
            style="width: 280px"
            @change="onPhaseHighlightChange"
          >
            <el-option
              v-for="m in phaseMetricsRaw"
              :key="m.key"
              :label="m.label || m.key"
              :value="m.key"
            />
          </el-select>
        </div>
        <div class="phase-metric-cards">
          <div
            v-for="m in phaseMetricCardsOrdered"
            :key="m.key"
            class="phase-metric-card"
            :class="{ highlight: isPhaseHighlighted(m.key) }"
          >
            <div class="phase-metric-label">
              <span>{{ m.label || m.key }}</span>
              <el-tag v-if="isPhaseHighlighted(m.key)" size="small" type="warning" effect="plain">着重</el-tag>
            </div>
            <div class="phase-metric-values">
              <div class="phase-metric-main">
                <span class="pm-num">{{ formatPhaseSec(m.mean) }}</span>
                <span class="pm-unit">均值(s)</span>
              </div>
              <div class="phase-metric-sub">
                <span>P95 {{ formatPhaseSec(m.p95) }}s</span>
                <span>n={{ m.normal_count ?? m.count ?? '-' }}</span>
              </div>
            </div>
          </div>
        </div>
        <div ref="phaseChartRef" class="perf-chart phase-compare-chart"></div>
      </div>

      <!-- SSE 阶段指标汇总 -->
      <div v-if="showPhaseMetricsSection" class="table-section">
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
          异常率 {{ phaseSummary.error_rate ?? 0 }}%（{{ phaseSummary.fail_count ?? 0 }}/{{ phaseSummary.total_requests ?? 0 }} 未满足流式成功判定）
        </div>
        <el-alert
          v-if="phaseAllFailedTip"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 8px;"
          :title="phaseAllFailedTip"
        />
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
            <p class="field-tip">
              共 {{ httpTraceTotal }} 条（含失败采样与成功明细）；请用筛选查看失败，勿与错误分类中的次数重复相加。
              敏感头/凭证已脱敏展示。
            </p>
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
                  <el-alert
                    v-if="!row.trace_content_full && !(row.request_headers || row.request_body)"
                    type="info"
                    :closable="false"
                    show-icon
                    title="历史记录可能为截断预览；重新以「详细」模式压测后可查看完整请求头/体（单字段上限 32KB）。"
                    style="margin-bottom: 10px;"
                  />
                  <div class="trace-block" v-if="row.method || row.url">
                    <div class="trace-label">请求</div>
                    <div><span class="trace-k">Method</span> {{ row.method || '-' }}</div>
                    <div><span class="trace-k">URL</span> {{ row.url || '-' }}</div>
                  </div>
                  <div class="trace-block" v-if="traceField(row, 'request_headers')">
                    <div class="trace-label">请求头</div>
                    <pre class="trace-pre trace-pre-full">{{ traceField(row, 'request_headers') }}</pre>
                  </div>
                  <div class="trace-block" v-if="traceField(row, 'request_params')">
                    <div class="trace-label">Query 参数</div>
                    <pre class="trace-pre trace-pre-full">{{ traceField(row, 'request_params') }}</pre>
                  </div>
                  <div class="trace-block" v-if="traceField(row, 'request_body')">
                    <div class="trace-label">请求 Body</div>
                    <pre class="trace-pre trace-pre-full">{{ traceField(row, 'request_body') }}</pre>
                  </div>
                  <div class="trace-block" v-if="row.response_headers">
                    <div class="trace-label">响应头</div>
                    <pre class="trace-pre trace-pre-full">{{ row.response_headers }}</pre>
                  </div>
                  <div class="trace-block" v-if="row.thinking_preview">
                    <div class="trace-label">思考过程</div>
                    <pre class="trace-pre trace-pre-full">{{ row.thinking_preview }}</pre>
                  </div>
                  <div class="trace-block" v-if="row.response_body_preview">
                    <div class="trace-label">响应 / 流式内容（解析后的正式回答）</div>
                    <pre class="trace-pre trace-pre-full">{{ row.response_body_preview }}</pre>
                  </div>
                  <div class="trace-block" v-if="row.raw_sse_preview">
                    <div class="trace-label">原始 SSE（截断预览，便于对照规则）</div>
                    <pre class="trace-pre trace-pre-full">{{ row.raw_sse_preview }}</pre>
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
        <PerfAiInlineNote v-if="liveAi?.trend_note" :text="liveAi.trend_note" label="趋势解读" />
        <el-alert
          v-if="hasApproxP95"
          title="秒级 P95 含「多机近似」：多 Worker 同秒取各机 P95 的较大值，非全样本精确分位；汇总卡片中的全程 P95 仍为合并后真分位。"
          type="info"
          show-icon
          :closable="false"
          style="margin-bottom: 12px;"
        />
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

      <!-- 响应时间直方图（区间分布图，与上方「响应时间分布」分位表互补） -->
      <div v-if="rtHistogram.length" class="chart-section">
        <div class="section-header"><h3>📊 响应时间直方图</h3></div>
        <PerfAiInlineNote v-if="liveAi?.distribution_note" :text="liveAi.distribution_note" label="分布解读" />
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
        <div v-if="failedSamplesHint" class="field-tip" style="margin-top: 8px;">
          {{ failedSamplesHint }}
        </div>
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
          <el-table-column prop="name" label="用例名称" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <div>{{ row.name }}</div>
              <div v-if="caseNoteFor(row.name)" class="case-ai-note">{{ caseNoteFor(row.name) }}</div>
            </template>
          </el-table-column>
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
          <el-table-column v-if="showCaseTargetCol" label="目标判定" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="caseTargetStatus(row)" size="small" :type="statusTagType(caseTargetStatus(row))">
                {{ statusLabel(caseTargetStatus(row)) }}
              </el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <PerfAiAnalysisPanel
        v-if="reportData?.id"
        mode="record"
        variant="conclusion"
        :target-id="reportData.id"
        :initial-analysis="liveAi || reportData.ai_analysis"
        style="margin: 16px 0"
        @analysis-updated="onAiUpdated"
      />
      <div style="margin: 16px 0">
        <PerfMetricGlossary />
      </div>
    </template>
  </PageCard>

  <SendReportDialog
    v-model="sendDialogVisible"
    :project-id="sendProjectId"
    :send-fn="doSendReport"
  />
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Download, Message } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import SendReportDialog from '@/components/SendReportDialog.vue'
import PerfAiAnalysisPanel from '@/views/Perf/components/PerfAiAnalysisPanel.vue'
import PerfMetricGlossary from '@/views/Perf/components/PerfMetricGlossary.vue'
import PerfAiInlineNote from '@/views/Perf/components/PerfAiInlineNote.vue'
import { perfRecordApi, perfExecApi, perfSceneApi } from '@/api'
import { resolveDownloadFilename } from '@/utils/downloadFilename'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

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
const proStore = ProjectStore()

const reportData = ref({})
const sendProjectId = computed(
  () => Number(reportData.value?.project_id) || Number(proStore.projectInfo?.id) || Number(route.params.projectId) || 0,
)
const liveAi = ref(null)
const chartRef = ref(null)
const histogramRef = ref(null)
const baselineTrendChartRef = ref(null)
const phaseChartRef = ref(null)
let chartInstance = null
let histogramInstance = null
let baselineTrendChartInstance = null
let phaseChartInstance = null
const phaseHighlightKeys = ref([])
let phaseHighlightSeeded = false
let pollTimer = null
const exporting = ref(false)
const exportingExcel = ref(false)
const sending = ref(false)
const pinningBaseline = ref(false)
const expandedPanels = ref([])
const baselineTrend = ref({ points: [], baseline: null })

const configSummary = computed(() => reportData.value.config_summary || {})
const steppingStages = computed(() => {
  const stages = reportData.value.stepping_stages
  if (Array.isArray(stages) && stages.length) return stages
  const planned = configSummary.value.steps
  return Array.isArray(planned) ? planned : []
})

const caseDrift = computed(() => reportData.value.case_drift || { items: [], has_drift: false })

const executionModeTag = computed(() => {
  const workers = reportData.value.distribution_info?.workers || []
  if (workers.length) return '分布式 Worker'
  if (reportData.value.distribution_info?.is_distributed) return '分布式 Worker'
  return '无 Worker 明细'
})

const caseRtSampleNote = computed(() => configSummary.value.case_rt_sample_note || '')

const METRIC_NOTE_LABELS = {
  qps: 'QPS',
  avg_rt: '平均响应时间',
  p95: 'P95',
  error_rate: '错误率',
  total_requests: '总请求数',
  success_qps: '成功 QPS',
  success_avg_rt: '成功平均响应时间',
  success_p95: '成功 P95',
  p90: 'P90',
  p99: 'P99',
}

const targetEvaluation = computed(() => reportData.value?.target_evaluation || {})
const targetEvalItems = computed(() => {
  const items = targetEvaluation.value.items || []
  return Array.isArray(items) ? items : []
})
const hasPerfTargetsConfigured = computed(() => {
  if (!targetEvaluation.value.enabled) return false
  return targetEvalItems.value.some(
    (it) => it && it.enabled !== false && it.expected != null && it.status !== 'skipped'
  )
})
const targetTrustWarnings = computed(() => {
  const w = targetEvaluation.value.trust_warnings
  return Array.isArray(w) ? w : []
})
const showTargetTrustBox = computed(() => {
  if (!targetEvaluation.value.enabled) return false
  return targetEvaluation.value.trust_level === 'low' || targetTrustWarnings.value.length > 0
})
const overallTargetLabel = computed(() => {
  const map = { pass: '通过', warn: '警告', fail: '失败', unknown: '未判定' }
  return map[targetEvaluation.value.overall_status] || '未判定'
})
const overallTargetTagType = computed(() => statusTagType(targetEvaluation.value.overall_status))

const statusLabel = (st) => ({
  pass: '通过', warn: '警告', fail: '失败', skipped: '跳过', unknown: '未判定'
}[st] || st || '—')

const statusTagType = (st) => ({
  pass: 'success', warn: 'warning', fail: 'danger', skipped: 'info', unknown: 'info'
}[st] || 'info')

const targetItemMap = computed(() => {
  const map = {}
  for (const it of targetEvalItems.value) {
    if (it?.scope === 'global' && it.key) map[it.key] = it
  }
  return map
})

const metricCardClass = (targetKey, fallback) => {
  const it = targetItemMap.value[targetKey]
  if (!it || !hasPerfTargetsConfigured.value || it.status === 'skipped') return fallback
  if (it.status === 'pass') return 'success'
  if (it.status === 'warn') return 'warning'
  if (it.status === 'fail') return 'danger'
  return fallback
}

/** 与导出 HTML target_card_note 对齐：系统判定说明 + AI 解读 */
const buildMetricCardNote = (targetKey, aiNoteKey) => {
  const parts = []
  if (hasPerfTargetsConfigured.value) {
    const it = targetItemMap.value[targetKey]
    if (it && it.status !== 'skipped' && it.message) parts.push(it.message)
  }
  const notes = liveAi.value?.metric_notes
  if (notes && typeof notes === 'object') {
    const aiTxt = notes[aiNoteKey] || notes[targetKey]
    if (aiTxt) parts.push(`AI 解读：${aiTxt}`)
  }
  return parts.join('；')
}

const metricCardNotes = computed(() => ({
  qps: buildMetricCardNote('qps', 'qps'),
  success_qps: buildMetricCardNote('success_qps', 'success_qps'),
  total_requests: buildMetricCardNote('total_requests', 'total_requests'),
  avg_response_time: buildMetricCardNote('avg_response_time', 'avg_rt'),
  success_avg_response_time: buildMetricCardNote('success_avg_response_time', 'success_avg_rt'),
  p95_response_time: buildMetricCardNote('p95_response_time', 'p95'),
  success_p95_response_time: buildMetricCardNote('success_p95_response_time', 'success_p95'),
  error_rate: buildMetricCardNote('error_rate', 'error_rate'),
}))

const formatTargetNum = (v, unit) => {
  if (v == null || v === '') return '—'
  const n = Number(v)
  const s = Number.isFinite(n) ? (Math.abs(n - Math.round(n)) < 1e-9 ? String(Math.round(n)) : String(Math.round(n * 100) / 100)) : String(v)
  return unit ? `${s} ${unit}` : s
}

const caseTargetBest = computed(() => {
  const rank = { fail: 3, warn: 2, unknown: 1, pass: 0, skipped: -1 }
  const best = {}
  for (const it of targetEvalItems.value) {
    if (it?.scope !== 'case' || it.case_id == null) continue
    const key = String(it.case_id)
    const st = it.status || 'unknown'
    if (best[key] == null || (rank[st] || 0) > (rank[best[key]] || 0)) best[key] = st
  }
  return best
})
const showCaseTargetCol = computed(() => Object.keys(caseTargetBest.value).length > 0)
const caseTargetStatus = (row) => {
  const id = row?.case_id ?? row?.id
  if (id == null) return ''
  return caseTargetBest.value[String(id)] || ''
}

const metricNoteRows = computed(() => {
  const notes = liveAi.value?.metric_notes
  if (!notes || typeof notes !== 'object') return []
  return Object.entries(notes)
    .filter(([, v]) => v)
    .map(([k, v]) => ({ key: k, label: METRIC_NOTE_LABELS[k] || k, note: v }))
})
/** 已贴到核心卡片的 AI 解读不再重复条带展示（定义见 successLatency 之后的 cardAiNoteKeys） */
const orphanMetricNoteRows = computed(() =>
  metricNoteRows.value.filter((row) => !cardAiNoteKeys.value.has(row.key))
)

const rtPercentileColumns = [
  { key: 'min', label: 'Min' },
  { key: 'median', label: 'P50' },
  { key: 'avg', label: 'Avg' },
  { key: 'p90', label: 'P90' },
  { key: 'p95', label: 'P95' },
  { key: 'p99', label: 'P99' },
  { key: 'max', label: 'Max' },
]
const rtPercentileRow = computed(() => {
  const d = reportData.value || {}
  return {
    min: d.min_response_time,
    median: d.median_response_time,
    avg: d.avg_response_time,
    p90: d.p90_response_time,
    p95: d.p95_response_time,
    p99: d.p99_response_time,
    max: d.max_response_time,
  }
})
const hasRtPercentiles = computed(() => {
  const row = rtPercentileRow.value
  return Object.values(row).some((v) => v != null && v !== '')
})
const rtBarItems = computed(() => {
  const d = reportData.value || {}
  const items = [
    { label: 'Min', value: d.min_response_time, color: 'green' },
    { label: 'P50/Median', value: d.median_response_time, color: 'blue' },
    { label: 'Avg', value: d.avg_response_time, color: 'orange' },
    { label: 'P90', value: d.p90_response_time, color: 'blue' },
    { label: 'P95', value: d.p95_response_time, color: 'orange' },
    { label: 'Max', value: d.max_response_time, color: 'red' },
  ].filter((it) => it.value != null && Number.isFinite(Number(it.value)))
  const peak = Math.max(...items.map((it) => Number(it.value)), 1)
  return items.map((it) => ({
    ...it,
    widthPct: Math.max(8, Math.min(100, (Number(it.value) / peak) * 100)),
  }))
})
const caseNoteFor = (name) => {
  const list = liveAi.value?.case_notes || []
  const hit = list.find((c) => c?.name === name)
  return hit?.note || ''
}
const onAiUpdated = (ai) => {
  liveAi.value = ai || null
  if (reportData.value) reportData.value.ai_analysis = ai || reportData.value.ai_analysis
}

const distributedWorkers = computed(() => {
  const workers = reportData.value.distribution_info?.workers || configSummary.value.workers || []
  return workers.map(w => ({
    worker_id: w.worker_id,
    host: w.host || '-',
    assigned_concurrent: w.assigned_concurrent ?? '-'
  }))
})

const previousComparison = computed(() => reportData.value.previous_comparison || null)
const baselineComparison = computed(() => reportData.value.baseline_comparison || null)
const successLatency = computed(() => reportData.value.success_latency || {})

/** 已贴到可见核心卡片的 AI 解读不再重复条带展示；无对应卡片的键（如 p90/p99）走 orphan */
const cardAiNoteKeys = computed(() => {
  const keys = new Set(['qps', 'success_qps', 'avg_rt', 'p95', 'error_rate', 'total_requests'])
  if (successLatency.value?.avg_response_time != null) keys.add('success_avg_rt')
  if (successLatency.value?.p95_response_time != null) keys.add('success_p95')
  return keys
})
const isCurrentBaseline = computed(() => !!reportData.value.scene_baseline?.is_current_baseline)
const canPinBaseline = computed(() => {
  const st = reportData.value.status
  return ['success', 'failed', 'stopped'].includes(st) && reportData.value.scene_id
})

const comparisonWarnings = computed(() => {
  const trust = previousComparison.value?.trust
  return Array.isArray(trust?.warnings) ? trust.warnings : []
})

const baselineWarnings = computed(() => {
  const trust = baselineComparison.value?.trust
  return Array.isArray(trust?.warnings) ? trust.warnings : []
})

const baselineAlerts = computed(() => {
  const alerts = baselineComparison.value?.alerts
  return Array.isArray(alerts) ? alerts : []
})

const metricsMetaTip = computed(() => {
  const meta = reportData.value.metrics_meta || {}
  if (!meta || !Object.keys(meta).length) return ''
  const parts = []
  if (meta.effective_duration != null) {
    parts.push(`有效加压时长 ${meta.effective_duration}s（已排除结束收尾）`)
  }
  if (meta.rt_scope === 'steady' && meta.warmup_seconds > 0) {
    parts.push(`延迟指标取稳态（剔除前 ${meta.warmup_seconds}s 热身）`)
  }
  if (meta.ramp_up_applied) {
    parts.push('已应用 Ramp-up 错峰加压')
  }
  return parts.length ? parts.join('；') : ''
})

const mapComparisonRows = (comp) => {
  if (!comp?.changes) return []
  const items = Object.values(comp.changes)
  // HTTP 指标在前，阶段指标在后（保持通用，按 group）
  items.sort((a, b) => {
    const ga = a.group === 'phase' ? 1 : 0
    const gb = b.group === 'phase' ? 1 : 0
    return ga - gb
  })
  return items.map(item => {
    const pct = item.change_pct
    const improved = item.lower_is_better ? pct < 0 : pct > 0
    const worsened = item.lower_is_better ? pct > 0 : pct < 0
    let changeColor = '#909399'
    if (improved) changeColor = '#67c23a'
    if (worsened) changeColor = '#f56c6c'
    const sign = pct > 0 ? '+' : ''
    return {
      label: item.label,
      previous: formatCompareValue(item.label, item.previous, item.unit),
      current: formatCompareValue(item.label, item.current, item.unit),
      changeText: `${sign}${pct}%`,
      changeColor,
      group: item.group || 'http'
    }
  })
}

const comparisonRows = computed(() => mapComparisonRows(previousComparison.value))
const baselineRows = computed(() => mapComparisonRows(baselineComparison.value))

/** 当次压测是否启用了流式（有 stream_profile 或流式阶段模式） */
const isStreamConfiguredRun = computed(() => {
  const mode = reportData.value.mode
  if (['stream_burst', 'sse_burst'].includes(mode)) return true
  return !!(reportData.value.stream_profile?.parser_id)
})

const caseAggregationList = computed(() => {
  const aggs = reportData.value.case_aggregations || {}
  return Object.entries(aggs).map(([id, v]) => ({
    ...(v || {}),
    case_id: (v && v.case_id != null) ? v.case_id : id,
  }))
})

const rtHistogram = computed(() => reportData.value.rt_histogram || [])

const secondaryMetrics = computed(() => {
  const d = reportData.value
  return [
    { label: '成功数', tip: 'HTTP 状态正常且断言全部通过的请求数', value: d.success_count || 0, unit: '' },
    { label: '失败数', tip: 'HTTP 异常或断言未通过的请求数', value: d.fail_count || 0, unit: '' },
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

const failedSamplesHint = computed(() => {
  const bd = reportData.value.error_breakdown || {}
  const n = bd.failed_samples_total || 0
  if (!n) return ''
  return `已采样 ${n} 条失败请求详情，请在上方「HTTP 请求明细」中筛选「失败」查看（主报告不再重复列出，避免误判数量）。`
})

const STREAM_TEXT_COLS = new Set(['问题', '答案预览', '思考过程', '参考文件', '引用文件', '错误信息', '参考资料(全部)', '参考资料(高分)', '完整回答'])
const STREAM_FULL_TEXT_KEYS = new Set(['thinking', 'answer_preview', 'answer', 'references_all', 'references_high', 'reference_files'])

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
  isStreamConfiguredRun.value
  && ((reportData.value.request_details_total || 0) > 0 || streamDetailTotal.value > 0)
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

/** 优先完整字段，兼容历史仅有 *_preview 的记录 */
const traceField = (row, key) => {
  if (!row) return ''
  const full = row[key]
  if (full != null && String(full).length) return full
  const preview = row[`${key}_preview`]
  return preview != null ? preview : ''
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

/** 多 Worker 秒级合并时后端会标 p95_approx，避免误读为精确分位 */
const hasApproxP95 = computed(() => {
  const ts = reportData.value.time_series_data
  return Array.isArray(ts) && ts.some(p => p && p.p95_approx)
})

const phaseSummary = computed(() => reportData.value.phase_metrics || {})
const phaseMetricsRaw = computed(() => {
  const metrics = phaseSummary.value.metrics || []
  return Array.isArray(metrics) ? metrics.filter((m) => m && m.key) : []
})

/** 仅流式压测展示 SSE 阶段区；普通 HTTP 压测即使历史脏数据也不展示 */
const showPhaseMetricsSection = computed(() =>
  isStreamConfiguredRun.value && phaseMetricsRaw.value.length > 0
)

const phaseAllFailedTip = computed(() => {
  if (!showPhaseMetricsSection.value) return ''
  const total = Number(phaseSummary.value.total_requests || 0)
  const fail = Number(phaseSummary.value.fail_count || 0)
  if (total <= 0 || fail < total) return ''
  return '全部请求未通过流式成功判定。若接口返回的是普通 JSON 而非 SSE，请关闭场景「流式问答」后重新保存并执行，将按 HTTP 状态码/断言统计。'
})

const isSustainedStreamRun = computed(() => {
  const mode = reportData.value.mode
  if (['stream_burst', 'sse_burst'].includes(mode)) return false
  if (!['fixed', 'loop', 'stepping', 'journey_fixed', 'journey_loop'].includes(mode)) return false
  if (!isStreamConfiguredRun.value) return false
  return phaseMetricsRaw.value.length > 0
})

const sustainedStreamTip = computed(() => {
  if (!isSustainedStreamRun.value) return ''
  const mode = reportData.value.mode
  const modeHint =
    mode === 'loop' ? '循环次数内反复 SSE'
      : mode === 'stepping' ? '梯度加压过程中持续 SSE'
        : mode?.startsWith('journey') ? '链路步骤中的流式请求'
          : '固定并发持续时间内反复 SSE'
  return `本场为流式持续压测（${modeHint}）。上方 QPS/RT 反映吞吐与整段请求耗时；下方「SSE 阶段指标」为首字等解析阶段（秒）。二者含义不同，请对照阅读，勿把阶段秒数直接当 HTTP 毫秒 RT。`
})

const phaseMetricsRows = computed(() => {
  return phaseMetricsRaw.value.map(m => ({
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

const phaseHighlightSet = computed(() => new Set(phaseHighlightKeys.value || []))
const isPhaseHighlighted = (key) => phaseHighlightSet.value.has(key)

const phaseMetricCardsOrdered = computed(() => {
  const rows = phaseMetricsRaw.value
  const hl = phaseHighlightSet.value
  if (!hl.size) return rows
  const top = []
  const rest = []
  for (const m of rows) {
    if (hl.has(m.key)) top.push(m)
    else rest.push(m)
  }
  return [...top, ...rest]
})

const formatPhaseSec = (val) => {
  if (val === undefined || val === null || val === 'N/A') return '-'
  if (typeof val === 'number') return Number.isInteger(val) ? String(val) : val.toFixed(3)
  const n = Number(val)
  return Number.isFinite(n) ? n.toFixed(3) : String(val)
}

const seedPhaseHighlightFromProfile = () => {
  if (phaseHighlightSeeded) return
  const valid = new Set(phaseMetricsRaw.value.map((m) => m.key))
  if (!valid.size) return
  const fromProfile = reportData.value.stream_profile?.report_highlight_phases || []
  const keys = (Array.isArray(fromProfile) ? fromProfile : [])
    .map((k) => String(k || '').trim())
    .filter((k) => valid.has(k))
  phaseHighlightKeys.value = keys
  phaseHighlightSeeded = true
}

const onPhaseHighlightChange = () => {
  nextTick(() => initPhaseCompareChart())
}

watch(phaseMetricsRaw, () => {
  seedPhaseHighlightFromProfile()
  nextTick(() => initPhaseCompareChart())
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

const formatCompareValue = (label, val, unit) => {
  if (val === undefined || val === null) return '-'
  if (unit === 's') return `${val} s`
  if (unit === 'ms' || (label && label.includes('时间') && !label.includes('(s)'))) return `${val} ms`
  if (unit === '%' || (label && label.includes('率'))) return `${val}%`
  if (label && label.includes('(s)')) return `${val} s`
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
    a.download = resolveDownloadFilename(res, {
      title: reportData.value.scene_name || '性能测试报告',
      fallback: '性能测试报告',
      ext: '.html'
    })
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (err) {
    console.error(err)
    const timedOut = err?.code === 'ECONNABORTED' || /timeout/i.test(String(err?.message || ''))
    ElMessage.error(timedOut ? '报告导出超时，请稍后重试（大报告可能需 1–2 分钟）' : '报告导出失败')
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
    a.download = resolveDownloadFilename(res, {
      title: `${reportData.value.scene_name || '流式阶段报告'}-阶段明细`,
      fallback: '流式阶段报告-阶段明细',
      ext: '.xlsx'
    })
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

const handleSendReport = () => {
  if (reportData.value.status === 'running') {
    ElMessage.warning('压测进行中，请稍后再发送报告')
    return
  }
  sendDialogVisible.value = true
}

const sendDialogVisible = ref(false)
const doSendReport = async (configIds) => {
  sending.value = true
  try {
    return await perfRecordApi.sendReport(recordId, { config_ids: configIds })
  } finally {
    sending.value = false
  }
}

const handlePinBaseline = async () => {
  if (!reportData.value.scene_id || isCurrentBaseline.value) return
  pinningBaseline.value = true
  try {
    await perfSceneApi.pinBaseline(reportData.value.scene_id, {
      record_id: Number(recordId)
    })
    ElMessage.success('已设为场景基线，后续报告将自动对比')
    await loadReport()
  } catch (err) {
    console.error(err)
    ElMessage.error(err?.response?.data?.detail || '钉选基线失败')
  } finally {
    pinningBaseline.value = false
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
    liveAi.value = reportData.value.ai_analysis || null
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
    await loadBaselineTrend()
    nextTick(() => {
      initChart()
      initHistogramChart()
      initBaselineTrendChart()
      seedPhaseHighlightFromProfile()
      initPhaseCompareChart()
    })
  } catch (err) {
    console.error(err)
    ElMessage.error('加载报告失败')
  }
}

const loadBaselineTrend = async () => {
  baselineTrend.value = { points: [], baseline: null }
  const sceneId = reportData.value.scene_id
  const pinned = reportData.value.scene_baseline?.baseline_record_id
  if (!sceneId || !pinned) return
  try {
    const res = await perfSceneApi.getBaselineTrend(sceneId, { limit: 20 })
    const data = res.data || res
    baselineTrend.value = {
      points: data.points || [],
      baseline: data.baseline || null
    }
  } catch (err) {
    console.warn('[PerfReport] baseline-trend unavailable', err)
  }
}

const initBaselineTrendChart = () => {
  if (!baselineTrendChartRef.value) return
  if (baselineTrendChartInstance) {
    baselineTrendChartInstance.dispose()
    baselineTrendChartInstance = null
  }
  const points = baselineTrend.value.points || []
  if (!points.length) return

  const baseline = baselineTrend.value.baseline
  const currentId = Number(reportData.value.id)
  baselineTrendChartInstance = echarts.init(baselineTrendChartRef.value)
  const xData = points.map(p => `#${p.record_id}`)
  const qpsData = points.map(p => p.qps)
  const p95Data = points.map(p => p.p95_response_time)
  const errData = points.map(p => p.error_rate)
  const markPointData = []
  const idx = points.findIndex(p => Number(p.record_id) === currentId)
  if (idx >= 0) {
    markPointData.push({
      name: '本次',
      coord: [idx, qpsData[idx]],
      itemStyle: { color: '#409eff' }
    })
  }

  const markLine = baseline ? {
    silent: true,
    symbol: 'none',
    data: [
      {
        yAxis: baseline.qps,
        lineStyle: { type: 'dashed', color: '#e6a23c' },
        label: { formatter: `基线 QPS ${baseline.qps}`, position: 'insideEndTop' }
      }
    ]
  } : undefined

  baselineTrendChartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['QPS', 'P95(ms)', '错误率(%)'] },
    grid: { left: 48, right: 48, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: xData },
    yAxis: [
      { type: 'value', name: 'QPS / 错误率' },
      { type: 'value', name: 'P95(ms)' }
    ],
    series: [
      {
        name: 'QPS',
        type: 'line',
        data: qpsData,
        markPoint: markPointData.length ? { data: markPointData } : undefined,
        markLine
      },
      { name: 'P95(ms)', type: 'line', yAxisIndex: 1, data: p95Data },
      { name: '错误率(%)', type: 'line', data: errData }
    ]
  })
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
  const avgRtData = timeSeries.map(d => {
    if (!d.qps || d.qps <= 0) return null
    return d.avg_rt != null ? d.avg_rt : null
  })
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
        const idx = params[0].dataIndex
        const point = timeSeries[idx] || {}
        const lines = [axis]
        if (!point.qps || point.qps <= 0) {
          lines.push('<span style="color:#909399">该秒无完成请求</span>')
        }
        params.forEach(p => {
          let val = p.value
          if (val == null || val === '-') {
            lines.push(`${p.marker}${p.seriesName}: —`)
            return
          }
          if (p.seriesName === 'QPS') {
            val = `${val}（该秒瞬时）`
          } else if (String(p.seriesName).includes('P95')) {
            val = `${val} ms`
            if (point?.p95_approx) val += '（多机近似）'
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
        connectNulls: true,
        smooth: true,
        itemStyle: { color: '#5470c6' },
        lineStyle: { width: 2 }
      },
      {
        name: 'P95 RT',
        type: 'line',
        yAxisIndex: 0,
        data: p95RtData,
        connectNulls: true,
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

const initPhaseCompareChart = () => {
  if (!phaseChartRef.value) return
  if (phaseChartInstance) {
    phaseChartInstance.dispose()
    phaseChartInstance = null
  }
  const rows = phaseMetricsRaw.value
  if (!rows.length) return

  const toNum = (v) => {
    if (v === undefined || v === null || v === 'N/A') return null
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }

  phaseChartInstance = echarts.init(phaseChartRef.value)
  const labels = rows.map((m) => m.label || m.key)
  const meanData = rows.map((m) => toNum(m.mean))
  const p95Data = rows.map((m) => toNum(m.p95))
  phaseChartInstance.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['均值(s)', 'P95(s)'], top: 0 },
    grid: { left: 48, right: 24, top: 40, bottom: labels.length > 6 ? 72 : 48 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { interval: 0, rotate: labels.length > 5 ? 28 : 0, fontSize: 11 }
    },
    yAxis: { type: 'value', name: '秒', nameTextStyle: { fontSize: 11 } },
    series: [
      {
        name: '均值(s)',
        type: 'bar',
        data: meanData,
        barMaxWidth: 36,
        itemStyle: { color: '#5470c6' }
      },
      {
        name: 'P95(s)',
        type: 'bar',
        data: p95Data,
        barMaxWidth: 36,
        itemStyle: { color: '#fac858' }
      }
    ]
  })
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
  if (baselineTrendChartInstance) baselineTrendChartInstance.dispose()
  if (phaseChartInstance) phaseChartInstance.dispose()
})

window.addEventListener('resize', () => {
  chartInstance && chartInstance.resize()
  histogramInstance && histogramInstance.resize()
  baselineTrendChartInstance && baselineTrendChartInstance.resize()
  phaseChartInstance && phaseChartInstance.resize()
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

.phase-report-section .section-header {
  margin-bottom: 12px;
}

.phase-metric-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.phase-metric-card {
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 12px 14px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.phase-metric-card.highlight {
  background: #fff8e6;
  border-color: #f5dab1;
  box-shadow: 0 2px 8px rgba(230, 162, 60, 0.15);
}

.phase-metric-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
  font-weight: 600;
}

.phase-metric-values {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.phase-metric-main {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.phase-metric-main .pm-num {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
  line-height: 1.1;
}

.phase-metric-main .pm-unit {
  font-size: 12px;
  color: #909399;
}

.phase-metric-sub {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
}

.phase-compare-chart {
  height: 320px;
  margin-top: 4px;
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.metrics-row.secondary {
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
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

.metric-sys-note {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.4;
  opacity: 0.92;
  text-align: left;
}

.trust-warn-list {
  margin: 4px 0 0;
  padding-left: 18px;
  line-height: 1.5;
}

.rt-distribution-section {
  margin-top: 8px;
}

.rt-unit {
  color: #909399;
  font-size: 12px;
}

.rt-bars {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 2px 8px;
}

.rt-bar-row {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 12px;
  align-items: center;
}

.rt-bar-label {
  font-size: 13px;
  color: #475569;
  text-align: right;
}

.rt-bar-track {
  height: 22px;
  background: #f1f5f9;
  border-radius: 6px;
  overflow: hidden;
}

.rt-bar-fill {
  height: 100%;
  min-width: 48px;
  border-radius: 6px;
  color: #fff;
  font-size: 12px;
  line-height: 22px;
  padding: 0 8px;
  white-space: nowrap;
  box-sizing: border-box;
}

.rt-bar-fill.green { background: linear-gradient(90deg, #22c55e, #16a34a); }
.rt-bar-fill.blue { background: linear-gradient(90deg, #3b82f6, #2563eb); }
.rt-bar-fill.orange { background: linear-gradient(90deg, #f59e0b, #ea580c); }
.rt-bar-fill.red { background: linear-gradient(90deg, #ef4444, #dc2626); }

@media (max-width: 720px) {
  .rt-bar-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
  .rt-bar-label {
    text-align: left;
  }
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

.case-ai-note {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.45;
}
.metric-notes-strip {
  margin: 8px 0 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
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

.baseline-trend-wrap {
  margin-top: 8px;
}

.baseline-trend-chart {
  width: 100%;
  height: 280px;
  margin-top: 8px;
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

.stage-summary-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.stage-summary-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  background: #f8fafc;
  border-left: 3px solid #1a73e8;
}
.stage-sum-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 4px;
}
.stage-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: #1a73e8;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}
.stage-sum-meta {
  font-size: 12.5px;
  color: #64748b;
  line-height: 1.5;
}

.trace-pre.trace-pre-full {
  max-height: min(70vh, 960px);
  overflow: auto;
}

.trace-pre.error-text {
  color: #f56c6c;
}
</style>
