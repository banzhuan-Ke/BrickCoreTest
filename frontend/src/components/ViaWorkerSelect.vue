<template>
  <div class="via-worker-select" :class="{ 'is-env': isEnv }">
    <div class="via-worker-select__row">
      <el-checkbox
        v-if="!isEnv"
        v-model="enabled"
        @change="onEnabledChange"
      >{{ checkboxLabel }}</el-checkbox>
      <el-select
        :model-value="modelValue"
        :placeholder="isEnv ? '不选则执行时由平台本机发送' : '选择在线空闲执行机'"
        :size="size"
        clearable
        filterable
        :disabled="!isEnv && !enabled"
        class="via-worker-select__input"
        @update:model-value="onSelect"
      >
        <el-option
          v-for="w in idleWorkers"
          :key="w.id"
          :label="workerOptionLabel(w)"
          :value="w.id"
        />
      </el-select>
      <el-button
        link
        type="primary"
        :size="size"
        :loading="loading"
        @click="loadWorkers"
      >刷新</el-button>
      <el-tooltip :content="hint" placement="top" :show-after="200">
        <el-icon class="via-worker-tip"><QuestionFilled /></el-icon>
      </el-tooltip>
    </div>
    <span v-if="(isEnv || enabled) && emptyHint" class="via-worker-warn">
      {{ emptyHint }}
    </span>
    <div v-if="!isEnv && enabled && forceSerialHint" class="via-worker-serial">
      经执行机时将改为串行，并由执行机整包下发套件步骤
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { httpExecApi } from '@/api/modules/http'
import { getEnvDefaultPerfWorkerId } from '@/utils/caseDescription.js'

