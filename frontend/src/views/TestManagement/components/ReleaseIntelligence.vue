<template>
  <div class="release-intelligence" v-loading="loading">
    <TmPremiumBanner />
    <div class="intel-toolbar">
      <el-button size="small" @click="load">刷新分析</el-button>
      <el-button
        v-if="canGenerateAi"
        type="primary"
        size="small"
        :loading="aiLoading"
        @click="generateAi"
      >
        生成 AI 版本总结
      </el-button>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :lg="14">
        <el-card shadow="never" class="intel-card">
          <template #header>
            <span>稳定性趋势</span>
            <el-tag v-if="runDeltaLabel" size="small" :type="runDeltaType" style="margin-left: 8px">
              {{ runDeltaLabel }}
            </el-tag>
          </template>
          <div v-if="runTrend.length" ref="chartRef" class="trend-chart" />
          <el-empty v-else description="暂无计划运行数据" :image-size="64" />
          <div v-if="automationOverview.linked_count" class="auto-overview">
            <span>关联自动化 {{ automationOverview.linked_count }} 条</span>
            <span>本版本运行样本 {{ automationOverview.with_runs || 0 }}</span>
            <span>不稳定 {{ automationOverview.unstable || 0 }}</span>
            <span v-if="automationOverview.avg_pass_rate_pct != null">
              平均通过率 {{ automationOverview.avg_pass_rate_pct }}%
            </span>
          </div>
          <el-table
            v-if="unstableItems.length"
            :data="unstableItems"
            size="small"
            border
            stripe
            style="margin-top: 12px"
            empty-text="无"
          >
            <el-table-column prop="case_name" label="自动化用例" min-width="160" show-overflow-tooltip />
            <el-table-column prop="domain" label="域" width="70" />
            <el-table-column label="通过率" width="90">
              <template #default="{ row }">
                {{ formatRate(row.pass_rate) }}
              </template>
            </el-table-column>
            <el-table-column label="关联功能用例" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">
                {{ (row.functional_case_titles || []).join('、') || '—' }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="10">
        <el-card shadow="never" class="intel-card">
          <template #header>风险推荐</template>
          <el-empty v-if="!recommendations.length" description="暂无风险项，质量状态良好" :image-size="64" />
          <div v-else class="rec-list">
            <div
              v-for="item in recommendations"
              :key="item.id"
              class="rec-item"
              @click="onRecAction(item)"
            >
              <div class="rec-head">
                <el-tag :type="severityTag(item.severity)" size="small" effect="light">
                  {{ severityLabel(item.severity) }}
                </el-tag>
                <span class="rec-title">{{ item.title }}</span>
              </div>
              <p class="rec-detail">{{ item.detail }}</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="intel-card ai-card" style="margin-top: 16px">
      <template #header>
        <span>AI 版本总结</span>
        <el-tag v-if="aiSummary?.status === 'done'" type="success" size="small" style="margin-left: 8px">已生成</el-tag>
        <el-tag v-else-if="aiSummary?.status === 'failed'" type="danger" size="small" style="margin-left: 8px">失败</el-tag>
      </template>
      <template v-if="aiSummary?.status === 'done'">
        <div class="ai-conclusion">
          <el-tag :type="conclusionTag(aiSummary.conclusion)" size="large">
            {{ aiSummary.conclusion || '—' }}
          </el-tag>
          <span v-if="aiSummary.generated_at" class="ai-meta">
            {{ formatTime(aiSummary.generated_at) }}
            <template v-if="aiSummary.generated_by"> · {{ aiSummary.generated_by }}</template>
          </span>
        </div>
        <p class="ai-exec">{{ aiSummary.executive_summary }}</p>
        <el-row :gutter="16">
          <el-col :xs="24" :md="8" v-if="aiSummary.highlights?.length">
            <h4>亮点</h4>
            <ul><li v-for="(t, i) in aiSummary.highlights" :key="'h'+i">{{ t }}</li></ul>
          </el-col>
          <el-col :xs="24" :md="8" v-if="aiSummary.risks?.length">
            <h4>风险</h4>
            <ul><li v-for="(t, i) in aiSummary.risks" :key="'r'+i">{{ t }}</li></ul>
          </el-col>
          <el-col :xs="24" :md="8" v-if="aiSummary.recommendations?.length">
            <h4>建议</h4>
            <ul><li v-for="(t, i) in aiSummary.recommendations" :key="'a'+i">{{ t }}</li></ul>
          </el-col>
        </el-row>
        <p v-if="aiSummary.automation_note" class="ai-note">{{ aiSummary.automation_note }}</p>
      </template>
      <el-alert
        v-else-if="aiSummary?.status === 'failed'"
        type="error"
        :closable="false"
        show-icon
        :title="aiSummary.error || '生成失败'"
        :description="aiSummary.raw_preview"
      />
      <el-empty v-else description="点击「生成 AI 版本总结」基于当前质量与风险数据生成" :image-size="72" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { testReleaseApi } from '@/api/testManagement'
import { UserStore } from '@/stores/module/UserStore'
import TmPremiumBanner from '@/components/TmPremiumBanner.vue'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  releaseId: { type: [Number, String], required: true },
  projectId: { type: [Number, String], required: true },
  tabActive: { type: Boolean, default: true }
})

