<template>
  <el-container class="case-edit-container">
    <KeywordSidebar v-model="activeGroups" :groups="keywordGroups" />

    <el-main class="case-main">
      <el-card class="edit-card">
        <div class="card-header">
          <h2>{{ isNew ? '新建步骤片段' : '编辑步骤片段' }}</h2>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" class="case-form">
          <el-form-item label="片段名称" prop="name">
            <el-input v-model="form.name" placeholder="请输入片段名称" maxlength="100" show-word-limit />
          </el-form-item>
          <el-form-item label="分类标签">
            <el-input v-model="form.tags" placeholder="如：登录、导航" maxlength="200" />
          </el-form-item>
          <el-form-item label="说明">
            <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" show-word-limit />
          </el-form-item>
          <el-form-item v-if="!isNew" label="当前版本">
            <el-tag type="info">v{{ form.version }}</el-tag>
            <el-text type="info" size="small" style="margin-left: 8px;">修改步骤后版本自动 +1</el-text>
          </el-form-item>
        </el-form>

        <div class="ai-gen-bar">
          <el-button type="warning" @click="aiDialogVisible = true" icon="MagicStick">🤖 AI 生成步骤</el-button>
          <el-button type="success" @click="recordDialogVisible = true" icon="VideoCamera">🎬 AI 录制步骤</el-button>
          <el-button type="primary" plain @click="fragmentPickerVisible = true" icon="Collection">插入片段</el-button>
        </div>

        <div class="steps-section">
          <div class="section-title">
            <span>片段步骤</span>
            <el-text type="info" size="small">编辑步骤时在弹窗内插入变量/工具/标签</el-text>
          </div>
          <StepEditor
            v-model:steps="form.steps"
            :debug-selected-index="selectedStepIndex"
            @debug-select-step="selectedStepIndex = $event"
          />
        </div>

        <FragmentPickerDialog
          v-model="fragmentPickerVisible"
          :exclude-fragment-id="isNew ? null : fragmentId"
          :selected-step-index="selectedStepIndex"
          :steps-count="form.steps?.length || 0"
          @insert="onFragmentInsert"
        />
        <UiCaseGenerator v-model="aiDialogVisible" @apply="handleAiApply" />
        <UiCaseRecorder
          v-model="recordDialogVisible"
          :existing-step-count="form.steps?.length || 0"
          :default-apply-mode="form.steps?.length ? 'append' : 'replace'"
          @apply="handleAiApply"
        />

        <div class="action-bar">
          <el-button type="primary" :loading="saving" @click="save">
            <el-icon><Check /></el-icon>
            保存
          </el-button>
          <el-button @click="goBack">
            <el-icon><Close /></el-icon>
            取消
          </el-button>
        </div>
      </el-card>
    </el-main>
  </el-container>
</template>

<script setup>
import { reactive, ref, computed, onMounted, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { StepEditor, KeywordSidebar } from '@/components/StepEditor'
import UiCaseGenerator from '@/views/AI/components/UiCaseGenerator.vue'
import UiCaseRecorder from '@/views/AI/components/UiCaseRecorder.vue'
import FragmentPickerDialog from '@/components/StepEditor/FragmentPickerDialog.vue'
import { uiFragmentApi } from '@/api/modules/ui'
import { normalizeRecorderApplyPayload } from '@/utils/caseDescription.js'
import { mergeRecorderSteps } from '@/utils/recorderStepMerge.js'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import ActionGroup from '@/datas/ActionGroup.js'
import { insertStepIntoList, resolveInsertAfterIndex } from '@/utils/stepHelper'
import { ElNotification, ElMessage } from 'element-plus'
import {
  Check, Close, Document, Edit, Mouse, Clock, Search, MessageBox, MoreFilled, Share, Collection
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const userStore = UserStore()
const formRef = ref()
const saving = ref(false)
const aiDialogVisible = ref(false)
const recordDialogVisible = ref(false)
const fragmentPickerVisible = ref(false)
const selectedStepIndex = ref(-1)
const varInsertEnvId = ref(proStore.envList[0]?.id || null)
provide('varInsertEnvId', varInsertEnvId)
const activeGroups = ref(['1', '2', '2b', '3', '4', '5', '6', '7', '8'])
const fragmentId = computed(() => route.params.id)
const isNew = computed(() => route.name === 'uiFragmentNew')

const form = reactive({
  name: '',
  description: '',
  tags: '',
  steps: [],
  version: 1,
})

const rules = {
  name: [{ required: true, message: '请输入片段名称', trigger: 'blur' }],
}

const iconMap = {
  Document, Edit, Mouse, Clock, Search, MessageBox, MoreFilled, Share
}

const keywordGroups = computed(() =>
  ActionGroup.map((group) => ({
    ...group,
    icon: iconMap[group.groupIcon] || Document,
    items: group.items.map((item) => ({
      name: item.keyword,
      keyword: item.keyword,
      method: item.method,
      icon: iconMap[group.groupIcon] || Document,
      params: { ...item.params },
    })),
  }))
)

async function loadDetail() {
  if (isNew.value) return
  const res = await uiFragmentApi.getDetail(fragmentId.value, proStore.projectInfo.id)
  const d = res.data?.data
  if (!d) return
  form.name = d.name
  form.description = d.description || ''
  form.tags = d.tags || ''
  form.steps = d.steps || []
  form.version = d.version
}

async function save() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (!form.steps?.length) {
    ElNotification.warning('请至少添加一个步骤')
    return
  }
  saving.value = true
  try {
    const projectId = proStore.projectInfo.id
    const payload = {
      project_id: projectId,
      name: form.name,
      description: form.description,
      tags: form.tags,
      steps: form.steps,
    }
    if (isNew.value) {
      const res = await uiFragmentApi.create(payload)
      if (res.data?.code !== 200) {
        ElNotification.error(res.data?.message || '创建失败')
        return
      }
      ElNotification.success('创建成功')
    } else {
      const res = await uiFragmentApi.update(fragmentId.value, payload, projectId)
      if (res.data?.code !== 200) {
        ElNotification.error(res.data?.message || '保存失败')
        return
      }
      ElNotification.success('保存成功')
    }
    goBack()
  } catch (e) {
    ElNotification.error(e?.data?.message || e?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.push('/ui-fragments')
  userStore.deleteTabs(route.path)
}

function onFragmentInsert(payload) {
  const refStep = payload?.step || payload
  if (!refStep) return
  const insertAt = payload?.insertAt ?? resolveInsertAfterIndex(form.steps?.length || 0, selectedStepIndex.value)
  const { steps, insertAt: at } = insertStepIntoList(form.steps, refStep, insertAt)
  form.steps = steps
  selectedStepIndex.value = at
  ElMessage.success(`已在第 ${at + 1} 步插入片段「${refStep.params?.fragment_name || refStep.desc}」`)
}

function handleAiApply(payload) {
  const { steps, applyMode, insertAtIndex } = normalizeRecorderApplyPayload(payload)
  if (!steps?.length) return
  const mode = form.steps?.length ? (applyMode || 'append') : 'replace'
  form.steps = mergeRecorderSteps(form.steps, steps, mode, insertAtIndex)
  ElNotification.success(`已应用 ${steps.length} 个步骤`)
}

onMounted(loadDetail)
</script>

<style scoped lang="scss">
@use '@/styles/case-step-editor-layout.scss';
</style>