const props = defineProps({
  modelValue: { type: [Number, String], default: null },
  envId: { type: [Number, String], default: null },
  variant: { type: String, default: 'run' },
  forceSerialHint: { type: Boolean, default: false },
  autoPrefill: { type: Boolean, default: true },
  size: { type: String, default: 'default' },
  checkboxLabel: { type: String, default: '经执行机发送' },
  hintText: { type: String, default: '' },
  minEngine: { type: String, default: '1.0.0' },
  /** 仅列出 supports_df_proxy 的执行机（数据工厂代发） */
  requireDfProxy: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const proStore = ProjectStore()
const loading = ref(false)
const workers = ref([])
const enabled = ref(!!props.modelValue)
const prefilledWorkerId = ref(null)

const isEnv = computed(() => props.variant === 'env')
const minEngine = computed(() => props.minEngine || '1.0.0')
const hint = computed(() => {
  if (props.hintText) return props.hintText
  return isEnv.value
    ? '接口执行弹窗会预填此执行机，仍可改。数据工厂的 UI/App 库断言、套件前后 SQL、小测查库在选了此项后走该执行机（引擎 ≥ 1.8.2），失败不改回平台本机。不选则这些仍由平台本机连接。普通 HTTP 引擎 ≥ 1.0.0；form-data 与套件整包 ≥ 1.6.2。'
    : '平台服务器访问不到被测系统时，勾选后由执行机代发。默认仍本机发送。普通 HTTP ≥ 1.0.0；form-data 文件与套件/计划/定时整包 ≥ 1.6.2（单文件 ≤ 10MB、合计 ≤ 15MB）。失败不会静默改回本机，可取消勾选后本机重跑。'
})

const capableWorkers = computed(() => {
  let list = (workers.value || []).filter((w) => w && w.id)
  if (props.requireDfProxy) {
    list = list.filter((w) => w.supports_df_proxy !== false)
  }
  return list
})
const idleWorkers = computed(() =>
  capableWorkers.value.filter((w) => !w.current_record_id)
)
const busyWorkers = computed(() =>
  capableWorkers.value.filter((w) => w.current_record_id)
)
const emptyHint = computed(() => {
  if (idleWorkers.value.length) return ''
  if (busyWorkers.value.length) {
    const ids = busyWorkers.value.map((w) => `#${w.current_record_id}`).join('、')
    return `执行机忙碌（${ids}），完成后请刷新再勾选`
  }
  const extra = props.requireDfProxy ? '，且需支持数据工厂代发' : ''
  return `暂无在线可用执行机（需引擎 ≥ ${minEngine.value}${extra}）`
})

function workerOptionLabel(w) {
  const ver = w.engine_version || '?'
  let label = `${w.name} (#${w.id}) · ${w.host} · 引擎 ${ver}`
  if (w.supports_file_form === false) {
    label += ' · 不含文件 form-data'
  }
  if (props.forceSerialHint && w.supports_api_suite === false) {
    label += ' · 不含套件整包'
  }
  if (props.requireDfProxy && w.supports_df_proxy === false) {
    label += ' · 不含数据工厂代发'
  }
  return label
}

function parseIdleList(res) {
  const raw = res?.data ?? res
  return Array.isArray(raw) ? raw : (raw?.data ?? [])
}

async function loadWorkers() {
  const pid = proStore.projectInfo?.id
  if (!pid) {
    workers.value = []
    return
  }
  loading.value = true
  try {
    const res = await httpExecApi.listIdleWorkers({ project_id: pid })
    workers.value = parseIdleList(res)
  } catch (e) {
    console.error(e)
    workers.value = []
  } finally {
    loading.value = false
  }
}

function findEnv(envId) {
  const n = Number(envId)
  if (!Number.isFinite(n) || n <= 0) return null
  return (proStore.envList || []).find((e) => Number(e.id) === n) || null
}

function emitId(id) {
  emit('update:modelValue', Number.isFinite(id) && id > 0 ? id : null)
}

function onSelect(val) {
  const id = val == null || val === '' ? null : Number(val)
  prefilledWorkerId.value = null
  if (!isEnv.value && !id) {
    enabled.value = false
    emitId(null)
    return
  }
  emitId(id)
  if (!isEnv.value && id) enabled.value = true
}

async function onEnabledChange(checked) {
  if (!checked) {
    prefilledWorkerId.value = null
    emitId(null)
    return
  }
  await loadWorkers()
  if (!idleWorkers.value.length) {
    enabled.value = false
    ElMessage.warning(emptyHint.value || `暂无在线可用执行机（需引擎 ≥ ${minEngine.value}）`)
    return
  }
  if (!props.modelValue) {
    const envDef = getEnvDefaultPerfWorkerId(findEnv(props.envId)?.global_vars)
    const pick = idleWorkers.value.some((w) => w.id === envDef)
      ? envDef
      : idleWorkers.value[0].id
    prefilledWorkerId.value = pick
    emitId(pick)
  }
}

function applyEnvDefault(envId) {
  if (isEnv.value || !props.autoPrefill) return
  const def = getEnvDefaultPerfWorkerId(findEnv(envId)?.global_vars)
  if (!def) {
    prefilledWorkerId.value = null
    enabled.value = false
    emitId(null)
    return
  }
  if (props.requireDfProxy) {
    // 数据工厂代发：环境默认机若引擎不足，勿自动勾选
    void (async () => {
      await loadWorkers()
      const ok = idleWorkers.value.some((w) => Number(w.id) === Number(def))
      if (ok) {
        prefilledWorkerId.value = def
        enabled.value = true
        emitId(def)
      } else {
        prefilledWorkerId.value = null
        enabled.value = false
        emitId(null)
      }
    })()
    return
  }
  prefilledWorkerId.value = def
  enabled.value = !!def
  emitId(def)
}

watch(() => props.modelValue, (val) => {
  enabled.value = !!(val != null && val !== '' && Number(val) > 0)
})

watch(() => props.envId, (id) => {
  const current = props.modelValue == null || props.modelValue === '' ? null : Number(props.modelValue)
  const pref = prefilledWorkerId.value == null ? null : Number(prefilledWorkerId.value)
  if (current == null || (pref != null && current === pref)) {
    applyEnvDefault(id)
  }
})

onMounted(() => {
  loadWorkers()
  if (props.modelValue) {
    enabled.value = true
  } else if (props.envId) {
    applyEnvDefault(props.envId)
  }
})

defineExpose({ loadWorkers })
</script>

<style scoped>
.via-worker-select {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  width: 100%;
  min-width: 0;
}
.via-worker-select__row {
  display: flex;
  align-items: center;
  gap: 6px 8px;
  width: 100%;
  min-width: 0;
}
.via-worker-select__input {
  flex: 1;
  min-width: 0;
}
.via-worker-tip {
  flex-shrink: 0;
  font-size: 14px;
  color: #909399;
  cursor: help;
  vertical-align: middle;
}
.via-worker-tip:hover {
  color: var(--el-color-primary);
}
.via-worker-warn {
  color: var(--el-color-warning);
  font-size: 12px;
  line-height: 1.4;
}
.via-worker-serial {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
  padding-left: 22px;
}
</style>
