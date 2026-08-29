<template>
  <el-dialog
    :model-value="modelValue"
    title="纳入测试版本"
    width="520px"
    destroy-on-close
    @close="emit('update:modelValue', false)"
  >
    <el-form label-width="90px">
      <el-form-item label="目标版本" required>
        <el-select v-model="releaseId" filterable style="width: 100%" placeholder="选择版本">
          <el-option
            v-for="r in releases"
            :key="r.id"
            :label="`${r.release_key} — ${r.name}`"
            :value="r.id"
            :disabled="['released', 'archived'].includes(r.status)"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="纳入后风险">
        <el-select v-model="riskLevel" style="width: 160px">
          <el-option label="低" value="low" />
          <el-option label="中" value="medium" />
          <el-option label="高" value="high" />
          <el-option label="严重" value="critical" />
        </el-select>
        <div class="field-hint">用于质量门禁统计，可在版本范围列表中单独调整</div>
      </el-form-item>
      <el-form-item label="已选用例">
        <span>{{ caseIds.length }} 条</span>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!releaseId || !caseIds.length" :loading="saving" @click="submit">
        纳入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { testReleaseApi } from '@/api/testManagement'

const props = defineProps({
  modelValue: Boolean,
  projectId: { type: Number, required: true },
  caseIds: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue', 'done'])

const releases = ref([])
const releaseId = ref(null)
const riskLevel = ref('medium')
const saving = ref(false)

const loadReleases = async () => {
  const res = await testReleaseApi.list({ project_id: props.projectId })
  releases.value = (res.data?.data || []).filter((r) => !['released', 'archived'].includes(r.status))
}

const submit = async () => {
  saving.value = true
  try {
    const res = await testReleaseApi.addScopes(releaseId.value, props.projectId, {
      functional_case_ids: props.caseIds,
      risk_level: riskLevel.value
    })
    const d = res.data?.data || {}
    ElMessage.success(`新增 ${d.created_count || 0}，已存在 ${d.existing_count || 0}`)
    emit('update:modelValue', false)
    emit('done', releaseId.value)
  } finally {
    saving.value = false
  }
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      releaseId.value = null
      loadReleases()
    }
  }
)
</script>

<style scoped>
.field-hint {
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
}
</style>
