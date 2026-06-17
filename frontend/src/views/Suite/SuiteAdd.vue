<template>
  <el-container class="suite-edit-container">
    <!-- 左侧：关键字面板 -->
    <el-aside width="280px" class="keyword-sidebar">
      <div class="sidebar-header">
        <h3>前置步骤操作</h3>
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

    <!-- 中间：套件信息 + 前置步骤 -->
    <el-main class="suite-main">
      <el-card class="suite-card">
        <!-- 标题 -->
        <div class="card-header">
          <h2>创建测试套件</h2>
        </div>

        <!-- 套件基本信息 -->
        <el-form 
          :model="suiteInfo" 
          :rules="formRules" 
          ref="formRef" 
          label-width="100px"
          class="suite-form"
        >
          <el-form-item label="套件名称" prop="name">
            <el-input v-model="suiteInfo.name" placeholder="请输入套件名称" />
          </el-form-item>
          
          <el-form-item label="套件类型" prop="suite_type">
            <el-select v-model="suiteInfo.suite_type" placeholder="请选择套件类型" style="width: 100%">
              <el-option label="功能测试" value="1" />
              <el-option label="场景测试" value="2" />
            </el-select>
          </el-form-item>

          <el-form-item label="执行策略">
            <div class="suite-strategy-box">
              <el-checkbox v-model="suiteInfo.propagate_variables">
                链路用例变量传递给后续链路用例
              </el-checkbox>
              <el-checkbox v-model="suiteInfo.stop_on_failure">
                任一用例失败时停止全部后续用例
              </el-checkbox>
            </div>
          </el-form-item>
          
          <el-form-item label="所属目录" prop="catalog_id">
            <CatalogTreeSelect
              v-model="suiteInfo.catalog_id"
              :project-id="proStore.projectInfo.id"
              placeholder="请选择所属目录"
            />
          </el-form-item>
          
          <el-form-item label="创建人">
            <el-input v-model="suiteInfo.username" disabled />
          </el-form-item>
        </el-form>

        <!-- 公共前置步骤 -->
        <div class="setup-steps-section">
          <div class="section-title">
            <span>公共前置步骤</span>
            <el-text type="info" size="small">拖拽左侧操作到此处</el-text>
          </div>
          <StepEditor v-model:steps="suiteInfo.pre_actions" />
        </div>

        <!-- 底部按钮 -->
        <div class="action-bar">
          <el-button type="primary" @click="saveSuite" :loading="saving">
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

    <!-- 右侧：套件用例 + 用例集 -->
    <el-aside width="420px" class="case-sidebar">
      <div class="case-section">
        <h3 class="sidebar-title">套件用例</h3>
        <div class="empty-case-tip">
          <el-empty description="保存套件后可从用例集拖拽添加" :image-size="80" />
        </div>
      </div>
      <div class="case-section">
        <h3 class="sidebar-title">测试用例集</h3>
        <CaseSet />
      </div>
    </el-aside>
  </el-container>
</template>

<script setup>
import { reactive, ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { VueDraggable } from 'vue-draggable-plus'
import { StepEditor } from '@/components/StepEditor'
import { ProjectStore } from '@/stores/module/ProjectStore'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import { UserStore } from '@/stores/module/UserStore'
import http from '@/api/index'
import { ElNotification } from 'element-plus'
import ActionGroup from '@/datas/ActionGroup.js'
import CaseSet from './componets/CaseSet.vue'
import {
  Rank, Check, Close,
  ChromeFilled, Position, Mouse,
  CircleCheck, Refresh,
  DocumentCopy, View, Timer,
  ArrowDown, Delete,
  Document, Edit, Clock, Search,
  MessageBox, MoreFilled, Share
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const proStore = ProjectStore()
const userStore = UserStore()

const formRef = ref()
const saving = ref(false)

// 套件信息
const suiteInfo = reactive({
  name: '测试套件',
  suite_type: '1',
  stop_on_failure: false,
  propagate_variables: false,
  catalog_id: null,
  username: userStore.userInfo.username,
  pre_actions: [
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

watch(() => suiteInfo.suite_type, (type) => {
  if (type === '2') {
    suiteInfo.propagate_variables = true
  }
})

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

// 克隆关键字（拖拽时）
function cloneKeyword(keyword) {
  return {
    ...keyword,
    params: { ...keyword.params }
  }
}

// 表单校验规则
const formRules = {
  name: [{ required: true, message: '请输入套件名称', trigger: 'blur' }],
  suite_type: [{ required: true, message: '请选择套件类型', trigger: 'change' }],
  catalog_id: [{ required: true, message: '请选择所属目录', trigger: 'change' }]
}

// 保存套件
const saveSuite = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const res = await http.suiteApi.create({
      ...suiteInfo,
      project_id: proStore.projectInfo.id
    })
    // axios 返回整个 response 对象，res.status 是 HTTP 状态码，res.data 是响应数据
    if (res.status === 201 || res.status === 200) {
      ElNotification.success('套件创建成功')
      goBack()
    } else {
      ElNotification.error(res.data?.detail || '创建失败')
    }
  } catch (error) {
    ElNotification.error(error?.response?.data?.detail || '创建套件失败')
  } finally {
    saving.value = false
  }
}

// 返回
const goBack = () => {
  router.back()
  userStore.deleteTabs(route.path)
}
</script>

<style scoped lang="scss">
.suite-strategy-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.suite-edit-container {
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
  padding: 0;
  overflow-y: auto;
  min-height: 0;
}

.keyword-collapse {
  border: none;
  
  :deep(.el-collapse-item__header) {
    padding: 0 12px;
    font-weight: 500;
    border-bottom: 1px solid var(--el-border-color-light);
  }
  
  :deep(.el-collapse-item__content) {
    padding: 8px;
  }
  
  :deep(.el-collapse-item__wrap) {
    border-bottom: none;
  }
}

.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  
  .el-icon {
    color: var(--el-color-primary);
  }
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

.suite-main {
  padding: 20px;
  background: var(--el-fill-color-light);
  overflow-y: auto;
  height: 100%;
}

.suite-card {
  min-height: auto;
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

.suite-form {
  max-width: 600px;
}

.setup-steps-section {
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

.case-sidebar {
  background: white;
  border-left: 1px solid var(--el-border-color);
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
}

.sidebar-title {
  margin: 0;
  padding: 16px;
  font-size: 16px;
  font-weight: 500;
  border-bottom: 1px solid var(--el-border-color);
}

.case-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  
  &:first-child {
    border-bottom: 1px solid var(--el-border-color);
  }
}

.empty-case-tip {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.draggable-source {
  min-height: 200px;
}
</style>
