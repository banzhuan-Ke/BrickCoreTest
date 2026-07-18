<template>
  <div class="notification-config-root">
  <ConfigShell :embedded="embedded">
    <template #title>
      <b>通知配置</b>
    </template>
    <template #main>
      <div style="margin-bottom: 15px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
        <template v-if="embedded">
          <span v-if="boundProjectName" style="color: #606266; font-size: 13px;">
            当前项目：<b>{{ boundProjectName }}</b>
          </span>
          <el-tag v-else type="warning" size="small">请先在顶栏选择项目</el-tag>
        </template>
        <template v-else>
          <span>选择项目：</span>
          <el-select
            v-model="selectedProjectId"
            placeholder="请选择项目"
            clearable
            style="width: 220px;"
            @change="onProjectChange"
          >
            <el-option v-for="item in projectList" :key="item.id" :label="item.name" :value="item.id"/>
          </el-select>
        </template>
        <el-button
          v-if="canEditResolved"
          type="primary"
          @click="openAddDialog"
          :disabled="!selectedProjectId"
          icon="Plus"
        >添加配置</el-button>
        <el-tag v-else type="info" size="small">只读：无「通知渠道-编辑」权限</el-tag>
      </div>

      <!-- 配置列表 -->
      <el-table :data="configList" style="width: 100%" :header-cell-style="{'text-align':'center'}"
                :cell-style="{'text-align':'center'}" stripe v-loading="loading">
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><Bell /></el-icon>
            </div>
            <div>暂无通知配置</div>
          </div>
        </template>
        <el-table-column label="序号" type="index" width="70"/>
        <el-table-column prop="channel_type" label="通知渠道" width="120">
          <template #default="scope">
            <el-tag v-if="scope.row.channel_type === 'email'" type="primary">邮件</el-tag>
            <el-tag v-else-if="scope.row.channel_type === 'dingtalk'" type="warning">钉钉</el-tag>
            <el-tag v-else-if="scope.row.channel_type === 'wechat'" type="success">企微</el-tag>
            <el-tag v-else-if="scope.row.channel_type === 'feishu'" type="info">飞书</el-tag>
            <span v-else>{{ scope.row.channel_type }}</span>
          </template>
        </el-table-column>
        <el-table-column label="配置内容" min-width="240" show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.channel_type === 'email'">
              收件人：{{ formatRecipients(scope.row.config.recipients) }}
              <el-tag v-if="scope.row.api_auto_push_report" size="small" type="success" style="margin-left: 6px;">API自动推送</el-tag>
              <el-tag v-if="scope.row.ui_auto_push_report" size="small" type="info" style="margin-left: 6px;">Web自动推送</el-tag>
              <el-tag v-if="scope.row.perf_auto_push_report" size="small" type="warning" style="margin-left: 6px;">压测自动推送</el-tag>
              <el-tag v-if="scope.row.app_auto_push_report" size="small" type="primary" style="margin-left: 6px;">App自动推送</el-tag>
            </span>
            <span v-else-if="scope.row.channel_type === 'dingtalk'">
              Webhook：{{ scope.row.config.webhook_url }}
            </span>
            <span v-else-if="scope.row.channel_type === 'wechat'">
              Webhook：{{ scope.row.config.webhook_url }}
            </span>
            <span v-else-if="scope.row.channel_type === 'feishu'">
              Webhook：{{ scope.row.config.webhook_url }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="启用状态" width="100">
          <template #default="scope">
            <el-switch
              v-model="scope.row.enabled"
              :disabled="!canEditResolved"
              @change="toggleEnabled(scope.row)"
              active-text=""
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260">
          <template #default="scope">
            <template v-if="canEditResolved">
              <el-button link type="primary" @click="openEditDialog(scope.row)" icon="Edit">编辑</el-button>
              <el-button link type="primary" @click="handleTest(scope.row.id)" icon="Promotion">测试</el-button>
              <el-button link type="danger" @click="handleDelete(scope.row.id)" icon="Delete">删除</el-button>
            </template>
            <span v-else style="color: #909399; font-size: 12px;">—</span>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </ConfigShell>

  <!-- 添加/编辑弹窗 -->
  <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑通知配置' : '添加通知配置'" width="520px" center destroy-on-close>
    <div style="margin-bottom: 15px; background: #f4f4f5; padding: 10px 12px; border-radius: 4px; font-size: 13px; color: #606266; display: flex; align-items: center; gap: 6px;">
      <el-icon><QuestionFilled /></el-icon>
      <span>启用后，当 UI/API 用例执行失败时，系统会自动向该渠道发送告警通知。</span>
      <el-tooltip placement="top">
        <template #content>
          <div style="max-width: 320px; line-height: 1.6;">
            <b>使用说明</b><br/>
            • <b>启用状态</b>：关闭后该渠道不再发送任何通知。<br/>
            • <b>失败告警</b>：UI/API 套件执行失败时，所有启用的渠道都会收到告警消息。<br/>
            • <b>自动推报告</b>（仅邮件）：API 套件 / UI 计划 / 性能测试执行完成后，自动将 HTML 报告作为邮件附件发送；钉钉/企微/飞书不支持此功能。<br/>
            • <b>测试发送</b>：配置完成后可点击“测试”按钮手动验证连通性。
          </div>
        </template>
        <el-icon style="cursor: pointer; color: #409eff;"><QuestionFilled /></el-icon>
      </el-tooltip>
    </div>
    <el-form :model="formData" label-width="110px" :rules="formRules" ref="formRef">
      <el-form-item label="通知渠道：" prop="channel_type">
        <el-select v-model="formData.channel_type" placeholder="请选择" style="width: 100%;" :disabled="isEdit">
          <el-option label="邮件" value="email"/>
          <el-option label="钉钉" value="dingtalk"/>
          <el-option label="企业微信" value="wechat"/>
          <el-option label="飞书" value="feishu"/>
        </el-select>
      </el-form-item>

      <!-- 邮件配置 -->
      <template v-if="formData.channel_type === 'email'">
        <el-form-item label="收件人：">
          <el-input v-model="recipientsText" type="textarea" :rows="2" placeholder="多个邮箱用逗号或换行分隔"/>
        </el-form-item>
        <el-form-item label="自动推报告：">
          <div style="display: flex; flex-direction: column; gap: 8px;">
            <el-switch v-model="formData.api_auto_push_report" active-text="API套件执行完成后自动发送报告"/>
            <el-switch v-model="formData.ui_auto_push_report" active-text="UI计划执行完成后自动发送报告"/>
            <el-switch v-model="formData.perf_auto_push_report" active-text="性能测试执行完成后自动发送报告"/>
            <el-switch v-model="formData.app_auto_push_report" active-text="App计划/套件执行完成后自动发送报告"/>
          </div>
        </el-form-item>
      </template>

      <!-- 钉钉配置 -->
      <template v-if="formData.channel_type === 'dingtalk'">
        <el-form-item label="Webhook：" prop="webhook_url">
          <el-input v-model="formData.config.webhook_url" placeholder="https://oapi.dingtalk.com/robot/send?access_token=xxx"/>
        </el-form-item>
        <el-form-item label="加签Secret：">
          <el-input v-model="formData.config.secret" placeholder="可选，若钉钉机器人开启加签则必填"/>
        </el-form-item>
      </template>

      <!-- 企微配置 -->
      <template v-if="formData.channel_type === 'wechat'">
        <el-form-item label="Webhook：" prop="webhook_url">
          <el-input v-model="formData.config.webhook_url" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"/>
        </el-form-item>
      </template>

      <!-- 飞书配置 -->
      <template v-if="formData.channel_type === 'feishu'">
        <el-form-item label="Webhook：" prop="webhook_url">
          <el-input v-model="formData.config.webhook_url" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"/>
        </el-form-item>
      </template>

      <el-form-item label="启用状态：">
        <el-switch v-model="formData.enabled"/>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer" style="text-align: center;">
        <el-button type="primary" @click="submitForm">确认</el-button>
        <el-button @click="dialogVisible = false">取消</el-button>
      </div>
    </template>
  </el-dialog>
  </div>
</template>

<script setup>
import ConfigShell from '@/components/ConfigShell.vue'
import { computed, ref, reactive, onMounted, watch } from 'vue'
import { Bell, Plus, Edit, Promotion, Delete, QuestionFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/index'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'

const props = defineProps({
  /** 嵌入「项目设置」时：锁定顶栏当前项目，不可再选其他项目 */
  embedded: { type: Boolean, default: false },
  /** 未传时按 notification_config:edit 推断 */
  canEdit: { type: Boolean, default: undefined },
})

const uStore = UserStore()
const proStore = ProjectStore()
const projectList = ref([])
const selectedProjectId = ref(null)
const configList = ref([])
const loading = ref(false)
const boundProjectName = computed(() => proStore.projectInfo?.name || '')
const canEditResolved = computed(() => {
  if (typeof props.canEdit === 'boolean') return props.canEdit
  return uStore.hasPermission('notification_config:edit')
})

const dialogVisible = ref(false)
const isEdit = ref(false)
const currentEditId = ref(null)
const formRef = ref(null)

const formData = reactive({
  channel_type: 'email',
  enabled: true,
  config: {},
  api_auto_push_report: false,
  ui_auto_push_report: false,
  perf_auto_push_report: false,
  app_auto_push_report: false,
})
const recipientsText = ref('')

const formRules = {
  channel_type: [{ required: true, message: '请选择通知渠道', trigger: 'change' }],
  webhook_url: [{ required: true, message: '请填写 Webhook 地址', trigger: 'blur' }]
}

watch(() => formData.channel_type, (val) => {
  if (val !== 'email') {
    formData.api_auto_push_report = false
    formData.ui_auto_push_report = false
    formData.perf_auto_push_report = false
    formData.app_auto_push_report = false
    delete formData.config.recipients
    recipientsText.value = ''
  }
  if (val !== 'dingtalk') {
    delete formData.config.secret
  }
  if (val !== 'dingtalk' && val !== 'wechat' && val !== 'feishu') {
    delete formData.config.webhook_url
  }
})

const syncEmbeddedProject = async () => {
  const pid = proStore.projectInfo?.id || null
  selectedProjectId.value = pid
  await getConfigList()
}

onMounted(async () => {
  if (props.embedded) {
    await syncEmbeddedProject()
    return
  }
  await getProjectList()
  if (!selectedProjectId.value && proStore.projectInfo?.id) {
    selectedProjectId.value = proStore.projectInfo.id
    await getConfigList()
  }
})

watch(
  () => (props.embedded ? proStore.projectInfo?.id : null),
  async () => {
    if (props.embedded) await syncEmbeddedProject()
  }
)

const getProjectList = async () => {
  const res = await http.projectApi.getProjectList({ page: 1, size: 1000 })
  if (res.status === 200) {
    projectList.value = res.data.data || []
  }
}

const getConfigList = async () => {
  if (!selectedProjectId.value) {
    configList.value = []
    return
  }
  loading.value = true
  try {
    const res = await http.notificationApi.getConfigList(selectedProjectId.value)
    if (res.status === 200) {
      configList.value = res.data || []
    }
  } finally {
    loading.value = false
  }
}

const onProjectChange = () => {
  getConfigList()
}

const formatRecipients = (list) => {
  if (!list || !list.length) return '-'
  return list.join('、')
}

const openAddDialog = () => {
  if (!canEditResolved.value) {
    ElMessage.warning('无编辑权限')
    return
  }
  isEdit.value = false
  currentEditId.value = null
  formData.channel_type = 'email'
  formData.enabled = true
  formData.config = {}
  formData.api_auto_push_report = false
  formData.ui_auto_push_report = false
  formData.perf_auto_push_report = false
  formData.app_auto_push_report = false
  recipientsText.value = ''
  dialogVisible.value = true
}

const openEditDialog = (row) => {
  isEdit.value = true
  currentEditId.value = row.id
  formData.channel_type = row.channel_type
  formData.enabled = row.enabled
  formData.config = { ...row.config }
  formData.api_auto_push_report = row.api_auto_push_report || false
  formData.ui_auto_push_report = row.ui_auto_push_report || false
  formData.perf_auto_push_report = row.perf_auto_push_report || false
  formData.app_auto_push_report = row.app_auto_push_report || false
  if (row.channel_type === 'email') {
    recipientsText.value = (row.config.recipients || []).join(',')
  }
  dialogVisible.value = true
}

const submitForm = async () => {
  if (!canEditResolved.value) {
    ElMessage.warning('无编辑权限')
    return
  }
  if (formData.channel_type === 'email') {
    const list = recipientsText.value.split(/[,，\n]/).map(s => s.trim()).filter(Boolean)
    if (list.length === 0) {
      ElMessage.warning('请至少填写一个收件人邮箱')
      return
    }
    formData.config.recipients = list
  }

  const payload = {
    channel_type: formData.channel_type,
    enabled: formData.enabled,
    config: formData.config,
    api_auto_push_report: formData.api_auto_push_report,
    ui_auto_push_report: formData.ui_auto_push_report,
    perf_auto_push_report: formData.perf_auto_push_report,
    app_auto_push_report: formData.app_auto_push_report,
  }

  try {
    if (isEdit.value) {
      const res = await http.notificationApi.updateConfig(currentEditId.value, payload)
      if (res.status === 200) {
        ElMessage.success('更新成功')
        dialogVisible.value = false
        getConfigList()
      }
    } else {
      const res = await http.notificationApi.createConfig(selectedProjectId.value, payload)
      if (res.status === 201) {
        ElMessage.success('添加成功')
        dialogVisible.value = false
        getConfigList()
      }
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
    console.error('保存失败:', error)
  }
}

const toggleEnabled = async (row) => {
  try {
    await http.notificationApi.updateConfig(row.id, {
      channel_type: row.channel_type,
      enabled: row.enabled,
      config: row.config,
      api_auto_push_report: row.api_auto_push_report,
      ui_auto_push_report: row.ui_auto_push_report,
      perf_auto_push_report: row.perf_auto_push_report,
      app_auto_push_report: row.app_auto_push_report || false,
    })
    ElMessage.success('状态更新成功')
  } catch (error) {
    row.enabled = !row.enabled
    console.error('状态更新失败:', error)
  }
}

const handleTest = async (id) => {
  try {
    const res = await http.notificationApi.testConfig(id)
    if (res.status === 200) {
      ElMessage.success(res.data.detail || '测试消息已发送')
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '测试发送失败')
  }
}

const handleDelete = (id) => {
  ElMessageBox.confirm('确定要删除该通知配置吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    const res = await http.notificationApi.deleteConfig(id)
    if (res.status === 204) {
      ElMessage.success('删除成功')
      getConfigList()
    }
  }).catch(() => {})
}
</script>

<style scoped>
.table-empty {
  padding: 40px 0;
  text-align: center;
  color: #909399;
}
.empty-icon {
  margin-bottom: 10px;
}
</style>
