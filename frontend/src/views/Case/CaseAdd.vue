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
          <h2>创建测试用例</h2>
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
          
          <el-form-item label="创建人">
            <el-input v-model="caseInfo.username" disabled />
          </el-form-item>
        </el-form>
        
        <!-- AI 生成/录制步骤按钮 -->
        <div class="ai-gen-bar">
          <el-button type="warning" @click="aiDialogVisible = true" icon="MagicStick">🤖 AI 生成步骤</el-button>
          <el-button type="success" @click="recordDialogVisible = true" icon="VideoCamera">🎬 AI 录制步骤</el-button>
        </div>

        <!-- 步骤编辑器 -->
        <div class="steps-section">
          <div class="section-title">
            <span>执行步骤</span>
            <VarInsertButton :show-env-edit="false" label="插入变量" />
            <el-text type="info" size="small">拖拽左侧操作到此处；步骤参数可用 <code v-pre>${{变量名}}</code></el-text>
          </div>
          <StepEditor v-model:steps="caseInfo.steps" />
        </div>

        <!-- AI 生成弹窗 -->
        <UiCaseGenerator v-model="aiDialogVisible" @apply="handleAiApply" />
        
        <!-- AI 录制弹窗 -->
        <UiCaseRecorder v-model="recordDialogVisible" @apply="handleAiApply" />
        
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
import { reactive, ref, computed, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VueDraggable } from 'vue-draggable-plus'
import { StepEditor } from '@/components/StepEditor'
import UiCaseGenerator from '@/views/AI/components/UiCaseGenerator.vue'
import UiCaseRecorder from '@/views/AI/components/UiCaseRecorder.vue'
import VarInsertButton from '@/components/VarInsertButton.vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import { UserStore } from '@/stores/module/UserStore'
import http from '@/api/index'
import { ElNotification } from 'element-plus'
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
const proStore = ProjectStore()
const varInsertEnvId = ref(proStore.envList[0]?.id || null)
provide('varInsertEnvId', varInsertEnvId)
const userStore = UserStore()

const formRef = ref()
const saving = ref(false)
const aiDialogVisible = ref(false)
const recordDialogVisible = ref(false)

// 默认展开所有分组
const activeGroups = ref(['1', '2', '3', '4', '5', '6', '7', '8'])

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
      params: { ...item.params },
      is_container: item.is_container,
      branches: item.branches
    }))
  }))
})

// 用例信息
const caseInfo = reactive({
  name: '测试用例',
  level: 'P2',
  catalog_id: null,
  username: userStore.userInfo.username,
  project_id: proStore.projectInfo.id,
  steps: [
    {
      id: `step_${Date.now()}`,
      keyword: '打开浏览器',
      desc: '打开浏览器',
      method: 'open_browser',
      params: { browser_type: 'chromium' },
      children: []
    }
  ]
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

// 保存用例
async function saveCase() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  
  saving.value = true
  try {
    const res = await http.caseApi.create(caseInfo)
    if (res.status === 200 || res.status === 201) {
      ElNotification.success('用例创建成功')
      goBack()
    } else {
      ElNotification.error(res.data?.detail || '创建失败')
    }
  } catch (error) {
    ElNotification.error('创建用例失败')
  } finally {
    saving.value = false
  }
}

// 返回列表
function goBack() {
  router.back()
  userStore.deleteTabs(route.path)
}

// AI 生成步骤应用
function handleAiApply(steps) {
  if (steps && steps.length > 0) {
    // 如果当前只有默认的打开浏览器步骤，则替换；否则追加
    if (caseInfo.steps.length === 1 && caseInfo.steps[0].method === 'open_browser') {
      caseInfo.steps = steps
    } else {
      caseInfo.steps = [...caseInfo.steps, ...steps]
    }
    ElNotification.success(`已应用 ${steps.length} 个步骤`)
  }
}
</script>

<style scoped lang="scss">
.case-edit-container {
  height: calc(100vh - 50px);
}

.keyword-sidebar {
  background: white;
  border-right: 1px solid var(--el-border-color);
  display: flex;
  flex-direction: column;
  height: 100%;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--el-border-color);
  flex-shrink: 0;
  
  h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 500;
  }
}

.keyword-list {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
  min-height: 0;
}

.keyword-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.keyword-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  cursor: grab;
  transition: all 0.2s;
  
  &:hover {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }
  
  &:active {
    cursor: grabbing;
  }
  
  .drag-icon {
    margin-left: auto;
    color: var(--el-text-color-secondary);
  }
}

.case-main {
  padding: 20px 20px 60px 20px;
  background: var(--el-fill-color-light);
  overflow-y: auto;
  height: 100%;
}

.edit-card {
  min-height: auto;
  margin-bottom: 20px;
}

.card-header {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--el-border-color);
  
  h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 500;
  }
}

.case-form {
  max-width: 600px;
}

.steps-section {
  margin-top: 24px;
  
  .section-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    
    span:first-child {
      font-weight: 500;
      font-size: 16px;
    }
  }
}

.action-bar {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--el-border-color);
  display: flex;
  gap: 12px;
}

.draggable-source {
  min-height: 200px;
}
</style>
