<template>
  <div class="tm-release-list">
    <div class="toolbar">
      <el-input
        v-model="keyword"
        clearable
        placeholder="搜索版本键 / 名称"
        style="width: 220px"
        @keyup.enter="load"
      />
      <el-select v-model="status" clearable placeholder="状态" style="width: 140px" @change="load">
        <el-option
          v-for="s in statusOptions"
          :key="s"
          :label="releaseStatusLabel(s)"
          :value="s"
        />
      </el-select>
      <el-button type="primary" @click="load">查询</el-button>
      <el-button v-if="canEdit" type="success" @click="openCreate">新建版本</el-button>
      <el-button v-if="canEdit" type="primary" plain @click="openAgileCreate">新建敏捷迭代</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe>
      <el-table-column prop="release_key" label="版本键" width="140" />
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }">
          <el-tag size="small">{{ releaseStatusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="quality_status" label="质量" width="120">
        <template #default="{ row }">
          <el-tag
            v-if="row.quality_status"
            size="small"
            :type="qualityStatusTagType(row.quality_status)"
          >{{ qualityStatusLabel(row.quality_status) }}</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="planned_release_at" label="计划发布" width="170">
        <template #default="{ row }">{{ formatTime(row.planned_release_at) }}</template>
      </el-table-column>
      <el-table-column prop="create_by" label="创建人" width="100" />
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">{{ formatTime(row.update_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right" class-name="ops-col">
        <template #default="{ row }">
          <div class="row-ops">
            <el-button link type="primary" @click="goDetail(row.id)">详情</el-button>
            <el-dropdown
              v-if="canEdit && allowedReleaseTransitions(row.status).length"
              trigger="click"
              @command="(cmd) => doTransition(row, cmd)"
            >
              <el-button link type="warning">
                变更状态
                <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu class="release-status-menu">
                  <el-dropdown-item
                    v-for="t in allowedReleaseTransitions(row.status)"
                    :key="t"
                    :command="t"
                  >
                    <span class="status-from">{{ releaseStatusLabel(row.status) }}</span>
                    <span class="status-arrow">→</span>
                    <span class="status-to">{{ releaseStatusLabel(t) }}</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button
              v-if="canEdit && releaseDeletable(row.status)"
              link
              type="danger"
              @click="removeRelease(row)"
            >删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="createVisible"
      :title="agileCreate ? '新建敏捷迭代' : '新建版本'"
      width="520px"
      destroy-on-close
    >
      <el-alert
        v-if="agileCreate"
        type="info"
        :closable="false"
        show-icon
        class="agile-tip"
        title="敏捷迭代模式"
        description="创建后自动进入「测试中」，并在版本概览展示 Phase 0–1 向导（功能用例优先）。"
      />
      <el-form :model="form" label-width="100px">
        <el-form-item label="版本键" required>
          <el-input v-model="form.release_key" placeholder="如 2026.08.0" maxlength="64" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="200" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="外部链接">
          <el-input v-model="form.external_url" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { testReleaseApi } from '@/api/testManagement'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import {
  allowedReleaseTransitions,
  qualityStatusLabel,
  qualityStatusTagType,
  releaseDeletable,
  releaseStatusLabel
} from '@/utils/testReleaseStatus'
import { confirmReleaseStatusChange } from '@/utils/releaseQualityConfirm'

const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()

const canEdit = computed(() => uStore.hasPermission('test_release:edit'))
const canQualityView = computed(() => uStore.hasPermission('test_quality:view'))
const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const keyword = ref('')
const status = ref('')
const createVisible = ref(false)
const agileCreate = ref(false)
const form = reactive({
  release_key: '',
  name: '',
  description: '',
  external_url: ''
})

const statusOptions = ['draft', 'testing', 'ready', 'released', 'archived']
const formatTime = (v) => (v ? String(v).replace('T', ' ').slice(0, 19) : '—')
const projectId = computed(() => proStore.projectInfo?.id)

const load = async () => {
  if (!projectId.value) {
    rows.value = []
    return
  }
  loading.value = true
  try {
    const res = await testReleaseApi.list({
      project_id: projectId.value,
      keyword: keyword.value || undefined,
      status: status.value || undefined
    })
    rows.value = res.data?.data || []
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  agileCreate.value = false
  form.release_key = ''
  form.name = ''
  form.description = ''
  form.external_url = ''
  createVisible.value = true
}

const openAgileCreate = () => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  agileCreate.value = true
  const d = new Date()
  const tag = `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}`
  form.release_key = tag
  form.name = `迭代 ${tag}`
  form.description = '敏捷迭代 · 功能测试优先'
  form.external_url = ''
  createVisible.value = true
}

const submitCreate = async () => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!form.release_key.trim() || !form.name.trim()) {
    ElMessage.warning('请填写版本键与名称')
    return
  }
  saving.value = true
  try {
    const res = await testReleaseApi.create({
      project_id: projectId.value,
      release_key: form.release_key.trim(),
      name: form.name.trim(),
      description: form.description || null,
      external_url: form.external_url || null
    })
    ElMessage.success(agileCreate.value ? '敏捷迭代已创建' : '已创建')
    createVisible.value = false
    const id = res.data?.data?.id
    if (id) {
      if (agileCreate.value && res.data?.data?.status === 'draft') {
        try {
          await testReleaseApi.transition(id, projectId.value, 'testing')
        } catch {
          /* 无权限或已切换则忽略 */
        }
      }
      router.push(`/test-releases/${id}?tab=overview`)
    } else await load()
  } finally {
    saving.value = false
  }
}

const goDetail = (id) => router.push(`/test-releases/${id}`)

const doTransition = async (row, target) => {
  const ok = await confirmReleaseStatusChange({
    target,
    releaseId: row.id,
    projectId: projectId.value,
    releaseName: row.name || row.release_key || '',
    canViewQuality: canQualityView.value
  })
  if (!ok) return
  try {
    const res = await testReleaseApi.transition(row.id, projectId.value, target)
    const data = res.data?.data
    const warnings = data?.warnings || []
    ElMessage.success(`已变更为 ${releaseStatusLabel(target)}`)
    if (warnings.length) {
      ElMessage.warning(warnings.join('；'))
    }
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '状态变更失败')
  }
}

const removeRelease = async (row) => {
  await ElMessageBox.confirm(`删除版本 ${row.release_key}？`, '确认', { type: 'warning' })
  await testReleaseApi.remove(row.id, projectId.value)
  ElMessage.success('已删除')
  await load()
}

watch(projectId, () => load())
onMounted(load)
</script>

<style scoped>
.tm-release-list {
  padding: 16px;
}
.agile-tip {
  margin-bottom: 16px;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}
.row-ops {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
}
:deep(.release-status-menu .el-dropdown-menu__item) {
  min-width: 180px;
}
.status-from {
  color: #909399;
  margin-right: 6px;
}
.status-arrow {
  margin: 0 6px;
  color: #c0c4cc;
}
.status-to {
  font-weight: 600;
  color: #303133;
}
</style>
