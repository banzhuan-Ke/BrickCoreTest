<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑范围项"
    width="480px"
    destroy-on-close
    @close="emit('update:modelValue', false)"
  >
    <el-form :model="form" label-width="90px">
      <el-form-item label="用例">
        <span>{{ scope?.case_title || `#${scope?.functional_case_id}` }}</span>
      </el-form-item>
      <el-form-item label="风险">
        <el-select v-model="form.risk_level" style="width: 160px">
          <el-option label="低" value="low" />
          <el-option label="中" value="medium" />
          <el-option label="高" value="high" />
          <el-option label="严重" value="critical" />
        </el-select>
      </el-form-item>
      <el-form-item label="范围状态">
        <el-select v-model="form.scope_status" style="width: 160px">
          <el-option label="计划中" value="planned" />
          <el-option label="就绪" value="ready" />
          <el-option label="阻塞" value="blocked" />
          <el-option label="不适用" value="not_applicable" />
          <el-option label="已完成" value="completed" />
        </el-select>
      </el-form-item>
      <el-form-item label="负责人">
        <ProjectMemberSelect
          v-if="projectId"
          v-model="form.owner_id"
          :project-id="projectId"
          placeholder="选择负责人（可选）"
          width="100%"
        />
      </el-form-item>
      <el-form-item label="关联需求">
        <el-select
          v-model="form.requirement_key"
          clearable
          filterable
          placeholder="选择当前版本需求"
          style="width: 100%"
        >
          <el-option
            v-for="r in requirementOptions"
            :key="r.requirement_key"
            :label="reqLabel(r)"
            :value="r.requirement_key"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.note" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { testReleaseApi } from '@/api/testManagement'
import ProjectMemberSelect from './ProjectMemberSelect.vue'

const props = defineProps({
  modelValue: Boolean,
  releaseId: { type: Number, required: true },
  projectId: { type: Number, required: true },
  scope: { type: Object, default: null },
  /** 版本已关联需求列表（来自 listRequirements） */
  requirements: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue', 'done'])

const saving = ref(false)
const form = reactive({
  risk_level: 'medium',
  scope_status: 'planned',
  owner_id: null,
  requirement_key: '',
  note: ''
})

const requirementOptions = computed(() => {
  const list = Array.isArray(props.requirements) ? props.requirements : []
  const key = String(form.requirement_key || '').trim()
  const mapped = list
    .filter((r) => r && r.requirement_key)
    .map((r) => ({
      requirement_key: String(r.requirement_key),
      title: r.title || r.name || r.requirement_name || ''
    }))
  // 若当前值不在版本需求列表中（历史手工编号），仍保留可选以免清空丢数据
  if (key && !mapped.some((r) => r.requirement_key === key)) {
    mapped.unshift({ requirement_key: key, title: '（当前值，不在版本需求列表）' })
  }
  return mapped
})

const reqLabel = (r) => {
  const title = String(r.title || '').trim()
  const key = String(r.requirement_key || '').trim()
  if (title && key) return `${title}（${key}）`
  return title || key || '—'
}

const resetForm = () => {
  const s = props.scope || {}
  form.risk_level = s.risk_level || 'medium'
  form.scope_status = s.scope_status || 'planned'
  form.owner_id = s.owner_id ?? null
  form.requirement_key = s.requirement_key || ''
  form.note = s.note || ''
}

const submit = async () => {
  if (!props.scope?.id) return
  saving.value = true
  try {
    await testReleaseApi.updateScope(props.releaseId, props.scope.id, props.projectId, {
      risk_level: form.risk_level,
      scope_status: form.scope_status,
      owner_id: form.owner_id || null,
      requirement_key: form.requirement_key || null,
      note: form.note || null
    })
    ElMessage.success('已保存')
    emit('update:modelValue', false)
    emit('done')
  } finally {
    saving.value = false
  }
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) resetForm()
  }
)
</script>

<style scoped>
</style>
