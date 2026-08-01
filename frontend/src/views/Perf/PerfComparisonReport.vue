<template>
  <PageCard>
    <template #title>
      <div class="title-row">
        <span class="title-text">
          {{ report?.title || kindTitle }}
          <el-tag v-if="report" size="small" :type="kindTagType" style="margin-left: 8px">
            {{ kindLabel }}
          </el-tag>
        </span>
        <div class="title-actions">
          <el-button @click="router.push('/perf-comparisons')">返回列表</el-button>
          <el-button type="primary" :loading="exporting" @click="exportHtml">导出 HTML</el-button>
        </div>
      </div>
    </template>
    <template #main>
      <div v-loading="loading" class="report-shell">
        <template v-if="report">
          <div class="report-hero">
            <div class="hero-title">{{ report.title || kindTitle }}</div>
            <div class="hero-meta">
              <span>{{ kindLabel }}</span>
              <span v-if="baselineEnabled">参照轮：{{ refRoundLabel }}</span>
              <span v-else-if="!isMerge">模式：并排（无相对变化率）</span>
              <span>记录 {{ records.length }} 条</span>
              <span v-if="report.create_time">创建 {{ report.create_time }}</span>
            </div>
          </div>

          <el-alert
            v-if="snapshot.note"
            type="info"
            :closable="false"
            show-icon
            :title="snapshot.note"
            class="block-gap"
          />
          <el-alert
            v-for="(msg, idx) in trustWarnings"
            :key="'tw-' + idx"
            :title="msg"
            type="warning"
            :closable="false"
            show-icon
            class="block-gap"
          />

          <!-- 汇总 -->
          <template v-if="isMerge">
            <section class="rpt-section">
              <h3 class="rpt-h2">一、测试概览</h3>
              <PerfAiInlineNote
                v-if="aiOverview"
                :text="aiOverview"
                label="概览"
                :label-map="metricLabelMap"
              />
              <p class="compare-intro">{{ snapshot.note || '各场景分章展示；顶层指标并排，不计算变化率。' }}</p>
              <div v-if="metricNoteStrip.length" class="metric-notes-strip">
                <PerfAiInlineNote
                  v-for="row in metricNoteStrip"
                  :key="'m-' + row.key"
                  :label="row.label"
                  :text="row.note"
                  :metric-key="row.key"
                  :label-map="metricLabelMap"
                  :lower-is-better="row.lowerIsBetter"
                />
              </div>
              <el-table :data="overviewRows" border size="small" class="rpt-table">
                <el-table-column prop="label" label="指标" width="150" fixed />
                <el-table-column
                  v-for="r in records"
                  :key="'o-' + r.id"
                  :label="recLabel(r)"
                  min-width="130"
                  align="right"
                >
                  <template #default="{ row }">
                    {{ formatMetric(row.key, row.values[String(r.id)]) }}
                  </template>
                </el-table-column>
              </el-table>
            </section>

            <section
              v-for="(ch, idx) in chapters"
              :key="'ch-' + ch.record_id"
              class="rpt-section chapter"
            >
              <div class="chapter-head">
                <h3 class="rpt-h2" style="border: none; margin: 0; padding: 0">
                  {{ idx + 1 }}. {{ chLabel(ch) }}
                </h3>
                <el-button link type="primary" @click="router.push(`/perf-report/${ch.record_id}`)">原报告</el-button>
              </div>
              <p class="chapter-meta">场景 {{ ch.scene_name }} · 执行 #{{ ch.record_id }}</p>
              <div class="summary-grid">
                <div class="summary-card">
                  <div class="label">QPS</div>
                  <div class="value" :class="metricTone('qps', ch.qps)">{{ ch.qps ?? '-' }}</div>
                </div>
                <div class="summary-card">
                  <div class="label">平均 RT</div>
                  <div class="value" :class="metricTone('rt', ch.avg_response_time)">
                    {{ ch.avg_response_time ?? '-' }} <small>ms</small>
                  </div>
                </div>
                <div class="summary-card">
                  <div class="label">P95</div>
                  <div class="value" :class="metricTone('p95', ch.p95_response_time)">
                    {{ ch.p95_response_time ?? '-' }} <small>ms</small>
                  </div>
                </div>
                <div class="summary-card">
                  <div class="label">错误率</div>
                  <div class="value" :class="metricTone('error_rate', ch.error_rate)">
                    {{ ch.error_rate ?? '-' }}%
                  </div>
                </div>
                <div class="summary-card">
                  <div class="label">总请求</div>
                  <div class="value tone-neutral">{{ ch.total_requests ?? '-' }}</div>
                </div>
              </div>
              <el-table v-if="(ch.top_cases || []).length" :data="ch.top_cases" border size="small" max-height="240" class="rpt-table">
                <el-table-column prop="name" label="接口" min-width="140" show-overflow-tooltip>
                  <template #default="{ row }">
                    <div>{{ row.name }}</div>
                    <div v-if="caseNoteFor(row.name)" class="case-ai-note">{{ caseNoteFor(row.name) }}</div>
                  </template>
                </el-table-column>
                <el-table-column prop="total" label="请求" width="80" align="right" />
                <el-table-column prop="avg_rt" label="Avg" width="80" align="right">
                  <template #default="{ row }">
                    <span :class="'cell-' + metricTone('rt', row.avg_rt)">{{ row.avg_rt ?? '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="p95_rt" label="P95" width="80" align="right">
                  <template #default="{ row }">
                    <span :class="'cell-' + metricTone('p95', row.p95_rt)">{{ row.p95_rt ?? '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="error_rate" label="错误率%" width="90" align="right">
                  <template #default="{ row }">
                    <span :class="errClass(row.error_rate)">{{ row.error_rate ?? '-' }}</span>
                  </template>
                </el-table-column>
              </el-table>
              <PerfRecordTrendCharts v-bind="recordChartsProps(ch)" />
            </section>
          </template>

          <!-- 对比 / hybrid：差异与对照表前置，各轮详细画像后置 -->
          <template v-else>
            <section class="rpt-section">
              <h3 class="rpt-h2">一、测试概览</h3>
              <PerfAiInlineNote v-if="aiOverview" :text="aiOverview" label="概览" :label-map="metricLabelMap" />
              <p class="compare-intro">
                流式阶段压测无固定时长配置时，实际时长随最慢请求结束。
                <span style="color:#15803d;font-weight:600">绿色偏好转</span>，
                <span style="color:#b91c1c;font-weight:600">红色偏变差</span>。
              </p>
              <div class="overview-grid">
                <div
                  v-for="r in records"
                  :key="'ov-' + r.id"
                  class="overview-panel"
                  :class="baselineEnabled ? (r.id === referenceId ? 'is-ref' : 'is-cmp') : ''"
                >
                  <div class="panel-title">
                    <el-tag size="small" :type="baselineEnabled && r.id === referenceId ? 'warning' : 'info'">
                      {{ roundRole(r) }}
                    </el-tag>
                    <strong>{{ recLabel(r) }}</strong>
                    <span class="muted">#{{ r.id }} · {{ shortTime(r.started_at) || r.scene_name }}</span>
                  </div>
                  <table class="kv-table">
                    <tr>
                      <td>并发用户</td>
                      <td>
                        <div v-if="isSteppingRecord(r)" class="steps-stack">
                          <div class="steps-head">{{ concurrentPeakText(r) }}</div>
                          <div
                            v-for="(s, i) in steppingStepsOf(r)"
                            :key="'cu-' + r.id + '-' + i"
                            class="step-line"
                          >
                            第 {{ i + 1 }} 阶段 · {{ s.users }}用户<span v-if="s.duration != null"> × {{ s.duration }}s</span>
                          </div>
                        </div>
                        <template v-else>{{ concurrentConfigText(r) }}</template>
                      </td>
                    </tr>
                    <tr><td>模式</td><td>{{ modeLabel(r.config_snapshot?.mode) }}</td></tr>
                    <tr>
                      <td>
                        Ramp-up
                        <el-tooltip placement="top" content="从 0 到目标并发的爬升时间；0 表示立即达到目标并发。">
                          <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                        </el-tooltip>
                      </td>
                      <td>{{ r.config_snapshot?.ramp_up_seconds ?? 0 }}s</td>
                    </tr>
                    <tr v-if="showDurationConfig(r)">
                      <td>时长配置</td>
                      <td>
                        <div v-if="isSteppingRecord(r)" class="steps-stack">
                          <div class="steps-head">{{ steppingStepsOf(r).length }} 个阶段</div>
                          <div
                            v-for="(s, i) in steppingStepsOf(r)"
                            :key="'du-' + r.id + '-' + i"
                            class="step-line"
                          >
                            第 {{ i + 1 }} 阶段 · {{ s.users }}用户<span v-if="s.duration != null"> × {{ s.duration }}s</span>
                          </div>
                        </div>
                        <template v-else>{{ durationConfigText(r) }}</template>
                      </td>
                    </tr>
                    <tr>
                      <td>
                        预热
                        <el-tooltip placement="top" content="统计 Avg/P95 时剔除开始一段时间的样本，降低冷启动噪声；未配置时通常跟随 Ramp-up。">
                          <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                        </el-tooltip>
                      </td>
                      <td>{{ r.config_snapshot?.warmup_seconds ?? 0 }}s</td>
                    </tr>
                    <tr>
                      <td>实际时长</td>
                      <td>
                        <span :class="overviewMetricClass(r, 'duration')">{{ r.duration ?? '-' }}s</span>
                      </td>
                    </tr>
                    <tr><td>开始时间</td><td>{{ r.started_at || '-' }}</td></tr>
                    <tr><td>请求/成功/失败</td><td>{{ r.total_requests ?? '-' }} / {{ r.success_count ?? '-' }} / {{ r.fail_count ?? '-' }}</td></tr>
                    <tr>
                      <td>Avg / P95</td>
                      <td>
                        <span :class="overviewMetricClass(r, 'avg')">{{ r.avg_response_time ?? '-' }}</span>
                        /
                        <span :class="overviewMetricClass(r, 'p95')">{{ r.p95_response_time ?? '-' }}</span>
                        ms
                      </td>
                    </tr>
                  </table>
                </div>
              </div>
            </section>

            <section v-if="deltaBlocks.length" class="rpt-section">
              <h3 class="rpt-h2">二、差异速览</h3>
              <p class="compare-intro">
                相对参照轮的关键变化一览。
              </p>
              <div v-for="block in deltaBlocks" :key="'delta-' + block.otherId" class="delta-block">
                <div class="delta-head">
                  <el-tag size="small" type="info">对比轮</el-tag>
                  <strong>{{ block.otherLabel }}</strong>
                  <span class="muted">相对</span>
                  <el-tag size="small" type="warning">参照轮</el-tag>
                  <strong>{{ block.refLabel }}</strong>
                </div>
                <div class="delta-grid">
                  <div
                    v-for="card in block.cards"
                    :key="card.key"
                    class="delta-card"
                    :class="card.tone"
                  >
                    <div class="delta-label">{{ card.label }}</div>
                    <div class="delta-pct" :class="card.tone">{{ card.pctText }}</div>
                    <div class="delta-vals">参照 {{ card.baseText }} → 本轮 {{ card.curText }}</div>
                  </div>
                </div>
              </div>
            </section>

            <section class="rpt-section">
              <h3 class="rpt-h2">
                {{ isHybrid ? (baselineEnabled ? '指标对照' : '指标并排') : '核心指标对比' }}
                <span v-if="baselineEnabled" style="font-weight:400;font-size:13px;color:#64748b">（相对参照轮）</span>
              </h3>
              <p v-if="baselineEnabled" class="compare-intro">
                百分比相对参照轮：{{ refRoundLabel }}。
                <span style="color:#15803d;font-weight:600">绿色偏好转</span>，
                <span style="color:#b91c1c;font-weight:600">红色偏变差</span>。
              </p>
              <div v-if="metricNoteStrip.length" class="metric-notes-strip">
                <PerfAiInlineNote
                  v-for="row in metricNoteStrip"
                  :key="row.key"
                  :label="row.label"
                  :text="row.note"
                  :metric-key="row.key"
                  :label-map="metricLabelMap"
                  :lower-is-better="row.lowerIsBetter"
                />
              </div>
              <el-table :data="metricRows" border size="small" class="rpt-table">
                <el-table-column prop="label" label="指标" width="150" fixed />
                <el-table-column
                  v-for="r in records"
                  :key="'m-' + r.id"
                  :label="roundHeading(r)"
                  min-width="140"
                  align="right"
                >
                  <template #default="{ row }">
                    <div>{{ formatMetric(row.key, row.values[String(r.id)]) }}</div>
                    <div
                      v-if="baselineEnabled && r.id !== referenceId"
                      class="pct"
                      :class="pctClass(row.key, row.change_pct[String(r.id)], row.lower_is_better)"
                    >
                      {{ formatPct(row.change_pct[String(r.id)]) }}
                    </div>
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="baselineEnabled || hasMetricNotes"
                  label="解读"
                  min-width="160"
                >
                  <template #default="{ row }">
                    <span
                      class="metric-note"
                      v-html="metricNoteHtml(row.key) || '—'"
                    />
                  </template>
                </el-table-column>
              </el-table>
            </section>

            <section v-if="steppingStageBlocks.length" class="rpt-section">
              <h3 class="rpt-h2">
                梯度阶段对照
                <span v-if="baselineEnabled" style="font-weight:400;font-size:13px;color:#64748b">（相对参照轮）</span>
              </h3>
              <p v-if="steppingStageNote" class="compare-intro">{{ steppingStageNote }}</p>
              <div class="stage-summary-block">
                <div class="stage-summary-label">分阶段对照摘要</div>
                <div class="stage-summary-list">
                  <div
                    v-for="stage in steppingStageBlocks"
                    :key="'sum-' + stage.stage"
                    class="stage-summary-card"
                    :class="stageCardTone(stage)"
                  >
                    <div class="stage-sum-title">
                      <span class="stage-idx">{{ stage.stage }}</span>
                      <span>{{ stage.label }}</span>
                    </div>
                    <div
                      v-for="r in records"
                      :key="'sum-line-' + stage.stage + '-' + r.id"
                      class="stage-sum-line"
                    >
                      <el-tag
                        size="small"
                        :type="baselineEnabled && r.id === referenceId ? 'warning' : 'info'"
                      >
                        {{ roundRole(r) }}
                      </el-tag>
                      <span class="stage-sum-meta">{{ stageRoundMeta(stage, r) }}</span>
                    </div>
                    <div
                      v-if="baselineEnabled && stageDeltaChips(stage).length"
                      class="stage-sum-deltas"
                    >
                      <span
                        v-for="(chip, ci) in stageDeltaChips(stage)"
                        :key="'chip-' + stage.stage + '-' + ci"
                        class="delta-chip"
                        :style="{ color: chip.color }"
                      >
                        {{ chip.text }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <p v-if="baselineEnabled" class="compare-intro">
                百分比相对参照轮：{{ refRoundLabel }}。
                <span style="color:#15803d;font-weight:600">绿色偏好转</span>，
                <span style="color:#b91c1c;font-weight:600">红色偏变差</span>。
              </p>
              <div
                v-for="stage in steppingStageBlocks"
                :key="'stg-' + stage.stage"
                class="stage-cmp-block"
              >
                <div class="stage-detail-head" :class="stageCardTone(stage)">
                  <span class="stage-idx">{{ stage.stage }}</span>
                  <h4 class="stage-cmp-title">{{ stage.label }}</h4>
                </div>
                <el-table :data="stage.metrics || []" border size="small" class="rpt-table">
                  <el-table-column prop="label" label="指标" width="140" fixed />
                  <el-table-column
                    v-for="r in records"
                    :key="'stg-m-' + stage.stage + '-' + r.id"
                    :label="roundHeading(r)"
                    min-width="140"
                    align="right"
                    :class-name="baselineEnabled && r.id === referenceId ? 'col-ref' : 'col-cmp'"
                    :header-class-name="baselineEnabled && r.id === referenceId ? 'col-ref' : 'col-cmp'"
                  >
                    <template #default="{ row }">
                      <div>{{ formatStageMetric(row.key, row.values[String(r.id)]) }}</div>
                      <div
                        v-if="baselineEnabled && r.id !== referenceId"
                        class="pct"
                        :class="pctClass(row.key, row.change_pct?.[String(r.id)], row.lower_is_better)"
                      >
                        {{ formatPct(row.change_pct?.[String(r.id)]) }}
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </section>

            <section v-if="baselineEnabled && caseRows.length" class="rpt-section">
              <h3 class="rpt-h2">{{ isHybrid ? '用例维度对照' : '用例维度对比' }}</h3>
              <el-alert
                v-if="caseHint"
                :type="caseCommonCount === 0 ? 'warning' : 'info'"
                :closable="false"
                show-icon
                :title="caseHint"
                class="block-gap"
              />
              <el-table :data="caseRows" border size="small" max-height="480" class="rpt-table case-cmp-table">
                <el-table-column label="接口" min-width="160" fixed show-overflow-tooltip>
                  <template #default="{ row }">
                    <div class="case-name">
                      {{ row.name || '未命名' }}
                      <el-tag v-if="row.coverage === 'common'" size="small" type="primary" effect="plain">共有</el-tag>
                      <el-tag v-else-if="row.coverage === 'partial'" size="small" type="warning" effect="plain">独有</el-tag>
                    </div>
                    <div v-if="caseNoteFor(row.name)" class="case-note">{{ caseNoteFor(row.name) }}</div>
                  </template>
                </el-table-column>
                <el-table-column
                  v-for="(r, gi) in records"
                  :key="'c-' + r.id"
                  :label="roundHeading(r)"
                  min-width="188"
                  :class-name="caseColClass(r, gi)"
                  :header-class-name="caseColClass(r, gi)"
                >
                  <template #header>
                    <div class="case-col-head">
                      <el-tag size="small" :type="Number(r.id) === Number(referenceId) ? 'warning' : 'info'">
                        {{ roundRole(r) }}
                      </el-tag>
                      <div class="case-col-sub">{{ roundHeading(r) }}</div>
                    </div>
                  </template>
                  <template #default="{ row }">
                    <div v-if="!casePresent(row, r.id)" class="missing-cell">本轮无此接口</div>
                    <div v-else class="case-metrics">
                      <div>
                        Avg {{ cellOf(row, r.id)?.avg_rt ?? '-' }}
                        <span
                          v-if="r.id !== referenceId && casePct(row, r.id) != null"
                          class="pct inline"
                          :class="pctClass('avg_response_time', casePct(row, r.id), true)"
                        >{{ formatPct(casePct(row, r.id)) }}</span>
                      </div>
                      <div>P95 {{ cellOf(row, r.id)?.p95_rt ?? '-' }}</div>
                      <div>
                        错误率
                        <span :class="errClass(cellOf(row, r.id)?.error_rate)">
                          {{ fmtErr(cellOf(row, r.id)?.error_rate) }}
                        </span>
                      </div>
                      <div>次数 {{ cellOf(row, r.id)?.total ?? '-' }}</div>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </section>
            <el-alert
              v-else-if="isHybrid && !baselineEnabled"
              type="info"
              :closable="false"
              show-icon
              class="block-gap"
              title="跨场景未计算变化率；用例见下方分章，指标仅并排观察。"
            />
            <el-alert
              v-else-if="baselineEnabled && !caseRows.length && isHybrid"
              type="info"
              :closable="false"
              show-icon
              class="block-gap"
              title="无同名接口可对齐，已省略用例对照；明细见下方分章。"
            />

            <template v-if="detailChapters.length">
              <section
                v-for="(ch, idx) in detailChapters"
                :key="'hch-' + ch.record_id"
                class="rpt-section chapter"
              >
                <div class="chapter-head">
                  <h3 class="rpt-h2" style="border: none; margin: 0; padding: 0">
                    各轮画像 {{ idx + 1 }} · {{ chLabel(ch) }}
                  </h3>
                  <el-button link type="primary" @click="router.push(`/perf-report/${ch.record_id}`)">原报告</el-button>
                </div>
                <p class="chapter-meta">
                  场景 {{ ch.scene_name }} · 执行 #{{ ch.record_id }}
                  <span v-if="chapterConcurrentText(ch)"> · {{ chapterConcurrentText(ch) }}</span>
                  <span v-if="ch.duration != null"> · 时长 {{ ch.duration }}s</span>
                </p>
                <div class="summary-grid">
                  <div class="summary-card">
                    <div class="label">QPS</div>
                    <div class="value" :class="metricTone('qps', ch.qps)">{{ ch.qps ?? '-' }}</div>
                  </div>
                  <div class="summary-card">
                    <div class="label">平均 RT</div>
                    <div class="value" :class="metricTone('rt', ch.avg_response_time)">
                      {{ ch.avg_response_time ?? '-' }} <small>ms</small>
                    </div>
                  </div>
                  <div class="summary-card">
                    <div class="label">P95</div>
                    <div class="value" :class="metricTone('p95', ch.p95_response_time)">
                      {{ ch.p95_response_time ?? '-' }} <small>ms</small>
                    </div>
                  </div>
                  <div class="summary-card">
                    <div class="label">错误率</div>
                    <div class="value" :class="metricTone('error_rate', ch.error_rate)">
                      {{ ch.error_rate ?? '-' }}%
                    </div>
                  </div>
                  <div class="summary-card">
                    <div class="label">总请求</div>
                    <div class="value tone-neutral">{{ ch.total_requests ?? '-' }}</div>
                  </div>
                </div>
                <el-table v-if="(ch.top_cases || []).length" :data="ch.top_cases" border size="small" max-height="220" class="rpt-table">
                  <el-table-column prop="name" label="接口" min-width="140" show-overflow-tooltip>
                    <template #default="{ row }">
                      <div>{{ row.name }}</div>
                      <div v-if="caseNoteFor(row.name)" class="case-ai-note">{{ caseNoteFor(row.name) }}</div>
                    </template>
                  </el-table-column>
                  <el-table-column prop="total" label="请求" width="80" align="right" />
                  <el-table-column prop="avg_rt" label="Avg" width="80" align="right">
                    <template #default="{ row }">
                      <span :class="'cell-' + metricTone('rt', row.avg_rt)">{{ row.avg_rt ?? '-' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="p95_rt" label="P95" width="80" align="right">
                    <template #default="{ row }">
                      <span :class="'cell-' + metricTone('p95', row.p95_rt)">{{ row.p95_rt ?? '-' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="error_rate" label="错误率%" width="90" align="right">
                    <template #default="{ row }">
                      <span :class="errClass(row.error_rate)">{{ row.error_rate ?? '-' }}</span>
                    </template>
                  </el-table-column>
                </el-table>
                <PerfRecordTrendCharts v-bind="recordChartsProps(ch)" />
              </section>
            </template>

            <section v-if="!detailChapters.length && !isHybrid" class="rpt-section">
              <h3 class="rpt-h2">各轮趋势与分布</h3>
              <div v-for="r in records" :key="'chart-' + r.id" class="record-chart-wrap">
                <div class="panel-title" style="margin-bottom: 8px">
                  <strong>{{ recLabel(r) }}</strong>
                  <span class="muted">#{{ r.id }}</span>
                </div>
                <PerfRecordTrendCharts v-bind="recordChartsProps(r)" />
              </div>
            </section>

            <section v-if="records.length >= 2" class="rpt-section">
              <PerfCompareOverlayCharts :records="records" />
            </section>
          </template>

          <section class="rpt-section">
            <PerfAiAnalysisPanel
              v-if="report?.id"
              mode="comparison"
              variant="conclusion"
              :target-id="report.id"
              :initial-analysis="liveAi || report.ai_analysis"
              :label-map="metricLabelMap"
              @analysis-updated="onAiUpdated"
            />
          </section>

          <section class="rpt-section">
            <PerfMetricGlossary />
          </section>
        </template>
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import PageCard from '@/components/PageCard.vue'
import PerfAiAnalysisPanel from '@/views/Perf/components/PerfAiAnalysisPanel.vue'
import PerfAiInlineNote from '@/views/Perf/components/PerfAiInlineNote.vue'
import PerfMetricGlossary from '@/views/Perf/components/PerfMetricGlossary.vue'
import PerfRecordTrendCharts from '@/views/Perf/components/PerfRecordTrendCharts.vue'
import PerfCompareOverlayCharts from '@/views/Perf/components/PerfCompareOverlayCharts.vue'
import {
  buildMetricLabelMap,
  colorizePctPhrases,
  humanizeMetricKey,
  metricLowerIsBetter,
  pctClass,
  pctColor as semanticPctColor,
  pctTone as semanticPctTone,
} from '@/views/Perf/perfMetricSemantics.js'
import { perfComparisonApi } from '@/api'
import { resolveDownloadFilename } from '@/utils/downloadFilename'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const exporting = ref(false)
const report = ref(null)
const liveAi = ref(null)

const snapshot = computed(() => report.value?.snapshot || {})
const reportKind = computed(() => report.value?.kind || snapshot.value.kind || 'compare')
const isMerge = computed(() => reportKind.value === 'merge')
const isHybrid = computed(() => reportKind.value === 'hybrid')
const kindTitle = computed(() => {
  if (isMerge.value) return '汇总报告'
  if (isHybrid.value) return '合并+对比报告'
  return '对比报告'
})
const kindLabel = computed(() => {
  if (isMerge.value) return '汇总'
  if (isHybrid.value) return '合并+对比'
  return '对比'
})
const kindTagType = computed(() => {
  if (isMerge.value) return 'success'
  if (isHybrid.value) return 'primary'
  return 'warning'
})
const records = computed(() => snapshot.value.records || [])
const baselineEnabled = computed(() => {
  if (isMerge.value) return false
  if (snapshot.value.baseline_enabled === false) return false
  if (snapshot.value.baseline_enabled === true) return true
  // 旧快照：对比默认有基准；hybrid 跨场景视为无
  if (isHybrid.value) {
    const ids = new Set(records.value.map((r) => r.scene_id).filter((x) => x != null))
    return ids.size <= 1
  }
  return true
})
const chapters = computed(() => snapshot.value.chapters || [])
/** 纯对比无 chapters 时，从 records 合成各轮画像（与导出 HTML 一致） */
const detailChapters = computed(() => {
  if (chapters.value.length) return chapters.value
  if (isMerge.value) return []
  return (records.value || []).map((r) => {
    const ag = r.case_aggregations || {}
    const top = Object.entries(ag)
      .filter(([, info]) => info && typeof info === 'object')
      .map(([cid, info]) => ({
        name: info.name || `接口-${cid}`,
        total: info.total || 0,
        fail: info.fail || 0,
        avg_rt: info.avg_rt,
        p95_rt: info.p95_rt,
        error_rate: info.error_rate
      }))
      .sort((a, b) => (b.error_rate || 0) - (a.error_rate || 0) || (b.p95_rt || 0) - (a.p95_rt || 0))
      .slice(0, 8)
    const cfg = r.config_snapshot || {}
    return {
      record_id: r.id,
      display_name: r.display_name,
      scene_name: r.scene_name,
      duration: r.duration,
      qps: r.qps,
      avg_response_time: r.avg_response_time,
      p95_response_time: r.p95_response_time,
      error_rate: r.error_rate,
      total_requests: r.total_requests,
      config: {
        concurrent_users: cfg.concurrent_users,
        mode: cfg.mode,
        duration_seconds: cfg.duration_seconds
      },
      top_cases: top
    }
  })
})
const overviewRows = computed(() => snapshot.value.overview_table || [])
const referenceId = computed(() => snapshot.value.reference_record_id)
const metricRows = computed(() => snapshot.value.metric_compare || [])
const steppingStageBlocks = computed(() => {
  const block = snapshot.value.stepping_stage_compare
  if (!block || typeof block !== 'object') return []
  return Array.isArray(block.stages) ? block.stages : []
})
const steppingStageNote = computed(() => {
  const block = snapshot.value.stepping_stage_compare
  return (block && block.note) || ''
})
const stageMetricMap = (stage) => {
  const out = {}
  for (const m of stage?.metrics || []) {
    if (m?.key) out[m.key] = m
  }
  return out
}
const stageRoundMeta = (stage, r) => {
  const by = stageMetricMap(stage)
  const rid = String(r.id)
  const bits = []
  const u = by.users?.values?.[rid]
  const d = by.completed_seconds?.values?.[rid]
  const q = by.avg_qps?.values?.[rid]
  const t = by.avg_rt?.values?.[rid]
  if (u != null) bits.push(`${u}并发`)
  if (d != null) bits.push(`有完成 ${d}s`)
  if (q != null) bits.push(`QPS ${q}`)
  if (t != null) {
    const sec = Math.round((Number(t) / 1000) * 10) / 10
    bits.push(`RT ${t}ms（约 ${sec}s）`)
  } else if (d === 0) {
    bits.push('无完成样本')
  }
  return bits.length ? bits.join(' · ') : '—'
}
const stageCardTone = (stage) => {
  if (!baselineEnabled.value) return 'flat'
  const by = stageMetricMap(stage)
  const tones = []
  for (const r of records.value) {
    if (Number(r.id) === Number(referenceId.value)) continue
    const rid = String(r.id)
    const qPct = by.avg_qps?.change_pct?.[rid]
    const tPct = by.avg_rt?.change_pct?.[rid]
    if (qPct != null) tones.push(pctTone('avg_qps', qPct, false))
    if (tPct != null) tones.push(pctTone('avg_rt', tPct, true))
  }
  if (tones.some((t) => t === 'worse')) return 'worse'
  if (tones.length && tones.every((t) => t === 'better')) return 'better'
  return 'flat'
}
const stageDeltaChips = (stage) => {
  if (!baselineEnabled.value) return []
  const by = stageMetricMap(stage)
  const chips = []
  for (const r of records.value) {
    if (Number(r.id) === Number(referenceId.value)) continue
    const rid = String(r.id)
    const qPct = by.avg_qps?.change_pct?.[rid]
    const tPct = by.avg_rt?.change_pct?.[rid]
    if (qPct != null) {
      chips.push({
        text: `QPS ${formatPct(qPct)}`,
        color: stagePctColor({ lower_is_better: false, key: 'avg_qps' }, qPct)
      })
    }
    if (tPct != null) {
      chips.push({
        text: `RT ${formatPct(tPct)}`,
        color: stagePctColor({ lower_is_better: true, key: 'avg_rt' }, tPct)
      })
    }
  }
  return chips
}
const isSteppingRecord = (r) => (r?.config_snapshot?.mode || '') === 'stepping'
const steppingStepsOf = (r) => {
  const steps = r?.config_snapshot?.steps
  if (!Array.isArray(steps)) return []
  return steps.filter((s) => s && s.users != null)
}
const concurrentPeakText = (r) => {
  const steps = steppingStepsOf(r)
  const peak = steps.reduce((m, s) => Math.max(m, Number(s?.users) || 0), 0)
  return peak > 0 ? `峰值 ${peak}` : '梯度并发'
}
const caseRows = computed(() => (snapshot.value.case_compare || []).slice(0, 40))
const caseCommonCount = computed(() => {
  if (snapshot.value.case_common_count != null) return Number(snapshot.value.case_common_count)
  if (!caseRows.value.length) return 0
  return caseRows.value.filter((c) => {
    if (c.coverage === 'common') return true
    if (c.coverage === 'partial') return false
    // 旧快照：两侧都有数据才算共有
    return records.value.every((r) => casePresent(c, r.id))
  }).length
})
const caseHint = computed(() => {
  if (!caseRows.value.length) return ''
  const common = caseCommonCount.value
  if (common === 0) {
    return '各轮接口名无交集：下列为独有接口，缺侧显示「本轮无」。'
  }
  if (common < caseRows.value.length) {
    return `按接口名对齐：共有 ${common} 个；其余为某轮独有。`
  }
  return '各轮共有接口；Avg 旁百分比为相对参照轮变化。'
})

const aiAnalysis = computed(() => liveAi.value || report.value?.ai_analysis || {})
const aiOverview = computed(() => aiAnalysis.value.overview || '')
const hasMetricNotes = computed(() => {
  const n = aiAnalysis.value.metric_notes
  return n && typeof n === 'object' && Object.keys(n).length > 0
})
const metricLabelMap = computed(() => buildMetricLabelMap(metricRows.value))
const metricNoteStrip = computed(() => {
  const notes = aiAnalysis.value.metric_notes
  if (!notes || typeof notes !== 'object') return []
  const byKey = Object.fromEntries((metricRows.value || []).map((m) => [m.key, m]))
  const aliasToRow = {
    avg_rt: 'avg_response_time',
    p95: 'p95_response_time',
  }
  return Object.entries(notes)
    .filter(([, v]) => v)
    .map(([k, v]) => {
      const rowKey = byKey[k] ? k : aliasToRow[k] || k
      const row = byKey[rowKey] || byKey[k] || {}
      const lib =
        row.lower_is_better != null ? row.lower_is_better : metricLowerIsBetter(rowKey || k)
      return {
        key: k,
        label: row.label || humanizeMetricKey(k, metricLabelMap.value),
        note: v,
        lowerIsBetter: lib,
      }
    })
})
const onAiUpdated = (ai) => {
  liveAi.value = ai || null
  if (report.value) report.value.ai_analysis = ai || report.value.ai_analysis
}

const recLabel = (r) => r?.display_name || r?.scene_name || `#${r?.id}`
const chLabel = (c) => c?.display_name || c?.scene_name || `#${c?.record_id}`
const shortTime = (ts) => {
  const s = String(ts || '').trim()
  if (!s) return ''
  if (s.includes(' ') && s.includes(':')) return s.split(' ')[1].slice(0, 5)
  return s.slice(0, 16)
}
const MODE_LABELS = {
  fixed: '固定模式',
  loop: '循环模式',
  stepping: '梯度模式',
  stream_burst: '流式阶段压测',
  sse_burst: '流式阶段压测',
  journey_fixed: '链路固定模式',
  journey_loop: '链路循环模式',
}
const modeLabel = (mode) => MODE_LABELS[mode] || mode || '-'
const concurrentConfigText = (r) => {
  const cfg = r?.config_snapshot || {}
  if (cfg.mode === 'stepping') {
    const steps = Array.isArray(cfg.steps) ? cfg.steps : []
    const peak = steps.reduce((m, s) => Math.max(m, Number(s?.users) || 0), 0)
    const summary = steps
      .map((s) => {
        const u = s?.users
        const d = s?.duration
        if (u == null) return null
        return d != null ? `${u}用户×${d}s` : `${u}用户`
      })
      .filter(Boolean)
      .join(' → ')
    if (peak > 0 && summary) return `峰值 ${peak}（${summary}）`
    if (peak > 0) return `峰值 ${peak}`
  }
  return cfg.concurrent_users ?? '-'
}
const chapterConcurrentText = (ch) => {
  const cfg = ch?.config || {}
  if (cfg.mode === 'stepping') {
    const steps = Array.isArray(cfg.steps) ? cfg.steps : []
    const peak = steps.reduce((m, s) => Math.max(m, Number(s?.users) || 0), 0)
    const summary = steps
      .map((s) => (s?.users != null ? (s.duration != null ? `${s.users}用户×${s.duration}s` : `${s.users}用户`) : null))
      .filter(Boolean)
      .join(' → ')
    if (peak > 0 && summary) return `峰值并发 ${peak}（${summary}）`
    if (peak > 0) return `峰值并发 ${peak}`
  }
  if (cfg.concurrent_users != null) return `并发 ${cfg.concurrent_users}`
  return ''
}
const showDurationConfig = (r) => {
  const mode = r?.config_snapshot?.mode
  return !['stream_burst', 'sse_burst'].includes(mode)
}
const durationConfigText = (r) => {
  const cfg = r?.config_snapshot || {}
  const mode = cfg.mode
  if (mode === 'fixed' || mode === 'journey_fixed') {
    return cfg.duration_seconds != null ? `${cfg.duration_seconds}s` : '-'
  }
  if (mode === 'loop' || mode === 'journey_loop') {
    return cfg.loop_count != null ? `${cfg.loop_count} 次/用户` : '-'
  }
  if (mode === 'stepping') {
    const n = (cfg.steps || []).length
    const bits = (cfg.steps || [])
      .map((s) => (s?.users != null ? (s.duration != null ? `${s.users}用户×${s.duration}s` : `${s.users}用户`) : null))
      .filter(Boolean)
    return bits.length ? `${n} 个阶段（${bits.join(' → ')}）` : `${n} 个阶段`
  }
  return cfg.duration_seconds != null ? `${cfg.duration_seconds}s` : '-'
}
const refRecord = computed(() => {
  if (!baselineEnabled.value) return null
  return records.value.find((x) => Number(x.id) === Number(referenceId.value)) || null
})
/** 对比轮相对参照：RT/时长越小越好 → 更短绿、更长红 */
const overviewMetricClass = (r, kind) => {
  if (!baselineEnabled.value || !refRecord.value) return ''
  if (Number(r.id) === Number(referenceId.value)) return 'ov-ref'
  const cur = kind === 'duration'
    ? Number(r.duration)
    : kind === 'avg'
      ? Number(r.avg_response_time)
      : Number(r.p95_response_time)
  const base = kind === 'duration'
    ? Number(refRecord.value.duration)
    : kind === 'avg'
      ? Number(refRecord.value.avg_response_time)
      : Number(refRecord.value.p95_response_time)
  if (!Number.isFinite(cur) || !Number.isFinite(base) || base === 0) return ''
  const pct = ((cur - base) / Math.abs(base)) * 100
  if (Math.abs(pct) < 3) return 'ov-flat'
  return pct < 0 ? 'ov-better' : 'ov-worse'
}
const roundRole = (r) => {
  if (!baselineEnabled.value) return '本轮'
  return Number(r?.id) === Number(referenceId.value) ? '参照轮' : '对比轮'
}
const roundHeading = (r) => {
  const bits = [roundRole(r), `#${r?.id}`]
  const t = shortTime(r?.started_at)
  if (t) bits.push(t)
  bits.push(recLabel(r))
  return bits.join(' · ')
}
const caseColClass = (r, gi) => {
  const base = Number(r?.id) === Number(referenceId.value) ? 'case-col-ref' : 'case-col-cmp'
  return gi > 0 ? `${base} case-col-start` : base
}
const refLabel = computed(() => {
  const r = records.value.find((x) => x.id === referenceId.value)
  return r ? recLabel(r) : `#${referenceId.value}`
})
const refRoundLabel = computed(() => {
  const r = records.value.find((x) => x.id === referenceId.value)
  return r ? roundHeading(r) : `#${referenceId.value}`
})
const DELTA_FOCUS_BASE = [
  { key: 'qps', label: 'QPS', unit: '/s' },
  { key: 'avg_response_time', label: '平均 RT', unit: 'ms' },
  { key: 'p95_response_time', label: 'P95', unit: 'ms' },
  { key: 'error_rate', label: '错误率', unit: '%' },
  { key: 'total_requests', label: '总请求', unit: '次' }
]
const deltaFocusKeys = computed(() => {
  const rows = metricRows.value || []
  const byKey = Object.fromEntries(rows.map((m) => [m.key, m]))
  const focus = [...DELTA_FOCUS_BASE]
  const phaseRows = rows
    .filter((m) => String(m?.key || '').startsWith('phase_mean_'))
    .sort((a, b) => {
      const ka = String(a.key || '')
      const kb = String(b.key || '')
      const rank = (k) => (k.includes('total_time') ? 0 : /answer/i.test(k) ? 1 : 2)
      return rank(ka) - rank(kb) || ka.localeCompare(kb)
    })
    .slice(0, 6)
  for (const m of phaseRows) {
    if (byKey[m.key]) {
      focus.push({ key: m.key, label: m.label || m.key, unit: 's' })
    }
  }
  return focus
})
const deltaBlocks = computed(() => {
  if (!baselineEnabled.value || records.value.length < 2) return []
  const ref = records.value.find((x) => x.id === referenceId.value)
  if (!ref) return []
  const byKey = Object.fromEntries((metricRows.value || []).map((m) => [m.key, m]))
  return records.value
    .filter((r) => r.id !== referenceId.value)
    .map((other) => {
      const rid = String(other.id)
      const cards = deltaFocusKeys.value
        .map(({ key, label, unit }) => {
          const m = byKey[key] || {}
          const cur = (m.values || {})[rid]
          const base = (m.values || {})[String(referenceId.value)]
          const pct = (m.change_pct || {})[rid]
          if (pct == null && cur == null) return null
          const tone = pctTone(key, pct, m.lower_is_better)
          const withUnit = (v) => {
            if (v == null) return '—'
            if (unit === 's') {
              const n = Number(v)
              return Number.isFinite(n) ? `${Math.round(n * 1000) / 1000} s` : `${v} s`
            }
            return unit ? `${v} ${unit}` : String(v)
          }
          return {
            key,
            label,
            tone,
            pctText: pct == null ? '—' : formatPct(pct),
            baseText: withUnit(base),
            curText: withUnit(cur)
          }
        })
        .filter(Boolean)
      return {
        otherId: other.id,
        otherLabel: roundHeading(other),
        refLabel: roundHeading(ref),
        cards
      }
    })
    .filter((b) => b.cards.length)
})

const metricKeyMap = {
  qps: 'qps',
  success_qps: 'success_qps',
  avg_response_time: 'avg_rt',
  p95_response_time: 'p95',
  error_rate: 'error_rate',
  total_requests: 'total_requests'
}
const metricNoteFor = (key) => {
  const notes = aiAnalysis.value.metric_notes || {}
  return notes[metricKeyMap[key] || key] || notes[key] || ''
}
const metricNoteHtml = (key) => {
  const text = metricNoteFor(key)
  const row = (metricRows.value || []).find((m) => m.key === key)
  const lib = row?.lower_is_better != null ? row.lower_is_better : metricLowerIsBetter(key)
  if (text) {
    return colorizePctPhrases(text, { metricKey: key, lowerIsBetter: lib })
  }
  if (!baselineEnabled.value) return ''
  // 无 AI 解读时，用相对参照轮变化生成短说明（与导出 HTML 回退一致）
  const ref = String(referenceId.value)
  const bits = []
  for (const r of records.value) {
    if (String(r.id) === ref) continue
    const pct = row?.change_pct?.[String(r.id)]
    if (pct == null) continue
    const n = Number(pct)
    if (!Number.isFinite(n)) continue
    const tone = pctTone(key, n, lib)
    const verb =
      tone === 'better' ? '改善' : tone === 'worse' ? '恶化' : '变化'
    bits.push(`${humanizeMetricKey(key, metricLabelMap.value)}较参照轮${verb}约 ${n > 0 ? '+' : ''}${n}%`)
  }
  if (!bits.length) return ''
  return colorizePctPhrases(bits.join('；'), { metricKey: key, lowerIsBetter: lib })
}
const caseNoteFor = (name) => {
  const list = aiAnalysis.value.case_notes || []
  const hit = list.find((c) => c?.name === name)
  return hit?.note || ''
}
const chartNoteFor = (label) => {
  const list = aiAnalysis.value.chart_notes || []
  const hit = list.find((c) => c?.label === label || c?.name === label)
  return hit || {}
}
const recordById = (id) => records.value.find((r) => Number(r.id) === Number(id))
const recordChartsProps = (recordOrChapter) => {
  const isChapter = recordOrChapter?.record_id != null && recordOrChapter?.id == null
  const rec = isChapter ? recordById(recordOrChapter.record_id) : recordOrChapter
  const label = isChapter ? chLabel(recordOrChapter) : recLabel(recordOrChapter)
  const note = chartNoteFor(label)
  return {
    timeSeries: rec?.time_series_data || [],
    rtHistogram: rec?.rt_histogram || [],
    qps: rec?.qps ?? recordOrChapter?.qps,
    p95: rec?.p95_response_time ?? recordOrChapter?.p95_response_time,
    trendNote: note.trend || '',
    distNote: note.distribution || ''
  }
}

const trustWarnings = computed(() => {
  if (isMerge.value || !baselineEnabled.value) return []
  const by = snapshot.value.trust_by_record || {}
  const msgs = []
  for (const [rid, t] of Object.entries(by)) {
    for (const w of t?.warnings || []) {
      const rec = records.value.find((x) => String(x.id) === String(rid))
      const label = rec ? recLabel(rec) : `#${rid}`
      msgs.push(`相对参照轮 · ${label}：${w}`)
    }
  }
  if (snapshot.value.trust?.warnings?.length) {
    msgs.push(...snapshot.value.trust.warnings)
  }
  return [...new Set(msgs)]
})

const cellOf = (row, rid) => (row.values || {})[String(rid)]
const casePresent = (row, rid) => {
  const v = cellOf(row, rid)
  if (!v) return false
  if (v.present === false) return false
  if (v.present === true) return true
  // 旧快照兼容
  return !(v.total === 0 && (v.avg_rt === 0 || v.avg_rt == null) && (v.p95_rt === 0 || v.p95_rt == null))
}
const casePct = (row, rid) => {
  if (!casePresent(row, rid) || !casePresent(row, referenceId.value)) return null
  if (row.change_pct_avg && row.change_pct_avg[String(rid)] != null) {
    return row.change_pct_avg[String(rid)]
  }
  const base = cellOf(row, referenceId.value)
  const cur = cellOf(row, rid)
  try {
    const b = Number(base?.avg_rt || 0)
    const c = Number(cur?.avg_rt || 0)
    if (b === 0) return c === 0 ? 0 : 100
    return Math.round(((c - b) / b) * 10000) / 100
  } catch {
    return null
  }
}

const formatMetric = (key, val) => {
  if (val === undefined || val === null) return '-'
  if (key === 'error_rate') return `${val}%`
  if (key === 'qps' || key === 'success_qps') return Number(val).toFixed(2)
  return val
}

const formatStageMetric = (key, val) => {
  if (val === undefined || val === null) return '-'
  const n = Number(val)
  if (Number.isNaN(n)) return val
  if (key === 'avg_qps') return n.toFixed(2)
  if (key === 'avg_rt' || key === 'avg_p95') {
    const sec = Math.round((n / 1000) * 10) / 10
    return `${Math.round(n * 10) / 10} ms（约 ${sec}s）`
  }
  if (key === 'avg_error_rate') return `${Math.round(n * 100) / 100}%`
  if (key === 'planned_duration' || key === 'observed_seconds' || key === 'completed_seconds') return `${Math.round(n)} s`
  if (key === 'users') return String(Math.round(n))
  return val
}

const formatPct = (pct) => {
  if (pct === undefined || pct === null) return ''
  const n = Number(pct)
  return `${n > 0 ? '+' : ''}${n}%`
}

const pctTone = (key, pct, lowerIsBetter) => semanticPctTone(key, pct, lowerIsBetter)
const pctColor = (key, pct, lowerIsBetter) => semanticPctColor(key, pct, lowerIsBetter)

const stagePctColor = (row, pct) => {
  // 并发/时长等配置项无好坏方向，仅灰显百分比
  if (row?.lower_is_better == null) return '#64748b'
  return pctColor(row?.key, pct, row?.lower_is_better)
}

const fmtErr = (v) => (v === undefined || v === null ? '-' : `${v}%`)
const errClass = (v) => {
  const n = Number(v)
  if (Number.isNaN(n)) return ''
  if (n >= 5) return 'err-bad'
  if (n > 0) return 'err-warn'
  return 'err-ok'
}

/** 指标语义色：与单次报告阈值对齐（错误率 5%、P95/RT 档位） */
const metricTone = (kind, val) => {
  if (val === undefined || val === null || val === '') return 'tone-neutral'
  const n = Number(val)
  if (Number.isNaN(n)) return 'tone-neutral'
  if (kind === 'error_rate') {
    if (n >= 5) return 'tone-danger'
    if (n > 0) return 'tone-warning'
    return 'tone-success'
  }
  if (kind === 'p95' || kind === 'rt') {
    if (n >= 1000) return 'tone-danger'
    if (n >= 500) return 'tone-warning'
    return 'tone-success'
  }
  if (kind === 'qps') {
    if (n <= 0) return 'tone-warning'
    return 'tone-primary'
  }
  return 'tone-neutral'
}

const loadReport = async () => {
  const id = Number(route.params.reportId)
  if (!id) return
  loading.value = true
  try {
    const res = await perfComparisonApi.getDetail(id)
    report.value = res.data || res
    liveAi.value = report.value?.ai_analysis || null
  } catch (err) {
    console.error(err)
    ElMessage.error('加载报告失败')
  } finally {
    loading.value = false
  }
}

const exportHtml = async () => {
  if (!report.value?.id) return
  exporting.value = true
  try {
    const res = await perfComparisonApi.exportHtml(report.value.id)
    const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = resolveDownloadFilename(res, {
      title: report.value.title || kindTitle.value,
      fallback: kindTitle.value || '对比报告',
      ext: '.html'
    })
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已开始下载')
  } catch (err) {
    console.error(err)
    const timedOut = err?.code === 'ECONNABORTED' || /timeout/i.test(String(err?.message || ''))
    ElMessage.error(timedOut ? '导出超时，请稍后重试（大报告可能需 1–2 分钟）' : '导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(loadReport)
</script>

<style scoped>
.report-shell {
  max-width: 1100px;
}
.title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.title-text {
  font-size: 18px;
  font-weight: bold;
  display: flex;
  align-items: center;
}
.title-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.report-hero {
  background: linear-gradient(135deg, #1a73e8, #0d47a1);
  color: #fff;
  padding: 28px 32px;
  border-radius: 12px;
  margin-bottom: 18px;
}
.hero-title {
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 8px;
}
.hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
  opacity: 0.9;
}
.rpt-section {
  background: #fff;
  border-radius: 10px;
  padding: 20px 22px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  border: 1px solid #eef2f7;
}
.rpt-section.chapter {
  background: #fafbfd;
}
.rpt-h2 {
  font-size: 16px;
  color: #1a73e8;
  margin: 0 0 14px;
  padding-bottom: 8px;
  border-bottom: 2px solid #e8edf3;
}
.block-gap {
  margin-bottom: 12px;
}
.overview-para {
  color: #555;
  margin: 0 0 14px;
  line-height: 1.6;
}
.metric-notes-strip {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0 0 14px;
}
.compare-intro {
  font-size: 13px;
  color: #475569;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  margin: 0 0 12px;
  line-height: 1.55;
}
.steps-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.steps-stack .steps-head {
  font-weight: 600;
  color: #334155;
  margin-bottom: 2px;
}
.steps-stack .step-line {
  font-size: 12px;
  color: #475569;
  background: #f8fafc;
  border: 1px solid #eef2f7;
  border-radius: 6px;
  padding: 4px 8px;
  line-height: 1.4;
}
.stage-summary-block {
  margin-bottom: 12px;
}
.stage-summary-label {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f1f5f9;
  border-radius: 8px;
}
.stage-summary-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.stage-summary-card {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px 14px;
  background: #fff;
  border-left: 4px solid #94a3b8;
}
.stage-summary-card.better {
  border-left-color: #22c55e;
  background: #f0fdf4;
}
.stage-summary-card.worse {
  border-left-color: #ef4444;
  background: #fef2f2;
}
.stage-summary-card.flat {
  border-left-color: #94a3b8;
  background: #f8fafc;
}
.stage-sum-title {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.stage-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 999px;
  background: #1a73e8;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}
.stage-sum-line {
  font-size: 12.5px;
  color: #334155;
  line-height: 1.55;
  margin: 4px 0;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 8px;
}
.stage-sum-meta {
  color: #64748b;
}
.stage-sum-deltas {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e2e8f0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.delta-chip {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid #e2e8f0;
}
.stage-detail-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}
.stage-detail-head.better {
  background: #f0fdf4;
  border-color: #bbf7d0;
}
.stage-detail-head.worse {
  background: #fef2f2;
  border-color: #fecaca;
}
.stage-cmp-block {
  margin-bottom: 16px;
}
.stage-cmp-block:last-child {
  margin-bottom: 0;
}
.stage-cmp-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}
:deep(.col-ref) {
  background: #fffefb !important;
}
:deep(th.col-ref) {
  background: #fff7ed !important;
  color: #9a3412 !important;
}
:deep(.col-cmp) {
  background: #fafcff !important;
}
:deep(th.col-cmp) {
  background: #eff6ff !important;
  color: #1e40af !important;
}
.delta-block {
  margin-bottom: 14px;
}
.delta-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 13px;
}
.delta-head .muted {
  color: #94a3b8;
}
.delta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 10px;
}
.delta-card {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 12px 10px;
  text-align: center;
  background: #fff;
}
.delta-card.better {
  border-color: #86efac;
  background: #f0fdf4;
}
.delta-card.worse {
  border-color: #fca5a5;
  background: #fef2f2;
}
.delta-card.flat {
  background: #f8fafc;
}
.delta-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}
.delta-pct {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  color: #64748b;
}
.delta-pct.better { color: #15803d; }
.delta-pct.worse { color: #b91c1c; }
.delta-vals {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
}
.case-ai-note {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.45;
}
.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}
.overview-panel {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px 14px;
}
.overview-panel.is-ref {
  border-color: #fcd34d;
  background: linear-gradient(180deg, #fffbeb 0%, #fff 48px);
}
.overview-panel.is-cmp {
  border-color: #93c5fd;
  background: linear-gradient(180deg, #eff6ff 0%, #fff 48px);
}
.panel-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.panel-title .muted {
  color: #94a3b8;
  font-size: 12px;
}
.kv-table {
  width: 100%;
  font-size: 13px;
  border-collapse: collapse;
}
.kv-table td {
  padding: 5px 0;
  border-bottom: 1px solid #f1f5f9;
}
.kv-table td:first-child {
  width: 110px;
  color: #64748b;
}
.tip-icon {
  margin-left: 2px;
  color: #94a3b8;
  cursor: help;
  vertical-align: middle;
}
.ov-better { color: #16a34a; font-weight: 600; }
.ov-worse { color: #dc2626; font-weight: 600; }
.ov-flat { color: #64748b; }
.ov-ref { color: #475569; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.summary-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px 14px;
  text-align: center;
}
.summary-card.wide {
  text-align: left;
}
.summary-card .label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}
.summary-card .value {
  font-size: 22px;
  font-weight: 700;
  color: #1a73e8;
}
.summary-card .value small {
  font-size: 13px;
  font-weight: 500;
  opacity: 0.85;
}
.summary-card .value.tone-primary { color: #1a73e8; }
.summary-card .value.tone-success { color: #38a169; }
.summary-card .value.tone-warning { color: #dd6b20; }
.summary-card .value.tone-danger { color: #e53e3e; }
.summary-card .value.tone-neutral { color: #475569; }
.cell-tone-primary { color: #1a73e8; }
.cell-tone-success { color: #38a169; }
.cell-tone-warning { color: #dd6b20; }
.cell-tone-danger { color: #e53e3e; }
.cell-tone-neutral { color: #475569; }
.card-sub {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}
.chapter-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.chapter-meta {
  margin: 0 0 12px;
  font-size: 12px;
  color: #909399;
}
.record-chart-wrap {
  margin-bottom: 18px;
  padding-bottom: 12px;
  border-bottom: 1px dashed #e2e8f0;
}
.record-chart-wrap:last-child {
  border-bottom: 0;
  margin-bottom: 0;
}
.rpt-table {
  width: 100%;
}
.pct {
  font-size: 12px;
  margin-top: 2px;
  font-weight: 600;
}
.pct.inline {
  margin-left: 4px;
}
.pct-better {
  color: #15803d !important;
  font-weight: 600;
}
.pct-worse {
  color: #b91c1c !important;
  font-weight: 600;
}
.pct-flat {
  color: #64748b !important;
}
.metric-note {
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
}
.metric-note :deep(.pct-better) {
  color: #15803d !important;
  font-weight: 600;
}
.metric-note :deep(.pct-worse) {
  color: #b91c1c !important;
  font-weight: 600;
}
.metric-note :deep(.pct-flat),
.metric-note :deep(.pct-emphasis) {
  color: #475569 !important;
  font-weight: 600;
}
.case-name {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.case-note {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
}
.case-metrics {
  font-size: 12px;
  color: #475569;
  line-height: 1.55;
}
.case-col-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
  line-height: 1.35;
}
.case-col-sub {
  font-size: 12px;
  font-weight: 600;
  white-space: normal;
}
.case-cmp-table :deep(th.case-col-ref),
.case-cmp-table :deep(td.case-col-ref) {
  background: #fffefb !important;
}
.case-cmp-table :deep(th.case-col-cmp),
.case-cmp-table :deep(td.case-col-cmp) {
  background: #fafcff !important;
}
.case-cmp-table :deep(th.case-col-start),
.case-cmp-table :deep(td.case-col-start) {
  border-left: 10px solid #f1f5f9 !important;
}
.missing-cell {
  color: #94a3b8;
  font-size: 12px;
  text-align: center;
  padding: 8px 0;
}
.err-ok { color: #38a169; }
.err-warn { color: #dd6b20; }
.err-bad { color: #e53e3e; }
</style>
