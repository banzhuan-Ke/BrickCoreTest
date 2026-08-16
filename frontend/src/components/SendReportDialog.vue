<template>
  <el-dialog
    :model-value="modelValue"
    title="发送报告"
    width="520px"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 14px;"
    >
      <template #title>
        邮件可附完整 HTML；钉钉 / 企微 / 飞书仅摘要。发送结果可在「系统管理 → 通知日志」核对是否真正成功。
      </template>
    </el-alert>
    <div v-loading="loading" style="min-height: 80px;">
      <div v-if="!loading && enabledConfigs.length === 0" style="color: #909399; font-size: 13px; line-height: 1.6;">
        当前项目没有已启用的通知配置。请先到「项目设置 → 通知配置」添加并启用。
      </div>
      <el-checkbox-group v-else v-model="selectedIds" style="display: flex; flex-direction: column; gap: 10px;">
        <el-checkbox
          v-for="cfg in enabledConfigs"
          :key="cfg.id"
          :value="cfg.id"
        >
          <span style="display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <el-tag size="small" :type="channelTagType(cfg.channel_type)">{{ channelLabel(cfg.channel_type) }}</el-tag>
            <span style="color: #606266;">{{ configSummary(cfg) }}</span>
            <span v-if="cfg.channel_type !== 'email'" style="color: #909399; font-size: 12px;">（仅摘要）</span>
            <span v-else style="color: #909399; font-size: 12px;">（含 HTML 附件）</span>
          </span>
        </el-checkbox>
      </el-checkbox-group>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="sending" :disabled="!selectedIds.length" @click="confirmSend">
        发送
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectId: { type: [Number, String], required: true },
  /** async (configIds: number[]) => response */
  sendFn: { type: Function, required: true },
})

const emit = defineEmits(['update:modelValue', 'sent'])

const loading = ref(false)
const sending = ref(false)
const configs = ref([])
const selectedIds = ref([])

const enabledConfigs = computed(() => (configs.value || []).filter((c) => c.enabled))

const channelLabel = (type) =>
  ({ email: '邮件', dingtalk: '钉钉', wechat: '企微', feishu: '飞书' }[type] || type)

const channelTagType = (type) =>
  ({ email: 'primary', dingtalk: 'warning', wechat: 'success', feishu: 'info' }[type] || '')

const configSummary = (cfg) => {
  const c = cfg.config || {}
  if (cfg.channel_type === 'email') {
    const list = c.recipients || []
    return list.length ? list.join(', ') : '未配置收件人'
  }
  const url = c.webhook_url || ''
  if (!url) return '未配置 Webhook'
  return url.length > 48 ? `${url.slice(0, 48)}…` : url
}

const loadConfigs = async () => {
  loading.value = true
  try {
    const res = await http.notificationApi.getSendTargets(Number(props.projectId))
    configs.value = res.data || []
    // 默认勾选全部启用项，方便一次多发
    selectedIds.value = enabledConfigs.value.map((c) => c.id)
  } catch (e) {
    configs.value = []
    selectedIds.value = []
    ElMessage.error(e?.response?.data?.detail || '加载通知配置失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) loadConfigs()
  },
)

const confirmSend = async () => {
  if (!selectedIds.value.length) {
    ElMessage.warning('请至少选择一个通知渠道')
    return
  }
  const picked = enabledConfigs.value.filter((c) => selectedIds.value.includes(c.id))
  const hasEmail = picked.some((c) => c.channel_type === 'email')
  sending.value = true
  try {
    const res = await props.sendFn([...selectedIds.value])
    const detail = res?.data?.detail || res?.data?.msg || '报告已发送'
    if (!hasEmail) {
      ElMessage.success({
        message: `${detail}（本次未勾选邮件，邮箱不会收到）`,
        duration: 7000,
      })
    } else {
      ElMessage.success({ message: detail, duration: 8000 })
    }
    emit('sent', selectedIds.value)
    emit('update:modelValue', false)
  } catch (e) {
    ElMessage.error({
      message: e?.response?.data?.detail || e?.data?.detail || '发送失败',
      duration: 8000,
    })
  } finally {
    sending.value = false
  }
}
</script>
