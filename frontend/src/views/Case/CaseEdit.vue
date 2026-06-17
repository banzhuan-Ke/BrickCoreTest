<template>
  <el-container class="case-edit-container">
    <!-- 左侧：关键字面板 -->
    <el-aside width="280px" class="keyword-sidebar">
      <div class="sidebar-header">
        <h3>操作选项</h3>
      </div>
      <div class="keyword-list">
        <el-collapse v-model="activeGroups" class="keyword-collapse">
          <el-collapse-item
            v-for="group in keywordGroups"
            :key="group.groupId"
            :name="group.groupId"
            class="keyword-group"
          >
            <template #title>
              <div class="group-title">
                <el-icon><component :is="group.icon" /></el-icon>
                <span>{{ group.name }}</span>
              </div>
            </template>
            
            <VueDraggable
              :modelValue="group.items"
              :group="{ name: 'steps', pull: 'clone', put: false }"
              :sort="false"
              :clone="cloneKeyword"
              :animation="200"
              target=".keyword-items"
              class="draggable-source"
            >
              <div class="keyword-items">
                <div
                  v-for="(item, itemIndex) in group.items"
                  :key="`${group.groupId}_${item.method}_${itemIndex}`"
                  class="keyword-item"
                  :data-step="JSON.stringify(item)"
                >
                  <el-icon><component :is="item.icon" /></el-icon>
                  <span>{{ item.name }}</span>
                  <el-icon class="drag-icon"><Rank /></el-icon>
                </div>
              </div>
            </VueDraggable>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-aside>
    
    <!-- 右侧：用例编辑区 -->
    <el-main class="case-main">
      <el-card class="edit-card">
        <!-- 标题 -->
        <div class="card-header">
          <h2>编辑测试用例</h2>
        </div>
        
        <!-- 基本信息表单 -->
        <el-form 
          :model="caseInfo" 
          :rules="formRules" 
          ref="formRef" 
          label-width="100px"
          class="case-form"
        >
          <el-form-item label="用例名称" prop="name">
            <el-input 
              v-model="caseInfo.name" 
              placeholder="请输入用例名称"
              maxlength="100"
              show-word-limit
            />
          </el-form-item>
          
          <el-form-item label="所属目录">
            <CatalogTreeSelect
              v-model="caseInfo.catalog_id"
              :project-id="proStore.projectInfo.id"
              placeholder="请选择所属目录"
            />
          </el-form-item>
          
          <el-form-item label="用例级别" prop="level">
            <el-select v-model="caseInfo.level" placeholder="请选择用例级别">
              <el-option label="P0 - 核心" value="P0" />
              <el-option label="P1 - 高" value="P1" />
              <el-option label="P2 - 中" value="P2" />
              <el-option label="P3 - 低" value="P3" />
            </el-select>
          </el-form-item>

          <el-form-item label="用例描述">
            <el-input
              v-model="caseInfo.description"
              type="textarea"
              :rows="4"
              maxlength="4000"
              show-word-limit
              placeholder="可选：功能背景、操作路径与预期结果（供 AI 优化步骤使用）"
            />
          </el-form-item>
          
          <el-form-item label="创建人">
            <el-input v-model="caseInfo.username" disabled />
          </el-form-item>
        </el-form>

        <CaseUsedVarsPanel :steps="caseInfo.steps" />
        
        <!-- AI 生成/录制步骤按钮 -->
        <div class="ai-gen-bar">
          <el-button type="warning" @click="aiDialogVisible = true" icon="MagicStick">🤖 AI 生成步骤</el-button>
          <el-button type="success" @click="recordDialogVisible = true" icon="VideoCamera">🎬 AI 录制步骤</el-button>
          <el-button type="warning" plain @click="openOptimizeDialog" icon="MagicStick">✨ AI 优化步骤</el-button>
          <el-button type="primary" plain @click="fragmentPickerVisible = true" icon="Collection">插入片段</el-button>
        </div>

        <!-- 步骤编辑器 -->
        <div class="steps-section">
          <div class="section-title">
            <span>执行步骤</span>
            <el-text type="info" size="small">编辑步骤时在弹窗内插入变量/工具/标签；参数支持 <code v-pre>${{变量名}}</code>、<code v-pre>${{df:标签名}}</code>、<code v-pre>${{dt:md5|text=@a}}</code></el-text>
          </div>
          <StepEditor v-model:steps="caseInfo.steps" @debug-step="openDebugDialog" />
        </div>

        <CaseDebugDialog
          v-model="debugDialogVisible"
          :case-id="caseId"
          :steps="caseInfo.steps"
          :through-index="debugThroughIndex"
        />

        <FragmentPickerDialog v-model="fragmentPickerVisible" @insert="onFragmentInsert" />

        <!-- AI 生成弹窗 -->
        <UiCaseGenerator v-model="aiDialogVisible" @apply="handleAiApply" />
        
        <!-- AI 录制弹窗 -->
        <UiCaseRecorder
          v-model="recordDialogVisible"
          :initial-description="recordingDescription"
          :initial-url="recordingInitialUrl"
          @apply="handleAiApply"
        />

        <UiCaseStepOptimizeDialog
          v-model="optimizeDialogVisible"
          :steps="caseInfo.steps"
          :initial-description="caseInfo.description || caseInfo.name"
          :project-id="proStore.projectInfo.id"
          @apply="handleOptimizeApply"
        />
        
        <!-- 底部按钮 -->
        <div class="action-bar">
          <el-button type="primary" @click="saveCase" :loading="saving">
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
import { reactive, ref, onMounted, computed, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VueDraggable } from 'vue-draggable-plus'
import { StepEditor } from '@/components/StepEditor'
import UiCaseGenerator from '@/views/AI/components/UiCaseGenerator.vue'
import UiCaseRecorder from '@/views/AI/components/UiCaseRecorder.vue'
import UiCaseStepOptimizeDialog from '@/views/AI/components/UiCaseStepOptimizeDialog.vue'
import CaseDebugDialog from '@/components/CaseDebugDialog.vue'
import CaseUsedVarsPanel from '@/components/CaseUsedVarsPanel.vue'
import FragmentPickerDialog from '@/components/StepEditor/FragmentPickerDialog.vue'
import { UserStore } from '@/stores/module/UserStore'
import { ProjectStore } from '@/stores/module/ProjectStore'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import { resolveCaseDescriptionForContext, extractOpenUrlFromSteps, normalizeRecorderApplyPayload } from '@/utils/caseDescription.js'
import http from '@/api/index'
import { ElNotification, ElMessage } from 'element-plus'
import ActionGroup from '@/datas/ActionGroup.js'
import {
  Rank, Check, Close,
  ChromeFilled, Position, Mouse,
  CircleCheck, Refresh, SwitchButton,
  DocumentCopy, Upload, Download, 
  FullScreen, View, Timer,
  ArrowDown, ArrowUp, Delete,
  Document, Edit, Clock, Search,
  MessageBox, MoreFilled, Share
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = UserStore()
const proStore = ProjectStore()
const varInsertEnvId = ref(proStore.envList[0]?.id || null)
provide('varInsertEnvId', varInsertEnvId)
const fragmentPickerVisible = ref(false)

const caseId = route.params.id
const formRef = ref()
const saving = ref(false)
const aiDialogVisible = ref(false)
const recordDialogVisible = ref(false)
const optimizeDialogVisible = ref(false)
const debugDialogVisible = ref(false)
const debugThroughIndex = ref(0)

// 默认展开所有分组
const activeGroups = ref(['1', '2', '3', '4', '5', '6', '7', '8'])

// 用例信息
const caseInfo = reactive({
  name: '',
  level: '',
  catalog_id: null,
  username: '',
  description: '',
  steps: []
})

const recordingDescription = computed(() => resolveCaseDescriptionForContext(caseInfo))
const recordingInitialUrl = computed(() => extractOpenUrlFromSteps(caseInfo.steps))

// 图标映射
const iconMap = {
  'Document': Document,
  'Edit': Edit,
  'Mouse': Mouse,
  'Clock': Clock,
  'Search': Search,
  'MessageBox': MessageBox,
  'MoreFilled': MoreFilled,
  'Share': Share
}

// 从 ActionGroup 生成分组后的关键字列表
const keywordGroups = computed(() => {
  return ActionGroup.map(group => ({
    ...group,
    icon: iconMap[group.groupIcon] || Document,
    items: group.items.map(item => ({
      name: item.keyword,
      keyword: item.keyword,
      method: item.method,
      icon: iconMap[group.groupIcon] || Document,
      params: { ...item.params }
    }))
  }))
})

// 扁平化的关键字列表（用于拖拽）
const keywordList = computed(() => {
  const list = []
  ActionGroup.forEach(group => {
    group.items.forEach(item => {
      list.push({
        name: item.keyword,
        keyword: item.keyword,
        method: item.method,
        icon: iconMap[group.groupIcon] || Document,
        params: { ...item.params }
      })
    })
  })
  return list
})

// 克隆关键字（拖拽时）
function cloneKeyword(keyword) {
  return {
    ...keyword,
    params: { ...keyword.params }
  }
}

// 表单校验规则
const formRules = {
  name: [
    { required: true, message: '请输入用例名称', trigger: 'blur' },
    { min: 2, max: 100, message: '长度在 2 到 100 个字符', trigger: 'blur' }
  ],
  level: [
    { required: true, message: '请选择用例级别', trigger: 'change' }
  ]
}

// 获取用例详情
async function getCaseDetail() {
  try {
    const res = await http.caseApi.getDetail(caseId)
    if (res.status === 200) {
      caseInfo.name = res.data.name
      caseInfo.level = res.data.level
      caseInfo.catalog_id = res.data.catalog_id ?? null
      caseInfo.username = res.data.username
      caseInfo.description = res.data.description || ''
      // 确保 steps 是数组
      caseInfo.steps = Array.isArray(res.data.steps) ? res.data.steps : []
    }
  } catch (error) {
    ElNotification.error('获取用例详情失败')
  }
}

// 保存用例
async function saveCase() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  
  saving.value = true
  try {
    const res = await http.caseApi.update(caseId, caseInfo)
    if (res.status === 200 || res.status === 201) {
      ElNotification.success('用例保存成功')
      goBack()
    } else {
      ElNotification.error(res.data?.detail || '保存失败')
    }
  } catch (error) {
    ElNotification.error('保存用例失败')
  } finally {
    saving.value = false
  }
}

