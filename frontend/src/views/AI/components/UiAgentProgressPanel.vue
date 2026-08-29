<template>

  <div v-if="visible" class="ui-agent-progress">

    <div class="progress-header">

      <span class="title">{{ title }}</span>

      <el-tag v-if="jobStatus" size="small" :type="statusTagType">{{ statusLabel }}</el-tag>

      <el-button

        v-if="canStop"

        type="danger"

        size="small"

        link

        :loading="stopping"

        @click="handleStop"

      >

        停止

      </el-button>

    </div>



    <el-row :gutter="16">

      <el-col :span="14">

        <div class="panel-title">探索日志</div>

        <div ref="logRef" class="log-panel">

          <div v-if="!displayedLogs.length" class="empty-hint">{{ waitingHint }}</div>

          <div

            v-for="(entry, idx) in displayedLogs"

            :key="idx"

            class="log-line"

          >

            <span>{{ formatEntry(entry) }}</span>

          </div>

        </div>

      </el-col>

      <el-col :span="10">

        <div class="panel-title">已产出步骤（{{ displayedSteps.length }}）</div>

        <div class="steps-panel">

          <div v-if="!displayedSteps.length" class="empty-hint">步骤将随探索逐步追加</div>

          <div

            v-for="(step, idx) in displayedSteps"

            :key="step.id || idx"

            class="step-line"

          >

            <span class="step-idx">#{{ idx + 1 }}</span>

            <el-tag size="small" type="primary">{{ step.keyword || step.method }}</el-tag>

            <span class="step-desc">{{ step.desc }}</span>

          </div>

        </div>

      </el-col>

    </el-row>



    <el-alert

      v-if="errorMessage"

      :title="errorMessage"

      type="error"

      show-icon

      :closable="false"

      class="error-alert"

    />

  </div>

</template>



<script setup>

import { computed, nextTick, ref, watch } from 'vue'

import { ElMessage } from 'element-plus'

import { aiGenerateApi } from '@/api/modules/ai'

import { useUiAgentJobPoll } from '@/composables/useUiAgentJobPoll.js'



const props = defineProps({

  jobId: { type: Number, default: null },

  projectId: { type: [Number, String], default: null },

  visible: { type: Boolean, default: false },

  title: { type: String, default: 'Agent 探索进度' },

  waitingHint: { type: String, default: '等待任务上报…' },

})



const emit = defineEmits(['done', 'fail', 'stopped'])



const stopping = ref(false)

const logRef = ref(null)



const {

  displayedLogs,

  displayedSteps,

  jobStatus,

  jobData,

  errorMessage,

  start,

  stop,

} = useUiAgentJobPoll()



const canStop = computed(() => ['pending', 'running', 'stopping', ''].includes(displayStatus.value))

const displayStatus = computed(() => {
  if (jobData.value?.stop_requested && ['pending', 'running'].includes(jobStatus.value)) {
    return 'stopping'
  }
  return jobStatus.value
})

const statusLabel = computed(() => {
  const map = {
    pending: '等待中',
    running: '探索中',
    stopping: '停止中',
    done: '已完成',
    failed: '失败',
    stopped: '已停止',
  }
  return map[displayStatus.value] || displayStatus.value || '连接中'
})

const statusTagType = computed(() => {
  if (displayStatus.value === 'done') return 'success'
  if (displayStatus.value === 'failed') return 'danger'
  if (displayStatus.value === 'stopped' || displayStatus.value === 'stopping') return 'warning'
  return 'info'
})



function formatEntry(entry) {

  const phase = entry.phase || ''

  const msg = entry.message || entry.error || (entry.done ? (entry.message || '完成') : '')

  const step = entry.step_index != null ? `[${entry.step_index}] ` : ''

  return `${step}${phase ? phase + ': ' : ''}${msg || JSON.stringify(entry)}`

}



function scrollLog() {

  nextTick(() => {

    const el = logRef.value

    if (el) el.scrollTop = el.scrollHeight

  })

}



watch(displayedLogs, scrollLog, { deep: true })



async function handleStop() {

  if (!props.jobId) return

  stopping.value = true

  try {

    await aiGenerateApi.stopUiAgentJob(props.jobId, props.projectId)

    ElMessage.success('已发送停止请求')

  } catch (e) {

    ElMessage.error(e.response?.data?.detail || '停止失败')

  } finally {

    stopping.value = false

  }

}



watch(

  () => [props.visible, props.jobId],

  ([vis, id]) => {

    if (vis && id) {

      start(id, props.projectId, {

        onDone(job) {

          emit('done', job)

        },

        onFail(payload) {

          emit('fail', payload)

        },

      })

    } else {

      stop()

    }

  },

  { immediate: true },

)



defineExpose({ displayedSteps, displayedLogs, jobStatus, jobData })

</script>



<style scoped>

.ui-agent-progress {

  margin-top: 12px;

}

.progress-header {

  display: flex;

  align-items: center;

  gap: 10px;

  margin-bottom: 10px;

}

.title {

  font-weight: 600;

}

.panel-title {

  font-size: 13px;

  color: var(--el-text-color-secondary);

  margin-bottom: 6px;

}

.log-panel,

.steps-panel {

  border: 1px solid var(--el-border-color-lighter);

  border-radius: 6px;

  padding: 8px 10px;

  height: 220px;

  overflow-y: auto;

  font-size: 12px;

  background: var(--el-fill-color-blank);

}

.log-line {

  margin-bottom: 6px;

  line-height: 1.45;

  word-break: break-word;

}

.step-line {

  display: flex;

  align-items: center;

  gap: 6px;

  margin-bottom: 8px;

}

.step-idx {

  color: var(--el-text-color-secondary);

  min-width: 28px;

}

.step-desc {

  flex: 1;

  overflow: hidden;

  text-overflow: ellipsis;

  white-space: nowrap;

}

.empty-hint {

  color: var(--el-text-color-placeholder);

}

.error-alert {

  margin-top: 10px;

}

</style>


