<template>
  <ConfigShell :embedded="embedded">
    <template #title>
      <b>数据保留</b>
    </template>
    <template #main>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="删除策略说明"
        description="配置 UI 用例运行记录的删除方式。逻辑删除仅从列表隐藏；物理删除立即从数据库清除；回收站模式删除后可在回收站恢复或永久删除。"
        style="margin-bottom: 20px; max-width: 960px;"
      />

      <el-form :model="form" label-width="160px" style="max-width: 960px;">
        <el-form-item label="用例运行记录删除">
          <el-radio-group v-model="form.ui_case_record_delete_mode">
            <el-radio value="logical">逻辑删除（从列表隐藏，不可恢复）</el-radio>
            <el-radio value="physical">物理删除（立即永久删除）</el-radio>
            <el-radio value="recycle_bin">回收站（可恢复或永久删除）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.update_time" label="最后修改">
          <span class="meta-text">{{ form.update_by || '—' }} · {{ form.update_time }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
        </el-form-item>
      </el-form>
    </template>
  </ConfigShell>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import ConfigShell from '@/components/ConfigShell.vue'
import { platformSettingsApi } from '@/api/modules/sys'

defineProps({
  embedded: { type: Boolean, default: false },
})

const form = reactive({
  ui_case_record_delete_mode: 'logical',
  update_by: '',
  update_time: '',
})

const saving = ref(false)

const loadConfig = async () => {
  try {
    const res = await platformSettingsApi.getConfig()
    const data = res?.data ?? res ?? {}
    Object.assign(form, {
      ui_case_record_delete_mode: data.ui_case_record_delete_mode || 'logical',
      update_by: data.update_by || '',
      update_time: data.update_time || '',
    })
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载配置失败')
  }
}

const saveConfig = async () => {
  saving.value = true
  try {
    const res = await platformSettingsApi.updateConfig({
      ui_case_record_delete_mode: form.ui_case_record_delete_mode,
    })
    const data = res?.data ?? res ?? {}
    Object.assign(form, data)
    ElMessage.success('数据保留配置已保存')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.meta-text {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
