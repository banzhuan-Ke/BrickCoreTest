<template>
  <el-dialog
    v-model="visible"
    title="AI 优化步骤"
    width="720px"
    destroy-on-close
    append-to-body
    @open="handleOpen"
  >
    <div class="optimize-dialog">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="精简冗余操作、优化步骤描述，可选基于预期结果补充断言。优化后请核对定位与断言再保存。"
      />

      <p class="step-summary">当前用例共 <strong>{{ sourceSteps.length }}</strong> 个步骤</p>

      <el-form label-width="88px">
        <el-form-item label="测试描述">
          <el-input
            v-model="description"
            type="textarea"
            :rows="4"
            placeholder="建议补充：操作路径 + 预期结果（勾选补充断言时必填预期部分）"
          />
        </el-form-item>
        <el-form-item label="AI 模型">
          <el-select
            v-model="aiConfigId"
            placeholder="默认模型"
            clearable
            style="width: 100%"
            :loading="loadingConfigs"
          >
            <el-option
              v-for="c in enabledConfigs"
              :key="c.id"
              :label="`${c.name} (${c.model})`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="优化选项">
          <el-checkbox v-model="optimizeOptions.append_assertions">补充断言（基于描述中的预期）</el-checkbox>
        </el-form-item>
      </el-form>

      <div v-if="optimizedSteps.length" class="result-section">
        <el-radio-group v-model="stepVersion" size="small">
          <el-radio-button label="original">优化前 ({{ sourceSteps.length }} 步)</el-radio-button>
          <el-radio-button label="optimized">
            优化后 ({{ optimizedSteps.length }} 步
            <template v-if="lastStats.assertions_count">，含 {{ lastStats.assertions_count }} 断言</template>)
          </el-radio-button>
        </el-radio-group>
        <div v-if="lastStats.risk_steps_count" class="risk-hint">
          有 {{ lastStats.risk_steps_count }} 步存在定位风险，应用前请核对
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="warning" :loading="optimizing" @click="handleOptimize">
        <el-icon><MagicStick /></el-icon>
        {{ optimizing ? 'AI 优化中...' : (optimizedSteps.length ? '重新优化' : '开始优化') }}
      </el-button>
      <el-button
        type="primary"
        :disabled="!optimizedSteps.length"
        @click="handleApply"
      >
        应用到用例
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { aiRecordApi } from '@/api/modules/ai.js'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  steps: { type: Array, default: () => [] },
  initialDescription: { type: String, default: '' },
  projectId: { type: [Number, String], default: null },
  /** ui | app */
  stepModule: { type: String, default: 'ui' },
})

const emit = defineEmits(['update:modelValue', 'apply'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const { aiConfigId, enabledConfigs, loadingConfigs, loadConfigs } = useAiConfigSelect()

const description = ref('')
const optimizing = ref(false)
const optimizedSteps = ref([])
const stepVersion = ref('optimized')
const sourceSteps = ref([])

const optimizeOptions = reactive({
  append_assertions: true,
})

const lastStats = reactive({
  trimmed_count: 0,
  assertions_count: 0,
  risk_steps_count: 0,
  llm_applied: true,
  fallback_reason: '',
  assertions_skipped_reason: '',
})

function resetState() {
  description.value = props.initialDescription || ''
  optimizedSteps.value = []
  stepVersion.value = 'optimized'
  sourceSteps.value = JSON.parse(JSON.stringify(props.steps || []))
  lastStats.trimmed_count = 0
  lastStats.assertions_count = 0
  lastStats.risk_steps_count = 0
  lastStats.llm_applied = true
  lastStats.fallback_reason = ''
  lastStats.assertions_skipped_reason = ''
}

function handleOpen() {
  resetState()
  loadConfigs()
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) handleOpen()
  }
)

const handleOptimize = async () => {
  if (!sourceSteps.value.length) {
    ElMessage.warning('当前没有可优化的步骤')
    return
  }
  optimizing.value = true
  try {
    const res = await aiRecordApi.optimizeSteps({
      steps: sourceSteps.value,
      description: description.value,
      ai_config_id: aiConfigId.value || undefined,
      append_assertions: optimizeOptions.append_assertions,
      use_page_context: false,
      project_id: props.projectId ? Number(props.projectId) : undefined,
      step_module: props.stepModule || 'ui',
    })
    if (res.status === 200 && res.data?.code === 200) {
      const d = res.data.data || {}
      optimizedSteps.value = d.optimized_steps || []
      lastStats.trimmed_count = d.trimmed_count || 0
      lastStats.assertions_count = d.assertions_count || 0
      lastStats.risk_steps_count = d.risk_steps_count || 0
      lastStats.llm_applied = d.llm_applied !== false
      lastStats.fallback_reason = d.fallback_reason || ''
      lastStats.assertions_skipped_reason = d.assertions_skipped_reason || ''
      stepVersion.value = 'optimized'
      if (!lastStats.llm_applied || lastStats.fallback_reason) {
        ElMessage.warning(
          lastStats.fallback_reason
            ? `AI 优化未完全生效（${lastStats.fallback_reason}），请核对步骤`
            : 'AI 优化未生效，请核对或重试'
        )
      } else if (d.no_change) {
        ElMessage.info('AI 已完成描述优化，操作步骤与参数基本未变')
      } else {
        const parts = ['AI 优化完成']
        if (d.original_count && d.optimized_count && d.original_count > d.optimized_count) {
          parts.push(`精简 ${d.original_count - d.optimized_count} 步`)
        } else if (lastStats.trimmed_count) {
          parts.push(`精简 ${lastStats.trimmed_count} 步`)
        }
        if (lastStats.assertions_count) parts.push(`断言 ${lastStats.assertions_count} 条`)
        if (lastStats.assertions_skipped_reason === 'no_expectations_in_description' && optimizeOptions.append_assertions) {
          parts.push('未补充断言（描述中缺少「预期」）')
        }
        if (lastStats.risk_steps_count) parts.push(`${lastStats.risk_steps_count} 步需核对`)
        ElMessage.success(parts.join('，'))
      }
    } else {
      ElMessage.error(res.data?.message || 'AI 优化失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || 'AI 优化失败')
  } finally {
    optimizing.value = false
  }
}

const handleApply = async () => {
  const target = stepVersion.value === 'optimized' ? optimizedSteps.value : sourceSteps.value
  if (!target.length) {
    ElMessage.warning('没有可应用的步骤')
    return
  }
  const risks = target.filter(s => s.meta?.quality?.level === 'risk')
  if (risks.length > 0) {
    try {
      await ElMessageBox.confirm(
        `有 ${risks.length} 个步骤标记为「风险」，仍要应用到用例吗？`,
        '定位风险确认',
        { type: 'warning', confirmButtonText: '仍要应用', cancelButtonText: '返回修改' }
      )
    } catch {
      return
    }
  }
  emit('apply', JSON.parse(JSON.stringify(target)))
  visible.value = false
}
</script>

<style scoped>
.optimize-dialog {
  max-height: 65vh;
  overflow-y: auto;
}
.step-summary {
  margin: 0 0 12px;
  color: #606266;
  font-size: 14px;
}
.result-section {
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px dashed #ebeef5;
}
.risk-hint {
  margin-top: 8px;
  font-size: 13px;
  color: #e6a23c;
}
</style>
