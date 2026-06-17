<template>
  <ConfigShell :embedded="embedded">
    <template #title>
      <b>MCP 配置</b>
    </template>
    <template #main>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="客户端配置说明"
        description="HTTP 类 AI 客户端（如 Kimi Code）请在 headers 中填写 Authorization: Bearer <API Key>，不要写在环境变量里。接入地址与 JSON 见：数据看板 → 首页看板 → BrickCore MCP Server；详细步骤见文档中心 → MCP 外部接入。"
        style="margin-bottom: 16px; max-width: 720px;"
      />
      <el-alert
        v-if="form.using_env_fallback"
        type="info"
        :closable="false"
        show-icon
        title="当前仍使用环境变量兜底"
        description="保存后将写入平台配置，之后可在页面修改启用状态、对外地址与 API Key，无需重建镜像。"
        style="margin-bottom: 16px; max-width: 720px;"
      />
      <el-form :model="form" label-width="140px" style="max-width: 720px;">
        <el-form-item label="启用 MCP Server：">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="平台对外地址：">
          <el-input
            v-model="form.base_url"
            placeholder="如：https://test.company.com（用于生成客户端接入 URL）"
          />
        </el-form-item>
        <el-form-item label="接入路径：">
          <el-input :model-value="form.http_path" disabled />
          <div class="field-hint">由部署环境变量 MCP_HTTP_PATH 控制，修改需同步 Nginx 并重启</div>
        </el-form-item>
        <el-form-item label="MCP API Key：">
          <el-input
            v-model="apiKeyInput"
            type="password"
            show-password
            placeholder="留空表示不修改；首次保存可填写新密钥"
          />
          <div v-if="form.has_api_key" class="field-hint">当前密钥：{{ form.api_key_masked }}</div>
        </el-form-item>
        <el-form-item v-if="form.update_time" label="最近更新：">
          <span class="meta-text">{{ form.update_by || '-' }} · {{ form.update_time }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveConfig" icon="Check">保存 MCP 配置</el-button>
          <el-button @click="loadConfig" icon="Refresh">刷新</el-button>
        </el-form-item>
      </el-form>
    </template>
  </ConfigShell>
</template>

<script setup>
import ConfigShell from '@/components/ConfigShell.vue'

defineProps({
  embedded: { type: Boolean, default: false }
})

import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { mcpApi } from '@/api/modules/sys.js'

const form = reactive({
  enabled: true,
  base_url: '',
  http_path: '',
  api_key_masked: '',
  has_api_key: false,
  using_env_fallback: true,
  update_by: '',
  update_time: ''
})
const apiKeyInput = ref('')

const loadConfig = async () => {
  try {
    const res = await mcpApi.getConfig()
    const data = res.data || res
    Object.assign(form, data)
    apiKeyInput.value = ''
  } catch (error) {
    console.error(error)
    ElMessage.error('获取 MCP 配置失败')
  }
}

const saveConfig = async () => {
  try {
    const payload = {
      enabled: form.enabled,
      base_url: form.base_url
    }
    if (apiKeyInput.value.trim()) {
      payload.api_key = apiKeyInput.value.trim()
    }
    const res = await mcpApi.updateConfig(payload)
    const data = res.data || res
    Object.assign(form, data)
    apiKeyInput.value = ''
    ElMessage.success('MCP 配置已保存，立即生效')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  }
}

onMounted(() => {
  loadConfig()
})
</script>

<style scoped>
.field-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 4px;
}
.meta-text {
  font-size: 13px;
  color: #606266;
}
</style>
