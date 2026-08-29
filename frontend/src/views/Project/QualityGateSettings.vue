<template>
  <div class="tm-quality-gate-settings" v-loading="loading">
    <TmPremiumBanner />
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
      title="版本质量门禁阈值"
      description="用于版本质量预览、快照与就绪/发布判定。比率类填 0–100（保存为 0–1）；缺陷与高风险缺口为整数上限。"
    />
    <el-form label-width="180px" style="max-width: 640px">
      <el-form-item label="必测完成率 ≥">
        <el-input-number
          v-model="form.required_completion_pct"
          :min="0"
          :max="100"
          :step="1"
          :disabled="!canEdit"
        />
        <span class="hint">%</span>
      </el-form-item>
      <el-form-item label="必测通过率 ≥">
        <el-input-number
          v-model="form.required_pass_rate_pct"
          :min="0"
          :max="100"
          :step="1"
          :disabled="!canEdit"
        />
        <span class="hint">%</span>
      </el-form-item>
      <el-form-item label="阻塞级未关闭 ≤">
        <el-input-number v-model="form.blocker_open_max" :min="0" :disabled="!canEdit" />
      </el-form-item>
      <el-form-item label="严重级未关闭 ≤">
        <el-input-number v-model="form.critical_open_max" :min="0" :disabled="!canEdit" />
      </el-form-item>
      <el-form-item label="高风险无结果 ≤">
        <el-input-number
          v-model="form.high_risk_without_result_max"
          :min="0"
          :disabled="!canEdit"
        />
      </el-form-item>
      <el-form-item>
        <el-button v-if="canEdit" type="primary" :loading="saving" @click="save">保存</el-button>
        <el-button @click="load">刷新</el-button>
        <el-button link type="primary" @click="resetDefaults">恢复默认</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { projectSettingsApi } from '@/api/modules/sys'
import { ProjectStore } from '@/stores/module/ProjectStore'
import TmPremiumBanner from '@/components/TmPremiumBanner.vue'

defineProps({
  canEdit: { type: Boolean, default: false }
})

const proStore = ProjectStore()
const loading = ref(false)
const saving = ref(false)
const form = reactive({
  required_completion_pct: 100,
  required_pass_rate_pct: 95,
  blocker_open_max: 0,
  critical_open_max: 0,
  high_risk_without_result_max: 0
})

const applyData = (data) => {
  Object.assign(form, {
    required_completion_pct: Math.round(Number(data.required_completion_min ?? 1) * 100),
    required_pass_rate_pct: Math.round(Number(data.required_pass_rate_min ?? 0.95) * 100),
    blocker_open_max: data.blocker_open_max ?? 0,
    critical_open_max: data.critical_open_max ?? 0,
    high_risk_without_result_max: data.high_risk_without_result_max ?? 0
  })
}

const toPayload = () => ({
  required_completion_min: Number(form.required_completion_pct) / 100,
  required_pass_rate_min: Number(form.required_pass_rate_pct) / 100,
  blocker_open_max: form.blocker_open_max,
  critical_open_max: form.critical_open_max,
  high_risk_without_result_max: form.high_risk_without_result_max
})

const load = async () => {
  const pid = proStore.projectInfo?.id
  if (!pid) return
  loading.value = true
  try {
    const res = await projectSettingsApi.getQualityGateSettings(pid)
    applyData(res.data?.data || {})
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

const save = async () => {
  const pid = proStore.projectInfo?.id
  if (!pid) {
    ElMessage.warning('请先选择项目')
    return
  }
  saving.value = true
  try {
    const res = await projectSettingsApi.updateQualityGateSettings(pid, toPayload())
    applyData(res.data?.data || toPayload())
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const resetDefaults = () => {
  applyData({
    required_completion_min: 1,
    required_pass_rate_min: 0.95,
    blocker_open_max: 0,
    critical_open_max: 0,
    high_risk_without_result_max: 0
  })
}

watch(() => proStore.projectInfo?.id, () => load())
onMounted(load)
</script>

<style scoped>
.hint {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
</style>
