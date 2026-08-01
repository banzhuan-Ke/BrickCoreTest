<template>
  <el-container class="suite-edit-container">
    <KeywordSidebar
      v-model="activeGroups"
      title="前置步骤操作"
      :groups="keywordGroups"
    />

    <!-- 中间 + 右侧（可拖拽调整宽度） -->
    <div class="suite-workspace">
      <div class="suite-main">
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
      </div>

      <div
        class="panel-resizer"
        :class="{ 'is-active': isResizing }"
        title="拖拽调整宽度"
        @mousedown="onResizeStart"
      />

      <!-- 右侧：套件用例 + 用例集 -->
      <aside class="case-sidebar" :style="{ width: `${rightWidth}px` }">
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
      </aside>
    </div>
  </el-container>
</template>

<script setup>
import { reactive, ref, computed, watch, provide } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { StepEditor, KeywordSidebar } from '@/components/StepEditor'
import { ProjectStore } from '@/stores/module/ProjectStore'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import { UserStore } from '@/stores/module/UserStore'
import http from '@/api/index'
import { ElNotification } from 'element-plus'
import ActionGroup from '@/datas/ActionGroup.js'
import CaseSet from './componets/CaseSet.vue'
import { useSplitPanelResize } from '@/composables/useSplitPanelResize'
import {
  Check, Close,
  Document, Edit, Clock, Search,
  MessageBox, MoreFilled, Share, Mouse
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const proStore = ProjectStore()
const userStore = UserStore()

const { rightWidth, isResizing, onResizeStart } = useSplitPanelResize({
  storageKey: 'suite-edit-right-panel-width',
  defaultWidth: 560,
})

const formRef = ref()
const saving = ref(false)

provide('suiteAddedCaseIds', ref(new Set()))

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
const activeGroups = ref(['1', '2', '2b', '3', '4', '5', '6', '7', '8'])

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
@use '@/styles/suite-edit-layout.scss';

.suite-strategy-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
</style>
