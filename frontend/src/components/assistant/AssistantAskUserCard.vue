<template>
  <div class="ask-user-card" :class="{ 'is-loading': loading }">
    <div class="ask-title">需要补充信息</div>
    <div class="ask-question">{{ card.question }}</div>
    <div v-if="card.reason" class="ask-reason">{{ card.reason }}</div>
    <div v-if="fields.length" class="ask-fields">
      <div v-for="f in fields" :key="f.name" class="ask-field">
        <label>
          {{ f.label || f.name }}
          <span v-if="isFieldRequired(f)" class="req">*</span>
        </label>
        <el-select
          v-if="f.field_type === 'select' && visibleOptions(f).length"
          v-model="form[f.name]"
          size="small"
          clearable
          filterable
          :disabled="loading"
          :placeholder="f.placeholder || `请选择${f.label || f.name}`"
          style="width: 100%"
          @change="() => onSelectChange(f)"
        >
          <el-option
            v-for="opt in visibleOptions(f)"
            :key="String(opt.value)"
            :label="opt.label || String(opt.value)"
            :value="opt.value"
          />
        </el-select>
        <el-alert
          v-else-if="f.field_type === 'select' && !visibleOptions(f).length"
          type="warning"
          :closable="false"
          show-icon
          :title="f.placeholder || '暂无可选项，请先准备数据或确认 Runner 在线'"
        />
        <el-input
          v-else-if="f.field_type === 'number'"
          v-model="form[f.name]"
          size="small"
          type="number"
          :disabled="loading"
          :placeholder="f.placeholder || ''"
        />
        <el-input
          v-else-if="f.field_type === 'textarea'"
          v-model="form[f.name]"
          size="small"
          type="textarea"
          :rows="3"
          :disabled="loading"
          :maxlength="fieldMaxLength(f)"
          show-word-limit
          :placeholder="f.placeholder || ''"
        />
        <el-input
          v-else
          v-model="form[f.name]"
          size="small"
          :disabled="loading"
          :maxlength="fieldMaxLength(f)"
          :placeholder="f.placeholder || ''"
        />
      </div>
    </div>
    <div class="ask-actions">
      <el-button type="primary" size="small" :loading="loading" @click="submit">提交并继续</el-button>
      <el-button size="small" :disabled="loading" @click="$emit('cancel')">取消</el-button>
    </div>
  </div>
</template>

