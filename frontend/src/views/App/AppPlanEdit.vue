<template>
  <el-container class="app-plan-edit-container">
    <PageCard>
      <template #title>
        <span>App 计划中的套件</span>
      </template>
      <template #main>
        <el-form :model="planInfo" label-width="auto" :rules="formRules" ref="formRef">
          <el-form-item label="计划名称" prop="name">
            <el-input v-model="planInfo.name" placeholder="请输入计划名称" />
          </el-form-item>
          <el-form-item label="所属目录">
            <CatalogTreeSelect
              v-model="planInfo.catalog_id"
              :project-id="proStore.projectInfo.id"
              placeholder="请选择所属目录"
            />
          </el-form-item>
          <el-form-item label="创建人">
            <el-input v-model="planInfo.username" disabled />
          </el-form-item>
          <el-form-item label="并行执行">
            <el-switch v-model="planInfo.parallel" active-text="套件按执行器权重分发" inactive-text="串行（单执行器）" />
            <div class="field-hint">开启后，运行计划时可选择多台 App Runner 并设置权重；套件内用例仍串行。</div>
          </el-form-item>
          <el-form-item label="录制视频">
            <el-switch v-model="planInfo.record_video" />
            <div class="field-hint">默认开启；执行时可覆盖。</div>
          </el-form-item>
        </el-form>

        <div class="title">计划中的套件</div>
        <div class="field-hint suite-order-hint">
          可从右侧 App 套件列表拖拽到下方；拖拽主要用于整理顺序与移除管理。
        </div>
        <draggable
          v-model="planInfo.suites"
          item-key="suite_id"
          :group="{ name: 'suite', pull: false, put: true }"
          handle=".sort_hand"
          chosen-class="chosen"
          drag-class="dragging"
          ghost-class="ghost"
          @add="handleAdd"
        >
          <template #item="{ element }">
            <div class="lines">
              <div class="name">{{ element.suite_name }}</div>
              <div class="create_time">{{ formatTime(element.create_time) }}</div>
              <div class="btn">
                <el-tooltip content="拖拽调整顺序" placement="bottom">
                  <el-button class="sort_hand" icon="Sort" circle type="success" plain />
                </el-tooltip>
                <el-tooltip content="从计划中移除" placement="bottom">
                  <el-button icon="Delete" circle type="danger" plain @click="removeSuite(element.suite_id)" />
                </el-tooltip>
                <el-tooltip content="编辑套件" placement="bottom">
                  <el-button
                    icon="Edit"
                    circle
                    type="primary"
                    plain
                    @click="router.push({ name: 'appSuiteEdit', params: { id: element.suite_id } })"
                  />
                </el-tooltip>
              </div>
            </div>
          </template>
        </draggable>
        <div class="line hint-line">
          <div class="info">可从右侧 App 套件列表拖拽套件到计划中</div>
        </div>
      </template>
      <template #bottom>
        <el-button type="primary" plain icon="SuccessFilled" :loading="saving" @click="savePlan">保存</el-button>
        <el-button plain icon="CircleCloseFilled" @click="goBack">关闭</el-button>
      </template>
    </PageCard>

    <AppSuiteSet />
  </el-container>
</template>

<script setup>
import { computed, onMounted, provide, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import draggable from 'vuedraggable'
import { ElNotification } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import AppSuiteSet from '@/views/App/components/AppSuiteSet.vue'
import { appPlanApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import dateTools from '@/tools/dateTools'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()
const planId = route.params.id
const formRef = ref()
const saving = ref(false)

const planInfo = reactive({
  name: '',
  catalog_id: null,
  username: '',
  parallel: false,
  record_video: true,
  suites: [],
})

const formRules = {
  name: [{ required: true, message: '计划名称不能为空', trigger: 'blur' }],
}

const addedSuiteIdSet = computed(() => {
  const suites = planInfo.suites
  if (!Array.isArray(suites)) return new Set()
  return new Set(suites.map((s) => s.suite_id))
})
provide('taskAddedSuiteIds', addedSuiteIdSet)

function formatTime(v) {
  return v ? dateTools.rTime(v) : '—'
}

async function loadDetail() {
  const [planRes, suitesRes] = await Promise.all([
    appPlanApi.detail(planId),
    appPlanApi.listSuites(planId),
  ])
  const plan = planRes.data || {}
  planInfo.name = plan.name || ''
  planInfo.catalog_id = plan.catalog_id ?? null
  planInfo.username = plan.username || uStore.userInfo?.username || ''
  planInfo.parallel = !!plan.parallel
  planInfo.record_video = plan.record_video !== false
  planInfo.suites = suitesRes.data?.suites || []
}

function removeSuite(suiteId) {
  planInfo.suites = planInfo.suites.filter((s) => s.suite_id !== suiteId)
}

async function refreshSuites() {
  const suitesRes = await appPlanApi.listSuites(planId)
  planInfo.suites = suitesRes.data?.suites || []
}

async function handleAdd() {
  await persistSuites(false)
  await refreshSuites()
}

async function persistSuites(showNotify = true) {
  const seen = new Set()
  const suiteIds = []
  for (const s of planInfo.suites || []) {
    if (!s?.suite_id || seen.has(s.suite_id)) continue
    seen.add(s.suite_id)
    suiteIds.push(s.suite_id)
  }
  planInfo.suites = (planInfo.suites || []).filter((s, idx, arr) =>
    arr.findIndex((x) => x.suite_id === s.suite_id) === idx
  )
  await appPlanApi.updateSuites(planId, { suite_ids: suiteIds })
  if (showNotify) {
    ElNotification.success('套件列表已保存')
  }
}

async function savePlan() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    await appPlanApi.update(planId, {
      name: planInfo.name,
      catalog_id: planInfo.catalog_id,
      parallel: planInfo.parallel,
      record_video: planInfo.record_video,
    })
    await persistSuites(false)
    ElNotification.success('计划保存成功')
    goBack()
  } catch (e) {
    ElNotification.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.back()
  uStore.deleteTabs(route.path)
}

onMounted(loadDetail)
</script>

<style scoped lang="scss">
@use '../Task/TaskEdit.scss';

.app-plan-edit-container {
  height: calc(100vh - 50px);
}

.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.suite-order-hint {
  margin: 4px 0 12px;
}

.hint-line {
  cursor: default;
}
</style>
