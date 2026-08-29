<template>
  <div class="tm-notify-settings" v-loading="loading">
    <TmPremiumBanner />
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
      title="测试管理指派通知"
      description="测试范围用例指派、缺陷、评审、运行项、质量门禁等：默认写站内信（顶栏 SSE 实时推送）；外发邮件走全局 SMTP 发给被指派人邮箱，钉钉等走项目 Webhook。个人免打扰 / IM @ 请到「个人中心 → 通知偏好」。"
    />
    <el-form label-width="160px" style="max-width: 640px">
      <el-form-item label="站内信">
        <el-switch v-model="form.inbox_enabled" :disabled="!canEdit" />
      </el-form-item>
      <el-form-item label="外发渠道">
        <el-switch v-model="form.external_enabled" :disabled="!canEdit" />
        <span class="hint">关闭后仅站内信，不发邮件/钉钉等</span>
      </el-form-item>
      <el-form-item v-if="form.external_enabled" label="启用渠道类型">
        <el-checkbox-group v-model="form.external_channels" :disabled="!canEdit">
          <el-checkbox label="email">邮件</el-checkbox>
          <el-checkbox label="dingtalk">钉钉</el-checkbox>
          <el-checkbox label="wechat">企微</el-checkbox>
          <el-checkbox label="feishu">飞书</el-checkbox>
        </el-checkbox-group>
      </el-form-item>
      <el-form-item label="合并窗口（分钟）">
        <el-input-number
          v-model="form.digest_minutes"
          :min="0"
          :max="1440"
          :disabled="!canEdit"
        />
        <span class="hint">同实体同事件 N 分钟内未读通知合并为一条；0 表示不合并</span>
      </el-form-item>
      <el-form-item label="默认范围负责人">
        <ProjectMemberSelect
          v-if="proStore.projectInfo?.id"
          v-model="form.default_scope_owner_id"
          :project-id="proStore.projectInfo.id"
          placeholder="纳入范围时预填（可空）"
          width="280px"
          :disabled="!canEdit"
        />
        <span class="hint block-hint">未手动指定负责人时，批量纳入范围自动使用此人</span>
      </el-form-item>
      <el-divider content-position="left">事件开关</el-divider>
      <el-form-item label="测试范围用例指派">
        <el-switch v-model="form.on_scope_owner_assigned" :disabled="!canEdit" />
        <span class="hint">控制版本页「通知负责人」按钮；指派时不再逐条自动通知</span>
      </el-form-item>
      <el-form-item label="缺陷指派">
        <el-switch v-model="form.on_defect_assigned" :disabled="!canEdit" />
      </el-form-item>
      <el-form-item label="评审邀请">
        <el-switch v-model="form.on_review_invited" :disabled="!canEdit" />
        <span class="hint">用例评审 + 需求可测性评审邀请站内信</span>
      </el-form-item>
      <el-form-item label="评审待办提醒">
        <el-switch v-model="form.on_review_item_pending" :disabled="!canEdit" />
        <span class="hint">他人提交结论后，提醒尚未提交的评审人</span>
      </el-form-item>
      <el-form-item label="运行项执行人">
        <el-switch v-model="form.on_plan_run_item_assigned" :disabled="!canEdit" />
      </el-form-item>
      <el-form-item label="质量门禁未通过">
        <el-switch v-model="form.on_quality_gate_failed" :disabled="!canEdit" />
        <span class="hint">生成非通过快照时通知版本负责人</span>
      </el-form-item>
      <el-form-item>
        <el-button v-if="canEdit" type="primary" :loading="saving" @click="save">保存</el-button>
        <el-button @click="load">刷新</el-button>
        <el-button link type="primary" @click="$router.push({ path: '/project-settings', query: { tab: 'notify' } })">
          配置通知渠道
        </el-button>
        <el-button link type="primary" @click="$router.push({ path: '/profile', query: { tab: 'notify' } })">
          个人通知偏好
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { projectSettingsApi } from '@/api/modules/sys'
import { ProjectStore } from '@/stores/module/ProjectStore'
import ProjectMemberSelect from '@/views/TestManagement/components/ProjectMemberSelect.vue'
import TmPremiumBanner from '@/components/TmPremiumBanner.vue'

defineProps({
  canEdit: { type: Boolean, default: false }
})

const proStore = ProjectStore()
const loading = ref(false)
const saving = ref(false)
const form = reactive({
  inbox_enabled: true,
  external_enabled: true,
  external_channels: ['email', 'dingtalk'],
  on_scope_owner_assigned: false,
  on_defect_assigned: true,
  on_review_invited: true,
  on_plan_run_item_assigned: true,
  on_review_item_pending: true,
  on_quality_gate_failed: true,
  default_scope_owner_id: null,
  digest_minutes: 5
})

const applyData = (data) => {
  Object.assign(form, {
    inbox_enabled: data.inbox_enabled === true,
    external_enabled: data.external_enabled === true,
    external_channels: Array.isArray(data.external_channels) ? [...data.external_channels] : [],
    on_scope_owner_assigned: data.on_scope_owner_assigned === true,
    on_defect_assigned: data.on_defect_assigned === true,
    on_review_invited: data.on_review_invited === true,
    on_plan_run_item_assigned: data.on_plan_run_item_assigned === true,
    on_review_item_pending: data.on_review_item_pending === true,
    on_quality_gate_failed: data.on_quality_gate_failed === true,
    default_scope_owner_id: data.default_scope_owner_id ?? null,
    digest_minutes: data.digest_minutes ?? 5
  })
}

const load = async () => {
  const pid = proStore.projectInfo?.id
  if (!pid) return
  loading.value = true
  try {
    const res = await projectSettingsApi.getTestNotifySettings(pid)
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
    const res = await projectSettingsApi.updateTestNotifySettings(pid, { ...form })
    applyData(res.data?.data || form)
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

watch(() => proStore.projectInfo?.id, () => load())
onMounted(load)
</script>

<style scoped>
.hint {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}
.block-hint {
  display: block;
  margin-left: 0;
  margin-top: 6px;
}
</style>
