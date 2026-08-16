<template>
  <ConfigShell :embedded="embedded">
    <template #title>
      <b>SMTP 配置</b>
    </template>
    <template #main>
      <el-form :model="smtpForm" label-width="120px" style="max-width: 600px;">
        <el-form-item label="SMTP服务器：">
          <el-input v-model="smtpForm.host" placeholder="如：smtp.qq.com"/>
        </el-form-item>
        <el-form-item label="端口：">
          <el-input-number v-model="smtpForm.port" :min="1" :max="65535" controls-position="right"/>
        </el-form-item>
        <el-form-item label="发件账号：">
          <el-input v-model="smtpForm.username" placeholder="发件邮箱账号"/>
        </el-form-item>
        <el-form-item label="密码/授权码：">
          <el-input v-model="smtpForm.password" type="password" show-password placeholder="邮箱授权码"/>
        </el-form-item>
        <el-form-item label="发件人名称：">
          <el-input v-model="smtpForm.sender" placeholder="如：BrickCore"/>
        </el-form-item>
        <el-form-item label="启用 TLS/SSL：">
          <el-switch v-model="smtpForm.use_tls"/>
        </el-form-item>
        <el-form-item label="测试收件人：">
          <el-input
            v-model="testTo"
            clearable
            placeholder="默认发给发件账号；可改成其它邮箱"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveSmtpConfig" icon="Check" :loading="saving">
            保存 SMTP 配置
          </el-button>
          <el-button type="success" plain @click="testSmtpConfig" icon="Connection" :loading="testing">
            测试连接
          </el-button>
        </el-form-item>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="「测试连接」会用上方当前填写的参数发一封短邮件，无需先保存；密码留空则使用已保存的授权码。"
        />
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
import http from '@/api/index'

const smtpForm = reactive({
  host: '',
  port: 465,
  username: '',
  password: '',
  use_tls: true,
  sender: ''
})
const testTo = ref('')
const saving = ref(false)
const testing = ref(false)

onMounted(() => {
  getSmtpConfig()
})

const getSmtpConfig = async () => {
  try {
    const res = await http.notificationApi.getSmtpConfig()
    if (res.status === 200 && res.data) {
      Object.assign(smtpForm, res.data)
      if (!testTo.value) testTo.value = res.data.username || ''
    }
  } catch (error) {
    console.error('获取SMTP配置失败:', error)
  }
}

const saveSmtpConfig = async () => {
  saving.value = true
  try {
    const res = await http.notificationApi.updateSmtpConfig({ ...smtpForm })
    if (res.status === 200) {
      ElMessage.success('SMTP 配置保存成功')
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const testSmtpConfig = async () => {
  if (!smtpForm.host || !smtpForm.username) {
    ElMessage.warning('请先填写 SMTP 服务器和发件账号')
    return
  }
  testing.value = true
  try {
    const res = await http.notificationApi.testSmtpConfig({
      host: smtpForm.host,
      port: smtpForm.port,
      username: smtpForm.username,
      password: smtpForm.password,
      use_tls: smtpForm.use_tls,
      sender: smtpForm.sender,
      to: (testTo.value || '').trim() || undefined,
    })
    if (res.status >= 200 && res.status < 300) {
      const msg = res.data?.detail || `测试邮件已发送至 ${testTo.value || smtpForm.username}`
      ElMessage.success(msg)
    } else {
      ElMessage.error(res.data?.detail || 'SMTP 测试失败')
    }
  } catch (error) {
    ElMessage.error(
      error?.response?.data?.detail ||
      error?.data?.detail ||
      error?.message ||
      'SMTP 测试失败'
    )
  } finally {
    testing.value = false
  }
}
</script>
