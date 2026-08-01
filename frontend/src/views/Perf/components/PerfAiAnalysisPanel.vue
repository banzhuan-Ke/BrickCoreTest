<template>
  <el-card shadow="never" class="perf-ai-panel" :class="{ 'is-conclusion': isConclusion }" v-loading="busy">
    <template #header>
      <div class="panel-header">
        <div class="title-wrap">
          <span class="panel-title">{{ isConclusion ? '结论与建议' : 'AI 分析' }}</span>
          <span v-if="isConclusion && hasSummary" class="title-hint">正文中已随文展示指标/趋势解读</span>
        </div>
        <div class="panel-actions">
          <el-tag v-if="analysis?.cached" size="small" type="info">缓存</el-tag>
          <el-tag v-if="isRunning" size="small" type="warning">分析中</el-tag>
          <el-tag v-else-if="analysis?.status === 'failed'" size="small" type="danger">失败</el-tag>
          <el-button
            v-if="showExpandToggle"
            size="small"
            text
            type="primary"
            @click="expanded = !expanded"
          >
            {{ expanded ? '收起随文解读副本' : '展开随文解读副本' }}
          </el-button>
          <el-button size="small" :disabled="busy" @click="refresh">刷新</el-button>
          <el-button size="small" type="primary" :loading="triggering" @click="generate(false)">
            {{ hasSummary ? '重新生成' : '生成分析' }}
          </el-button>
          <el-button size="small" :disabled="!hasSummary" @click="copySummary">复制</el-button>
        </div>
      </div>
    </template>

    <el-alert
      v-if="disabledByProject"
      type="info"
      :closable="false"
      show-icon
      title="项目已关闭压测 AI 分析（可在项目设置 → 压测 AI 开启）"
      style="margin-bottom: 12px"
    />

    <template v-if="isRunning">
      <div class="running-box">
        <el-icon class="is-loading" :size="20"><Loading /></el-icon>
        <span>正在分析中…报告数据可正常查看。完成后请点「刷新」或重新进入本页。</span>
      </div>
    </template>

    <template v-else-if="hasSummary">
      <p
        v-if="analysis.overview"
        class="overview-text"
        v-html="richText(analysis.overview)"
      />
      <p
        v-if="analysis.summary"
        class="summary-text"
        v-html="richText(analysis.summary)"
      />

      <div v-if="conclusionPoints.length" class="block">
        <div class="block-label">关键指标对照</div>
        <ul class="tone-list">
          <li
            v-for="(p, i) in conclusionPoints"
            :key="'cp' + i"
            :class="'tone-' + pointTone(p)"
          >
            <strong v-if="p.label">{{ humanizeLabel(p.label) }}：</strong>
            <span v-html="richText(p.text, p.label)" />
          </li>
        </ul>
      </div>

      <!-- 结论类内容：conclusion 模式默认展示 -->
      <div v-if="analysis.highlights?.length" class="block">
        <div class="block-label">关注要点</div>
        <ul>
          <li v-for="(h, i) in analysis.highlights" :key="'h' + i" v-html="richText(h)" />
        </ul>
      </div>
      <div v-if="analysis.bottleneck_notes?.length" class="block">
        <div class="block-label">瓶颈</div>
        <ul>
          <li v-for="(h, i) in analysis.bottleneck_notes" :key="'b' + i" v-html="richText(h)" />
        </ul>
      </div>
      <div v-if="analysis.risks?.length" class="block">
        <div class="block-label">风险</div>
        <ul>
          <li v-for="(h, i) in analysis.risks" :key="'r' + i" v-html="richText(h)" />
        </ul>
      </div>
      <div v-if="analysis.recommendations?.length" class="block">
        <div class="block-label">建议</div>
        <ul>
          <li v-for="(h, i) in analysis.recommendations" :key="'rec' + i" v-html="richText(h)" />
        </ul>
      </div>

      <!-- 与正文重复的解读：仅 full 模式，或 conclusion 展开后可见 -->
      <div v-show="!isConclusion || expanded">
        <div v-if="metricNoteEntries.length" class="block">
          <div class="block-label">指标解读</div>
          <ul>
            <li v-for="(row, i) in metricNoteEntries" :key="'m' + i">
              <strong>{{ row.label }}：</strong>
              <span v-html="richText(row.note, row.key)" />
            </li>
          </ul>
        </div>
        <div v-if="analysis.case_notes?.length" class="block">
          <div class="block-label">接口解读</div>
          <ul>
            <li v-for="(c, i) in analysis.case_notes" :key="'c' + i">
              <strong>{{ c.name }}：</strong>
              <span v-html="richText(c.note)" />
            </li>
          </ul>
        </div>
        <div v-if="chartNoteEntries.length" class="block">
          <div class="block-label">趋势与分布解读</div>
          <ul>
            <li v-for="(row, i) in chartNoteEntries" :key="'ch' + i">
              <strong>{{ row.label }}：</strong>
              <span v-if="row.trend">趋势 — <span v-html="richText(row.trend)" /></span>
              <span v-if="row.trend && row.distribution">；</span>
              <span v-if="row.distribution">分布 — <span v-html="richText(row.distribution)" /></span>
            </li>
          </ul>
        </div>
      </div>
      <div v-if="analysis.generated_at" class="footer-meta">生成于 {{ analysis.generated_at }}</div>
    </template>

    <template v-else-if="analysis?.status === 'failed'">
      <el-alert type="error" :closable="false" :title="analysis.error || '分析失败'" show-icon />
      <el-button style="margin-top: 12px" type="primary" size="small" @click="generate(true)">重试</el-button>
    </template>

    <el-empty v-else-if="!busy" description="暂无 AI 分析">
      <el-button type="primary" size="small" :disabled="disabledByProject" @click="generate(false)">
        生成 AI 分析
      </el-button>
    </el-empty>
  </el-card>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { aiAnalyzeApi, aiConfigApi } from '@/api/modules/ai.js'
