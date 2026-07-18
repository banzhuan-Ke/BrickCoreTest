<template>
  <el-drawer
    v-model="visible"
    title="AI 失败分析"
    size="520px"
    destroy-on-close
    @closed="handleClosed"
  >
    <div v-loading="loading" class="failure-analyzer">
      <div class="toolbar">
        <div v-if="targetType === 'ui' || targetType === 'app'" class="vision-toggle-row">
          <el-switch
            v-model="useVision"
            active-text="截图识图"
            inactive-text="纯文本"
            size="small"
          />
          <span class="vision-hint">{{ useVision ? '结合失败截图，费用较高' : '仅分析步骤与日志，推荐' }}</span>
        </div>
        <el-select
          v-if="useVision && (targetType === 'ui' || targetType === 'app')"
          v-model="visionConfigId"
          clearable
          placeholder="Vision 模型（自动）"
          size="small"
          style="width: 100%; margin-bottom: 8px;"
        >
          <el-option
            v-for="c in visionConfigs"
            :key="'v' + c.id"
            :label="`${c.name} (${c.model})`"
            :value="c.id"
          />
        </el-select>
        <el-select
          v-model="textConfigId"
          clearable
          placeholder="分析模型（默认）"
          size="small"
          style="width: 100%;"
        >
          <el-option
            v-for="c in textConfigs"
            :key="'t' + c.id"
            :label="`${c.name} (${c.model})`"
            :value="c.id"
          />
        </el-select>
        <div class="toolbar-actions">
          <el-button size="small" :loading="loading" @click="runAnalyze(true)">重新分析</el-button>
          <el-button size="small" :disabled="!result?.root_cause" @click="copyResult">复制结论</el-button>
        </div>
      </div>

      <el-alert
        v-if="result?.vision_used"
        type="success"
        :closable="false"
        show-icon
        title="已结合失败步骤截图（Vision）进行分析"
        style="margin-bottom: 12px;"
      />
      <el-alert
        v-else-if="(targetType === 'ui' || targetType === 'app') && result"
        type="info"
        :closable="false"
        show-icon
        :title="'未使用 Vision：本次为纯文本分析，或无可读截图'"
        style="margin-bottom: 12px;"
      />

      <template v-if="result?.root_cause">
        <div class="result-block">
          <div class="block-label">根因总结</div>
          <div class="root-cause">{{ result.root_cause }}</div>
          <div class="meta-row">
            <el-tag v-if="result.category" size="small" type="danger">{{ result.category }}</el-tag>
            <span v-if="result.confidence != null" class="confidence">
              置信度 {{ Math.round(Number(result.confidence) * 100) }}%
            </span>
            <el-tag v-if="result.cached" size="small" type="info">历史分析</el-tag>
          </div>
          <el-progress
            v-if="result.confidence != null"
            :percentage="Math.round(Number(result.confidence) * 100)"
            :stroke-width="6"
            style="margin-top: 8px;"
          />
        </div>

        <div v-if="result.possible_causes?.length" class="result-block">
          <div class="block-label">可能原因</div>
          <ul class="bullet-list">
            <li v-for="(item, idx) in result.possible_causes" :key="'c' + idx">{{ item }}</li>
          </ul>
        </div>

        <div v-if="result.suggestions?.length" class="result-block">
          <div class="block-label">修复建议</div>
          <ul class="bullet-list suggestions">
            <li v-for="(item, idx) in result.suggestions" :key="'s' + idx">{{ item }}</li>
          </ul>
        </div>
      </template>

      <el-empty
        v-else-if="!loading && !parseFailed"
        description="暂无分析记录，点击「重新分析」开始"
      />

      <el-alert
        v-if="parseFailed"
        type="warning"
        :closable="false"
        show-icon
        title="未能解析为结构化 JSON，以下为 LLM 原始回复"
        style="margin-top: 12px;"
      />
      <pre v-if="parseFailed && result?.raw_response" class="raw-box">{{ result.raw_response }}</pre>

      <div v-if="result?.duration_ms" class="footer-meta">
        耗时 {{ result.duration_ms }}ms · Token {{ result.tokens_used || 0 }}
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { aiAnalyzeApi, aiConfigApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  targetType: { type: String, default: 'api' },
  targetId: { type: Number, default: null }
})

const emit = defineEmits(['update:modelValue'])

const proStore = ProjectStore()
const uStore = UserStore()

