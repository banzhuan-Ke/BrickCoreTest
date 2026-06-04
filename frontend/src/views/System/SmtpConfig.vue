<template>
  <PageCard>
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
        <el-form-item>
          <el-button type="primary" @click="saveSmtpConfig" icon="Check">保存 SMTP 配置</el-button>
        </el-form-item>
      </el-form>
    </template>
  </PageCard>
</template>

<script setup>
import { reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/index'
import PageCard from "@/components/PageCard.vue"

const smtpForm = reactive({
  host: '',
  port: 465,
  username: '',
  password: '',
  use_tls: true,
  sender: ''
})

onMounted(() => {
  getSmtpConfig()
})

const getSmtpConfig = async () => {
  try {
    const res = await http.notificationApi.getSmtpConfig()
    if (res.status === 200 && res.data) {
      Object.assign(smtpForm, res.data)
    }
  } catch (error) {
    console.error('获取SMTP配置失败:', error)
  }
}

const saveSmtpConfig = async () => {
  try {
    const res = await http.notificationApi.updateSmtpConfig({ ...smtpForm })
    if (res.status === 200) {
      ElMessage.success('SMTP 配置保存成功')
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  }
}
</script>