<script setup>
import { reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  card: { type: Object, required: true },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits(['submit', 'cancel'])

const fields = reactive([])
const form = reactive({})

const DEFAULT_MAX = {
  curl: 12000,
  response_sample: 8000,
  content: 200000,
  raw_element: 20000,
  query: 4000,
  description: 4000,
  prompt: 2000,
  intent: 500
}

const TIME_RANGE_MAX_HOURS = { '1d': 24, '7d': 168, '30d': 720 }

const fieldMaxLength = (f) => {
  const n = Number(f?.max_length)
  if (Number.isFinite(n) && n > 0) return Math.min(n, 500000)
  return DEFAULT_MAX[f?.name] || 2000
}

/** 需求 Chip：按 input_mode 动态必填 */
const isFieldRequired = (f) => {
  if (!f) return false
  if (Object.prototype.hasOwnProperty.call(form, 'input_mode')) {
    const mode = String(form.input_mode || '').trim().toLowerCase()
    if (f.name === 'requirement_id') return mode !== 'paste'
    if (f.name === 'content') return mode === 'paste'
    if (f.name === 'requirement_name') return false
  }
  return f.required !== false
}

const fieldSchemaKey = (card) => {
  const list = card?.fields || []
  return list.map((f) => `${f?.name}:${f?.field_type || ''}`).join('|')
}

const optionMatchesFilters = (opt, filterBy) => {
  const keys = Array.isArray(filterBy) ? filterBy : filterBy ? [filterBy] : []
  if (!keys.length) return true
  const meta = opt?.meta || {}
  for (const key of keys) {
    const selected = form[key]
    if (selected == null || String(selected).trim() === '') continue
    if (key === 'time_range') {
      const maxH = TIME_RANGE_MAX_HOURS[String(selected)]
      const hoursAgo = meta.hours_ago
      if (maxH != null && hoursAgo != null && Number(hoursAgo) > maxH) return false
      continue
    }
    if (key === 'target_type' && meta.target_type != null) {
      if (String(meta.target_type) !== String(selected)) return false
      continue
    }
    if (key === 'report_type' && meta.report_type != null) {
      if (String(meta.report_type) !== String(selected)) return false
      continue
    }
    // 通用：meta[key] 存在则匹配
    if (meta[key] != null && String(meta[key]) !== String(selected)) return false
  }
  return true
}

const visibleOptions = (f) => {
  const opts = f?.options || []
  if (!f?.filter_by) return opts
  return opts.filter((o) => optionMatchesFilters(o, f.filter_by))
}

const onSelectChange = (changedField) => {
  // 上游筛选变化时，清掉已选但不在可见列表中的下游值
  for (const f of fields) {
    if (f.field_type !== 'select' || !f.filter_by) continue
    const keys = Array.isArray(f.filter_by) ? f.filter_by : [f.filter_by]
    if (!keys.includes(changedField.name)) continue
    const cur = form[f.name]
    if (cur == null || String(cur).trim() === '') continue
    const still = visibleOptions(f).some((o) => String(o.value) === String(cur))
    if (!still) form[f.name] = ''
  }
}

const syncFields = () => {
  const next = (props.card?.fields || []).filter((f) => f?.name)
  fields.splice(0, fields.length, ...next)
  // 提交等待中不重置，避免父组件重渲染把已填内容清掉
  if (props.loading) return
  const keep = { ...form }
  Object.keys(form).forEach((k) => delete form[k])
  fields.forEach((f) => {
    if (keep[f.name] != null && String(keep[f.name]).trim() !== '') {
      form[f.name] = keep[f.name]
    } else if (f.default != null && String(f.default).trim() !== '') {
      form[f.name] = f.default
    } else {
      form[f.name] = ''
    }
  })
}

// 仅在换卡 / 字段结构变化时重建；勿 deep watch 整个 card
watch(
  () => [props.card?.ask_id, fieldSchemaKey(props.card)],
  () => syncFields(),
  { immediate: true }
)

const submit = () => {
  if (props.loading) return
  for (const f of fields) {
    if (f.field_type === 'select') {
      const opts = visibleOptions(f)
      if (!opts.length) {
        if (!isFieldRequired(f)) continue
        ElMessage.warning(f.placeholder || `暂无可选项：${f.label || f.name}`)
        return
      }
    }
    if (!isFieldRequired(f)) continue
    const v = form[f.name]
    if (v == null || String(v).trim() === '') {
      ElMessage.warning(`请填写：${f.label || f.name}`)
      return
    }
  }
  // 失败分析：允许只选失败域（分析该域近期）；仅填 ID 无域时才拦截
  if (
    Object.prototype.hasOwnProperty.call(form, 'target_type') &&
    (Object.prototype.hasOwnProperty.call(form, 'target_id') ||
      Object.prototype.hasOwnProperty.call(form, 'failure_ref'))
  ) {
    const hasType = form.target_type != null && String(form.target_type).trim() !== ''
    const hasId =
      (form.target_id != null && String(form.target_id).trim() !== '') ||
      (form.failure_ref != null && String(form.failure_ref).trim() !== '')
    if (hasId && !hasType) {
      ElMessage.warning('填写记录 ID 时请同时选择失败域，或不选记录以分析近期失败')
      return
    }
  }
  const answers = {}
  fields.forEach((f) => {
    const v = form[f.name]
    if (v != null && String(v).trim() !== '') {
      answers[f.name] = f.field_type === 'number' ? Number(v) : v
    }
  })
  emit('submit', answers)
}
</script>

<style scoped lang="scss">
.ask-user-card {
  margin-top: 8px;
  padding: 10px;
  border: 1px solid #b3d8ff;
  border-radius: 8px;
  background: #ecf5ff;

  &.is-loading {
    opacity: 0.92;
  }
}

.ask-title {
  font-size: 13px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 4px;
}

.ask-question {
  font-size: 13px;
  color: #303133;
  margin-bottom: 4px;
}

.ask-reason {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.ask-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

.ask-field label {
  display: block;
  font-size: 12px;
  color: #606266;
  margin-bottom: 4px;

  .req {
    color: #f56c6c;
  }
}

.ask-actions {
  display: flex;
  gap: 8px;
}
</style>
