<template>
  <PageCard>
    <template #title>
      <div class="workspace-head">
        <el-button @click="router.push('/ai-testing')" icon="ArrowLeft">返回需求列表</el-button>
        <span class="req-name">{{ req?.name || '需求工作台' }}</span>
        <el-tag v-if="req" size="small" type="info">#{{ reqId }}</el-tag>
        <el-tag v-if="req?.file_name" size="small">{{ req.file_name }}</el-tag>
        <el-tag v-else-if="req?.source_type === 'xmind'" size="small" type="warning">XMind 导入</el-tag>
      </div>
    </template>
    <template #main>
      <div v-loading="loading">
        <el-tabs v-model="activeTab" @tab-change="onTabChange">
          <el-tab-pane label="概览" name="overview">
            <RequirementOverviewPanel v-if="req" :req="req" :overview="overview" @navigate="switchTab" />
          </el-tab-pane>
          <el-tab-pane label="需求文档与配置" name="document" lazy>
            <AiRequirement
              v-if="req && activeTab === 'document'"
              embed-mode
              :embed-req-id="reqId"
              embed-section="document"
            />
          </el-tab-pane>
          <el-tab-pane label="思维导图" name="mindmap" lazy>
            <AiTestAnalysis
              v-if="req && activeTab === 'mindmap'"
              embed-mode
              :embed-req-id="reqId"
              embed-tab="mindmap"
            />
          </el-tab-pane>
          <el-tab-pane label="测试点" name="points" lazy>
            <AiTestAnalysis
              v-if="req && activeTab === 'points'"
              embed-mode
              :embed-req-id="reqId"
              embed-tab="points"
              :highlight-point-id="highlightPointId"
            />
          </el-tab-pane>
          <el-tab-pane label="测试方案" name="schemes" lazy>
            <AiTestAnalysis
              v-if="req && activeTab === 'schemes'"
              embed-mode
              :embed-req-id="reqId"
              embed-tab="scheme"
            />
          </el-tab-pane>
          <el-tab-pane label="功能用例" name="cases" lazy>
            <AiRequirement
              v-if="req && activeTab === 'cases'"
              embed-mode
              :embed-req-id="reqId"
              embed-section="cases"
              :highlight-point-id="highlightPointId"
              :key="`cases-${route.query.sourceRef || ''}`"
            />
          </el-tab-pane>
        </el-tabs>
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import AiRequirement from '@/views/AI/AiRequirement.vue'
import AiTestAnalysis from '@/views/AI/AiTestAnalysis.vue'
import RequirementOverviewPanel from '@/views/AI/testing/RequirementOverviewPanel.vue'
import { aiRequirementApi, aiTestAnalysisApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

const props = defineProps({
  reqId: { type: [Number, String], required: true }
})

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const req = ref(null)
const overview = ref({})
const loading = ref(false)
const activeTab = ref('overview')

const highlightPointId = computed(() => {
  const raw = route.query.pointId
  return raw ? Number(raw) : null
})

const loadReq = async () => {
  if (!proStore.projectInfo?.id) {
    ElMessage.warning('请先在顶部导航栏选择项目')
    return
  }
  loading.value = true
  try {
    const id = Number(props.reqId)
    const [detailRes, overviewRes] = await Promise.all([
      aiRequirementApi.getDetail(id, proStore.projectInfo.id),
      aiTestAnalysisApi.getOverview(id, proStore.projectInfo.id)
    ])
    if (detailRes.data?.code === 200) req.value = detailRes.data.data
    if (overviewRes.data?.code === 200) {
      overview.value = overviewRes.data.data?.overview || {}
    }
  } finally {
    loading.value = false
  }
}

const syncTabFromRoute = () => {
  let tab = route.query.tab
  if (tab === 'config') tab = 'document'
  if (tab && typeof tab === 'string') activeTab.value = tab
}

const onTabChange = (name) => {
  router.replace({
    name: 'aiTestingWorkspace',
    params: { reqId: props.reqId },
    query: { ...route.query, tab: name, pointId: name === 'points' || name === 'cases' ? route.query.pointId : undefined }
  })
  if (name === 'overview') loadReq()
}

const switchTab = (name) => {
  activeTab.value = name
  onTabChange(name)
}

watch(() => route.query.tab, syncTabFromRoute)
watch(() => route.query.sourceRef, () => {
  if (activeTab.value === 'cases') activeTab.value = 'cases'
})
watch(() => props.reqId, () => {
  loadReq()
  syncTabFromRoute()
})

onMounted(async () => {
  syncTabFromRoute()
  await loadReq()
})
</script>

<style scoped>
.workspace-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
}
.req-name {
  max-width: 480px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
