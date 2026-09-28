<template>
  <div class="job-progress-card" :class="`status-${status}`">
    <div class="job-head">
      <span class="job-title">{{ card.title || '长任务' }}</span>
      <el-tag size="small" :type="statusTagType">{{ statusLabel }}</el-tag>
    </div>
    <div v-if="card.summary" class="job-summary">{{ card.summary }}</div>
    <div class="job-meta">
      <span v-if="card.job_type">类型：{{ jobTypeLabel }}</span>
      <span v-if="card.job_id">#{{ card.job_id }}</span>
    </div>
    <div class="job-actions">
      <el-button
        v-if="card.report_url"
        size="small"
        type="primary"
        link
        @click="openReport"
      >
        打开报告
      </el-button>
      <el-button
        v-if="card.can_cancel"
        size="small"
        type="danger"
        plain
        :loading="cancelling"
        @click="$emit('cancel', card)"
      >
        停止
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  card: { type: Object, default: () => ({}) },
  cancelling: { type: Boolean, default: false }
})

defineEmits(['cancel'])

const router = useRouter()

const status = computed(() => String(props.card?.status || 'pending').toLowerCase())

const statusLabel = computed(() => {
  const map = {
    pending: '排队中',
    running: '执行中',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已停止'
  }
  return map[status.value] || status.value
})

const statusTagType = computed(() => {
  const map = {
    pending: 'info',
    running: 'warning',
    succeeded: 'success',
    failed: 'danger',
    cancelled: 'info'
  }
  return map[status.value] || 'info'
})

const jobTypeLabel = computed(() => {
  const t = props.card?.job_type
  if (t === 'browser_lab') return '智能浏览器'
  if (t === 'ui_agent') return 'UI Agent'
  if (t === 'qa_eval') return '问答评测'
  if (t === 'requirement_generate') return '需求生成'
  return t || '任务'
})

const openReport = () => {
  const url = props.card?.report_url
  if (!url) return
  if (url.startsWith('/')) {
    router.push(url)
  } else {
    window.open(url, '_blank')
  }
}
</script>

<style scoped lang="scss">
.job-progress-card {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
}
.job-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.job-title {
  font-weight: 600;
  font-size: 13px;
}
.job-summary {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  word-break: break-word;
}
.job-meta {
  margin-top: 6px;
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.job-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}
.status-running {
  border-color: var(--el-color-warning-light-5);
}
.status-succeeded {
  border-color: var(--el-color-success-light-5);
}
.status-failed {
  border-color: var(--el-color-danger-light-5);
}
</style>
