<template>
  <el-card shadow="never" class="report-summary-panel" v-loading="loading">
    <template #header>
      <div class="panel-header">
        <span class="panel-title">AI 报告摘要</span>
        <div class="panel-actions">
          <el-tag v-if="summary?.cached" size="small" type="info">缓存</el-tag>
          <el-button size="small" :loading="loading" @click="generate(true)">重新生成</el-button>
          <el-button size="small" :disabled="!summary?.summary" @click="copySummary">复制</el-button>
        </div>
      </div>
    </template>

    <template v-if="summary?.summary">
      <el-alert
        v-if="summary?.summary && hasIncompleteFailureData"
        type="warning"
        :closable="false"
        show-icon
        title="部分失败用例缺少详细错误字段，可点击用例行的「AI 分析」获取逐步骤根因（含截图）。"
        style="margin-bottom: 12px;"
      />
      <p class="summary-text">{{ summary.summary }}</p>
      <div v-if="summary.highlights?.length" class="block">
        <div class="block-label">关注要点</div>
        <ul class="bullet-list">
          <li v-for="(h, i) in summary.highlights" :key="'h' + i">{{ h }}</li>
        </ul>
      </div>
      <div v-if="summary.recommendations?.length" class="block">
        <div class="block-label">下一步建议</div>
        <ul class="bullet-list rec">
          <li v-for="(r, i) in summary.recommendations" :key="'r' + i">{{ r }}</li>
        </ul>
      </div>
      <div v-if="summary.duration_ms" class="footer-meta">
        耗时 {{ summary.duration_ms }}ms · Token {{ summary.tokens_used || 0 }}
      </div>
    </template>

    <el-empty v-else-if="!loading" description="暂无 AI 摘要">
      <el-button type="primary" size="small" @click="generate(false)">生成 AI 摘要</el-button>
    </el-empty>
  </el-card>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { aiAnalyzeApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'

const props = defineProps({
  reportType: { type: String, required: true },
  recordId: { type: Number, required: true }
})

const proStore = ProjectStore()
const uStore = UserStore()
const loading = ref(false)
const summary = ref(null)

const hasIncompleteFailureData = computed(() => {
  const s = summary.value?.summary || ''
  return /缺少|未提供|无具体|错误信息缺失|详细错误/.test(s)
})

const loadCached = async () => {
  if (!props.recordId || !proStore.projectInfo?.id) return
  try {
    const res = await aiAnalyzeApi.getReportSummaryByRecord(
      props.reportType,
      props.recordId,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200 && res.data.data?.summary) {
      summary.value = res.data.data
    }
  } catch {
    summary.value = null
  }
}

const generate = async (force) => {
  if (!uStore.hasPermission('ai_test:execute')) {
    ElMessage.warning('无 AI 分析权限（需要 ai_test:execute）')
    return
  }
  if (!props.recordId || !proStore.projectInfo?.id) return
  loading.value = true
  try {
    const res = await aiAnalyzeApi.generateReportSummary(
      {
        report_type: props.reportType,
        record_id: props.recordId,
        force_refresh: force
      },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      summary.value = res.data.data
      if (summary.value?.summary) {
        ElMessage.success(res.data.message || '摘要已生成')
      } else {
        ElMessage.warning(res.data.message || '未能解析摘要')
      }
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '生成失败')
  } finally {
    loading.value = false
  }
}

const copySummary = async () => {
  const s = summary.value
  if (!s?.summary) return
  const lines = [
    s.summary,
    s.highlights?.length ? '\n要点：\n' + s.highlights.map((x, i) => `${i + 1}. ${x}`).join('\n') : '',
    s.recommendations?.length ? '\n建议：\n' + s.recommendations.map((x, i) => `${i + 1}. ${x}`).join('\n') : ''
  ].filter(Boolean)
  try {
    await navigator.clipboard.writeText(lines.join('\n'))
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

watch(
  () => [props.reportType, props.recordId],
  () => {
    summary.value = null
    loadCached()
  },
  { immediate: true }
)
</script>

<style scoped>
.report-summary-panel {
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-title {
  font-weight: 600;
}
.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.summary-text {
  line-height: 1.7;
  color: #303133;
  margin: 0 0 12px;
}
.block {
  margin-top: 12px;
}
.block-label {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 6px;
}
.bullet-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.6;
}
.rec li {
  color: #409eff;
}
.footer-meta {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
  text-align: right;
}
</style>