import { perfComparisonApi, perfRecordApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'
import {
  colorizePctPhrases,
  humanizeMetricKey,
  metricLowerIsBetter,
} from '@/views/Perf/perfMetricSemantics.js'

const props = defineProps({
  /** 'record' | 'comparison' */
  mode: { type: String, required: true },
  targetId: { type: Number, required: true },
  /** 报告接口已带回的 ai_analysis */
  initialAnalysis: { type: Object, default: null },
  /**
   * full = 完整面板；conclusion = 结论汇总（默认收起详情，并隐藏已随文展示的字段）
   */
  variant: { type: String, default: 'conclusion' },
  /** 指标 key → 中文名，用于清洗展示 */
  labelMap: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['analysis-updated'])

const proStore = ProjectStore()
const uStore = UserStore()
const analysis = ref(null)
const busy = ref(false)
const triggering = ref(false)
const disabledByProject = ref(false)
const expanded = ref(false)

const isConclusion = computed(() => props.variant === 'conclusion')
const hasSummary = computed(() => {
  const a = analysis.value
  if (!a) return false
  if (a.status && a.status !== 'done') return false
  if (a.summary) return true
  if (a.overview) return true
  const pts = a.conclusion_points || a.metric_deltas
  return Array.isArray(pts) && pts.length > 0
})
const conclusionPoints = computed(() => {
  const pts = analysis.value?.conclusion_points || analysis.value?.metric_deltas || []
  if (!Array.isArray(pts)) return []
  return pts
    .map((p) => {
      if (typeof p === 'string') return { label: '', text: p, tone: 'flat' }
      if (!p || typeof p !== 'object') return null
      return {
        label: String(p.label || '').trim(),
        text: String(p.text || p.note || '').trim(),
        tone: String(p.tone || 'flat').toLowerCase(),
      }
    })
    .filter((p) => p && (p.text || p.label))
})
const isRunning = computed(() => {
  const s = analysis.value?.status
  return s === 'running' || s === 'pending'
})
const hasInlineDupes = computed(() => (
  metricNoteEntries.value.length > 0
  || (analysis.value?.case_notes || []).length > 0
  || chartNoteEntries.value.length > 0
))
const showExpandToggle = computed(() => isConclusion.value && hasSummary.value && hasInlineDupes.value)

const METRIC_NOTE_LABELS = {
  qps: 'QPS',
  avg_rt: '平均响应时间',
  p95: 'P95',
  error_rate: '错误率',
  total_requests: '总请求数',
  success_qps: '成功 QPS',
}
const metricNoteEntries = computed(() => {
  const notes = analysis.value?.metric_notes
  if (!notes || typeof notes !== 'object') return []
  return Object.entries(notes)
    .filter(([, v]) => v)
    .map(([k, v]) => ({
      key: k,
      label: humanizeMetricKey(k, { ...METRIC_NOTE_LABELS, ...props.labelMap }),
      note: v,
    }))
})
const humanizeLabel = (label) => humanizeMetricKey(label, props.labelMap)
const richText = (text, metricKey = '') =>
  colorizePctPhrases(text, {
    metricKey,
    lowerIsBetter: metricLowerIsBetter(metricKey),
  })
const pointTone = (p) => {
  const t = String(p?.tone || 'flat').toLowerCase()
  if (t === 'better' || t === 'improved') return 'better'
  if (t === 'worse' || t === 'degraded') return 'worse'
  // tone 缺失时，按文案内百分比推断
  const html = richText(p?.text || '', p?.label || '')
  if (html.includes('pct-worse')) return 'worse'
  if (html.includes('pct-better')) return 'better'
  return 'flat'
}
const chartNoteEntries = computed(() => {
  const a = analysis.value
  if (!a) return []
  const rows = []
  for (const c of a.chart_notes || []) {
    if (!c) continue
    const label = c.label || c.name
    if (!label) continue
    if (c.trend || c.distribution) {
      rows.push({ label, trend: c.trend || '', distribution: c.distribution || '' })
    }
  }
  if (!rows.length && (a.trend_note || a.distribution_note)) {
    rows.push({
      label: '本报告',
      trend: a.trend_note || '',
      distribution: a.distribution_note || ''
    })
  }
  return rows
})

const normalize = (raw) => {
  if (!raw || typeof raw !== 'object') return null
  if (raw.summary && !raw.status) return { ...raw, status: 'done' }
  return raw
}

const publish = (raw) => {
  analysis.value = normalize(raw)
  emit('analysis-updated', analysis.value)
}

const loadProjectGate = async () => {
  const pid = proStore.projectInfo?.id
  if (!pid) return
  try {
    const fromStore = proStore.projectInfo?.global_vars?.ai_settings
    if (fromStore && typeof fromStore === 'object') {
      disabledByProject.value = fromStore.perf_ai_analysis_enabled === false
      return
    }
    const res = await aiConfigApi.getExecutionSettings(pid)
    const data = res.data?.data || res.data
    disabledByProject.value = data?.perf_ai_analysis_enabled === false
  } catch {
    disabledByProject.value = false
  }
}

const refreshFromServer = async () => {
  if (!props.targetId) return
  busy.value = true
  try {
    if (props.mode === 'record') {
      const res = await perfRecordApi.getReport(props.targetId)
      const data = res.data || res
      publish(data.ai_analysis)
    } else {
      const res = await perfComparisonApi.getDetail(props.targetId)
      const data = res.data || res
      publish(data.ai_analysis)
    }
  } catch (e) {
    console.error(e)
    ElMessage.error('刷新 AI 分析结果失败')
  } finally {
    busy.value = false
  }
}

const refresh = () => refreshFromServer()

const generate = async (force) => {
  if (!uStore.hasPermission('ai_test:execute')) {
    ElMessage.warning('无 AI 分析权限（需要 ai_test:execute）')
    return
  }
  if (disabledByProject.value) {
    ElMessage.warning('项目已关闭压测 AI 分析')
    return
  }
  triggering.value = true
  try {
    const pid = proStore.projectInfo?.id
    let res
    if (props.mode === 'record') {
      res = await aiAnalyzeApi.analyzePerfReport(
        { record_id: props.targetId, force_refresh: force, async_mode: true },
        pid
      )
    } else {
      res = await aiAnalyzeApi.analyzePerfCompare(
        { comparison_report_id: props.targetId, force_refresh: force, async_mode: true },
        pid
      )
    }
    const body = res.data || res
    const data = body.data !== undefined ? body.data : body
    publish(data)
    if (data?.status === 'running' || data?.status === 'pending') {
      ElMessage.info('已开始后台分析，完成后请刷新')
    } else if (data?.summary) {
      ElMessage.success(data.cached ? '已返回缓存分析' : '分析完成')
    }
  } catch (err) {
    console.error(err)
    const detail = err?.data?.detail || err?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : 'AI 分析失败')
  } finally {
    triggering.value = false
  }
}

const copySummary = async () => {
  const parts = [
    analysis.value?.summary,
    ...(analysis.value?.highlights || []).map((x) => `- ${x}`),
    ...(analysis.value?.recommendations || []).map((x) => `建议: ${x}`)
  ].filter(Boolean)
  try {
    await navigator.clipboard.writeText(parts.join('\n'))
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

watch(
  () => props.targetId,
  () => {
    expanded.value = false
    publish(props.initialAnalysis)
    loadProjectGate()
  },
  { immediate: true }
)

watch(
  () => props.initialAnalysis,
  (val) => {
    // 父组件回写 liveAi 时只同步内容，不重置 expanded
    analysis.value = normalize(val)
  },
  { deep: true }
)

defineExpose({ refresh: refreshFromServer })
</script>

<style scoped>
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.title-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.panel-title {
  font-weight: 600;
}
.title-hint {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 400;
}
.panel-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.running-box {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #64748b;
  font-size: 13px;
}
.overview-text {
  color: #475569;
  line-height: 1.6;
  margin: 0 0 10px;
  white-space: pre-wrap;
}
.summary-text {
  color: #1e293b;
  line-height: 1.7;
  margin: 0 0 8px;
  font-size: 14px;
  white-space: pre-wrap;
}
.block {
  margin-top: 14px;
}
.block-label {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 6px;
}
.block ul {
  margin: 0;
  padding-left: 18px;
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
}
.tone-list .tone-better { color: #16a34a; }
.tone-list .tone-worse { color: #dc2626; }
.tone-list .tone-flat { color: #64748b; }
.tone-list :deep(.pct-better),
.overview-text :deep(.pct-better),
.summary-text :deep(.pct-better),
.block :deep(.pct-better) {
  color: #15803d !important;
  font-weight: 600;
}
.tone-list :deep(.pct-worse),
.overview-text :deep(.pct-worse),
.summary-text :deep(.pct-worse),
.block :deep(.pct-worse) {
  color: #b91c1c !important;
  font-weight: 600;
}
.footer-meta {
  margin-top: 12px;
  font-size: 12px;
  color: #94a3b8;
}
.is-conclusion :deep(.el-card__header) {
  background: #f8fafc;
}
</style>