const emit = defineEmits(['goto'])

const uStore = UserStore()
const canGenerateAi = computed(() => uStore.hasPermission('ai_test:execute'))

const loading = ref(false)
const aiLoading = ref(false)
const runTrend = ref([])
const runDelta = ref(null)
const automationOverview = ref({})
const unstableItems = ref([])
const recommendations = ref([])
const aiSummary = ref(null)
const chartRef = ref(null)
let chart = null

const runDeltaLabel = computed(() => {
  if (runDelta.value == null) return ''
  const pct = Math.round(runDelta.value * 1000) / 10
  if (pct > 0) return `较上轮 +${pct}%`
  if (pct < 0) return `较上轮 ${pct}%`
  return '较上轮持平'
})
const runDeltaType = computed(() => {
  if (runDelta.value == null) return 'info'
  if (runDelta.value > 0) return 'success'
  if (runDelta.value < 0) return 'danger'
  return 'info'
})

const severityLabel = (s) =>
  ({ critical: '严重', high: '高', medium: '中', low: '低', info: '提示' }[s] || s)
const severityTag = (s) =>
  ({ critical: 'danger', high: 'danger', medium: 'warning', low: 'info', info: 'info' }[s] || 'info')
const conclusionTag = (c) => {
  const t = String(c || '')
  if (t.includes('不建议')) return 'danger'
  if (t.includes('有条件')) return 'warning'
  return 'success'
}
const formatRate = (v) => (v == null ? '—' : `${Math.round(v * 1000) / 10}%`)
const formatTime = (v) => (v ? String(v).replace('T', ' ').slice(0, 16) : '')

const renderChart = () => {
  if (!props.tabActive || !chartRef.value || !runTrend.value.length) return
  if (!chart) chart = echarts.init(chartRef.value)
  const labels = runTrend.value.map((r) => {
    const t = formatTime(r.started_at || r.time)
    return t ? `${t} #${r.run_id}` : `#${r.run_id}`
  })
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['必测通过率', '必测完成率'] },
    grid: { left: 48, right: 16, top: 36, bottom: 28 },
    xAxis: { type: 'category', data: labels },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      {
        name: '必测通过率',
        type: 'line',
        smooth: true,
        data: runTrend.value.map((r) => r.pass_rate_pct ?? null)
      },
      {
        name: '必测完成率',
        type: 'line',
        smooth: true,
        data: runTrend.value.map((r) => r.completion_rate_pct ?? null)
      }
    ]
  })
  chart.resize()
}

const disposeChart = () => {
  if (chart) {
    chart.dispose()
    chart = null
  }
}

const applyData = (data) => {
  const st = data?.stability_trend || {}
  runTrend.value = st.run_trend || []
  runDelta.value = st.run_trend_delta ?? null
  automationOverview.value = st.automation?.overview || {}
  unstableItems.value = st.automation?.unstable_items || []
  recommendations.value = data?.risk_recommendations || []
  aiSummary.value = data?.ai_summary || null
}

const load = async () => {
  if (!props.releaseId || !props.projectId) return
  loading.value = true
  try {
    const res = await testReleaseApi.getIntelligence(props.releaseId, props.projectId)
    applyData(res.data?.data || {})
    await nextTick()
    renderChart()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载智能化分析失败')
  } finally {
    loading.value = false
  }
}

const generateAi = async () => {
  aiLoading.value = true
  try {
    const res = await testReleaseApi.generateAiSummary(props.releaseId, props.projectId)
    const data = res.data?.data || null
    if (data?.status === 'done') {
      const cached = await testReleaseApi.getAiSummary(props.releaseId, props.projectId)
      aiSummary.value = cached.data?.data || data
      ElMessage.success('AI 版本总结已生成')
    } else {
      aiSummary.value = data
      ElMessage.error(data?.error || res.data?.message || 'AI 总结生成失败')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || 'AI 总结生成失败')
  } finally {
    aiLoading.value = false
  }
}

const onRecAction = (item) => {
  if (item?.action) emit('goto', item.action)
}

watch(
  () => [props.releaseId, props.projectId],
  () => {
    disposeChart()
    load()
  }
)

watch(
  () => props.tabActive,
  (active) => {
    if (active) {
      nextTick(() => renderChart())
    }
  }
)

onMounted(() => load())
onBeforeUnmount(() => disposeChart())
</script>

<style scoped lang="scss">
.release-intelligence {
  margin-top: 12px;
}
.intel-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.intel-card {
  margin-bottom: 16px;
}
.trend-chart {
  height: 260px;
}
.auto-overview {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
  font-size: 13px;
  color: #606266;
}
.rec-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.rec-item {
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s;
  &:hover {
    border-color: #409eff;
  }
}
.rec-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.rec-title {
  font-weight: 600;
  font-size: 14px;
}
.rec-detail {
  margin: 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}
.ai-conclusion {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.ai-meta {
  font-size: 12px;
  color: #909399;
}
.ai-exec {
  font-size: 15px;
  line-height: 1.6;
  margin: 0 0 16px;
}
.ai-card h4 {
  margin: 0 0 8px;
  font-size: 14px;
}
.ai-card ul {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: #606266;
}
.ai-note {
  margin-top: 12px;
  font-size: 13px;
  color: #909399;
}
</style>