const loading = ref(false)
const result = ref(null)
const parseFailed = ref(false)
const textConfigId = ref(null)
const visionConfigId = ref(null)
const useVision = ref(false)
const configList = ref([])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const isVisionModel = (model) => {
  const m = (model || '').toLowerCase()
  return m.includes('vl') || m.includes('vision') || m.includes('gpt-4o')
}

const visionConfigs = computed(() => configList.value.filter(c => isVisionModel(c.model)))
const textConfigs = computed(() => configList.value.filter(c => !isVisionModel(c.model)))

const projectId = computed(() => proStore.projectInfo?.id)

const loadConfigs = async () => {
  if (!projectId.value) return
  try {
    let list = []
    try {
      const res = await aiConfigApi.getSelectOptions()
      if (res.data?.code === 200) {
        list = res.data.data || []
      }
    } catch {
      const res = await aiConfigApi.getList({ size: 200 })
      if (res.data?.code === 200) {
        list = res.data.data?.list || []
      }
    }
    configList.value = list.filter(c => c.is_enabled !== false)
    if (!textConfigId.value) {
      const def = textConfigs.value.find(c => c.is_default) || textConfigs.value[0]
      if (def) textConfigId.value = def.id
    }
  } catch {
    configList.value = []
  }
}

const loadCached = async () => {
  if (!props.targetId || !projectId.value) return false
  try {
    const res = await aiAnalyzeApi.getByTarget(props.targetType, props.targetId, projectId.value)
    if (res.data?.code === 200 && res.data.data?.root_cause) {
      result.value = res.data.data
      parseFailed.value = false
      if (props.targetType === 'ui' || props.targetType === 'app') {
        useVision.value = !!res.data.data.vision_used
      }
      return true
    }
  } catch {
    /* ignore */
  }
  return false
}

const runAnalyze = async (force = false) => {
  if (!uStore.hasPermission('ai_test:execute')) {
    ElMessage.warning('无 AI 分析权限（需要 ai_test:execute）')
    return
  }
  if (!props.targetId || !projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  loading.value = true
  parseFailed.value = false
  try {
    const res = await aiAnalyzeApi.analyzeFailure(
      {
        target_type: props.targetType,
        target_id: props.targetId,
        ai_config_id: textConfigId.value || undefined,
        vision_config_id: useVision.value ? (visionConfigId.value || undefined) : undefined,
        use_vision: useVision.value,
        force_refresh: force
      },
      projectId.value
    )
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      result.value = d
      parseFailed.value = !d.root_cause && !!d.raw_response
      if (d.root_cause) {
        ElMessage.success(res.data.message || '分析完成')
      } else if (parseFailed.value) {
        ElMessage.warning(res.data.message || '返回未能完全解析，请查看原始回复')
      }
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '分析失败')
  } finally {
    loading.value = false
  }
}

const copyResult = async () => {
  const r = result.value
  if (!r?.root_cause) return
  const lines = [
    `【根因】${r.root_cause}`,
    r.category ? `【分类】${r.category}` : '',
    r.possible_causes?.length ? `【可能原因】\n${r.possible_causes.map((x, i) => `${i + 1}. ${x}`).join('\n')}` : '',
    r.suggestions?.length ? `【修复建议】\n${r.suggestions.map((x, i) => `${i + 1}. ${x}`).join('\n')}` : ''
  ].filter(Boolean)
  try {
    await navigator.clipboard.writeText(lines.join('\n\n'))
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

const handleClosed = () => {
  result.value = null
  parseFailed.value = false
  useVision.value = false
  visionConfigId.value = null
}

watch(
  () => [props.modelValue, props.targetId, props.targetType],
  async ([open, id]) => {
    if (!open || !id) return
    await loadConfigs()
    result.value = null
    parseFailed.value = false
    await loadCached()
  }
)
</script>

<style scoped>
.failure-analyzer {
  min-height: 200px;
}
.toolbar {
  margin-bottom: 16px;
}
.vision-toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.vision-hint {
  font-size: 12px;
  color: #909399;
}
.toolbar-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.result-block {
  margin-bottom: 18px;
}
.block-label {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}
.root-cause {
  font-size: 15px;
  line-height: 1.6;
  color: #f56c6c;
  font-weight: 500;
}
.meta-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  flex-wrap: wrap;
}
.confidence {
  font-size: 12px;
  color: #909399;
}
.bullet-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.7;
  color: #303133;
}
.suggestions li {
  margin-bottom: 6px;
}
.raw-box {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow: auto;
}
.footer-meta {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
  text-align: right;
}
</style>