// 返回列表
function goBack() {
  router.back()
  userStore.deleteTabs(route.path)
}

// AI 生成/录制步骤应用到用例（编辑页：替换全部步骤）
function onFragmentInsert(refStep) {
  if (!refStep) return
  caseInfo.steps = [...(caseInfo.steps || []), refStep]
  ElMessage.success(`已插入片段「${refStep.params?.fragment_name || refStep.desc}」`)
}

function handleAiApply(payload) {
  const { steps, description: desc } = normalizeRecorderApplyPayload(payload)
  if (!steps?.length) return
  caseInfo.steps = JSON.parse(JSON.stringify(steps))
  if (desc) {
    caseInfo.description = desc
    ElNotification.success(`已应用 ${steps.length} 个步骤，并同步测试描述到用例描述`)
  } else {
    ElNotification.success(`已应用 ${steps.length} 个步骤（已替换原有步骤）`)
  }
}

function openOptimizeDialog() {
  if (!caseInfo.steps?.length) {
    ElMessage.warning('请先添加或录制步骤后再优化')
    return
  }
  optimizeDialogVisible.value = true
}

function handleOptimizeApply(steps) {
  if (!steps?.length) return
  caseInfo.steps = JSON.parse(JSON.stringify(steps))
  ElNotification.success(`已应用 AI 优化后的 ${steps.length} 个步骤，请核对用例描述与步骤后保存`)
}

function openDebugDialog(index) {
  if (!caseInfo.steps?.length) {
    ElNotification.warning('请先添加步骤')
    return
  }
  debugThroughIndex.value = index
  debugDialogVisible.value = true
}

onMounted(() => {
  getCaseDetail()
})
</script>

<style scoped lang="scss">
@use '@/styles/case-step-editor-layout.scss';
</style>
