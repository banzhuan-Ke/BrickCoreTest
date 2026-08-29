<template>
  <el-dialog
    v-model="visible"
    title="跨环境同步变量"
    width="720px"
    destroy-on-close
    @open="onOpen"
  >
    <el-alert type="info" :closable="false" show-icon class="mb-12">
      项目共享变量请用「项目共享变量」页签。此处用于各环境<strong>键结构相同、值可能不同</strong>的批量增删，或从某一环境复制相同值。
    </el-alert>

    <el-form label-width="110px">
      <el-form-item label="操作">
        <el-radio-group v-model="form.mode">
          <el-radio-button label="add_keys">批量新增键</el-radio-button>
          <el-radio-button label="delete_keys">批量删除键</el-radio-button>
          <el-radio-button label="sync_values">同步值</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item v-if="form.mode === 'sync_values'" label="源环境" required>
        <el-select v-model="form.source_env_id" placeholder="从哪个环境复制值" style="width: 100%">
          <el-option v-for="e in envList" :key="e.id" :label="e.name" :value="e.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="目标环境" required>
        <el-select
          v-model="form.target_env_ids"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="不选则应用到当前项目全部环境"
          style="width: 100%"
        >
          <el-option v-for="e in envList" :key="e.id" :label="e.name" :value="e.id" />
        </el-select>
      </el-form-item>

      <el-form-item v-if="form.mode === 'add_keys'" label="新增键名" required>
        <el-select
          v-model="form.keys"
          multiple
          filterable
          allow-create
          default-first-option
          placeholder="输入后回车添加，可多个"
          style="width: 100%"
        />
        <div class="hint">仅补缺：目标环境已有该键时不覆盖值</div>
      </el-form-item>

      <el-form-item v-else label="选择变量" required>
        <el-select
          v-model="form.keys"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          placeholder="勾选要对齐的变量名"
          style="width: 100%"
        >
          <el-option v-for="k in candidateKeys" :key="k" :label="k" :value="k" />
        </el-select>
        <div v-if="form.mode === 'sync_values'" class="hint">
          <el-checkbox v-model="form.overwrite">覆盖目标环境已有值</el-checkbox>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/index'
import { isReservedGlobalVarKey, userVarRows } from '@/utils/globalVars.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectId: { type: [Number, String], default: null },
  envList: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'done'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const saving = ref(false)
const form = reactive({
  mode: 'add_keys',
  source_env_id: null,
  target_env_ids: [],
  keys: [],
  overwrite: true,
})

const candidateKeys = computed(() => {
  const set = new Set()
  const source =
    form.mode === 'sync_values' && form.source_env_id
      ? props.envList.find((e) => e.id === form.source_env_id)
      : null
  const list = source ? [source] : props.envList
  for (const env of list) {
    for (const row of userVarRows(env.global_vars)) {
      set.add(row.key)
    }
  }
  return [...set].sort()
})

watch(
  () => form.mode,
  () => {
    form.keys = []
  }
)

function onOpen() {
  form.mode = 'add_keys'
  form.source_env_id = props.envList[0]?.id ?? null
  form.target_env_ids = []
  form.keys = []
  form.overwrite = true
}

async function submit() {
  if (!props.projectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!form.keys.length) {
    ElMessage.warning('请至少指定一个变量名')
    return
  }
  const reservedHit = form.keys.filter((k) => isReservedGlobalVarKey(k))
  const effectiveKeys = form.keys.filter((k) => !isReservedGlobalVarKey(k))
  if (!effectiveKeys.length) {
    ElMessage.warning('所选均为系统保留键（如 __ 开头），无法批量操作用户变量')
    return
  }
  if (reservedHit.length) {
    ElMessage.info(`已忽略系统保留键：${reservedHit.join('、')}`)
  }
  if (form.mode === 'sync_values' && !form.source_env_id) {
    ElMessage.warning('请选择源环境')
    return
  }

  const modeLabel =
    form.mode === 'add_keys' ? '批量新增键' : form.mode === 'delete_keys' ? '批量删除键' : '同步值'
  try {
    await ElMessageBox.confirm(
      `确认对选中环境执行「${modeLabel}」？共 ${effectiveKeys.length} 个变量。`,
      '确认操作',
      { type: 'warning' }
    )
  } catch {
    return
  }

  saving.value = true
  try {
    const res = await http.environmentApi.batchVars({
      project_id: Number(props.projectId),
      mode: form.mode,
      keys: effectiveKeys,
      target_env_ids: form.target_env_ids,
      source_env_id: form.mode === 'sync_values' ? form.source_env_id : undefined,
      overwrite: form.overwrite,
    })
    const data = res.data?.data ?? res.data
    ElMessage.success(`已更新 ${data?.updated_count ?? 0} 个环境`)
    visible.value = false
    emit('done')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '操作失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.mb-12 {
  margin-bottom: 12px;
}
.hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
