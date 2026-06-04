<template>
  <div class="report-page">
    <div class="report-header">
      <div class="header-left">
        <el-button link @click="goBack" icon="ArrowLeft">返回</el-button>
        <h2>接口执行报告</h2>
      </div>
      <div class="header-right">
        <el-button type="primary" size="small" @click="copyShareLink" icon="Share">
          {{ copied ? '已复制' : '分享链接' }}
        </el-button>
        <el-button type="success" size="small" @click="exportReport" icon="Download" :loading="exporting">
          导出报告
        </el-button>
      </div>
    </div>
    
    <div class="report-body">
      <ApiRunDetail :record-id="Number(recordId)" :record-type="recordType" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ApiRunDetail from './components/ApiRunDetail.vue'
import http from '@/api/index'

const route = useRoute()
const router = useRouter()
const recordId = route.params.recordId
const recordType = computed(() => route.query.type || 'suite')

const copied = ref(false)
const exporting = ref(false)

const goBack = () => {
  router.back()
}

const copyTextFallback = (text) => {
  const input = document.createElement('textarea')
  input.value = text
  input.style.position = 'fixed'
  input.style.left = '-9999px'
  document.body.appendChild(input)
  input.focus()
  input.select()
  const ok = document.execCommand('copy')
  document.body.removeChild(input)
  return ok
}

const copyShareLink = async () => {
  const url = window.location.href
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url)
    } else if (!copyTextFallback(url)) {
      throw new Error('copy failed')
    }
    copied.value = true
    ElMessage.success('链接已复制到剪贴板')
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    ElMessage.warning('复制失败，请手动复制地址栏链接')
  }
}

const exportReport = async () => {
  exporting.value = true
  try {
    if (recordType.value === 'plan') {
      const res = await http.apiModuleApi.exportPlanReport(recordId)
      const blob = new Blob([res.data], { type: 'text/html' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `api_plan_report_${recordId}_${new Date().getTime()}.html`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } else {
      const res = await http.apiModuleApi.exportApiSuiteReport(recordId)
      const blob = new Blob([res.data], { type: 'text/html' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `api_report_${recordId}_${new Date().getTime()}.html`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    }
    ElMessage.success('报告导出成功')
  } catch (error) {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped lang="scss">
.report-page {
  padding: 20px;
  background: var(--el-bg-color-page);
  min-height: 100vh;
  box-sizing: border-box;
  overflow-y: auto;
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 16px 20px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
  
  .header-left {
    display: flex;
    align-items: center;
    gap: 15px;
    
    h2 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
    }
  }
  
  .header-right {
    display: flex;
    gap: 10px;
  }
}

.report-body {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}
</style>
