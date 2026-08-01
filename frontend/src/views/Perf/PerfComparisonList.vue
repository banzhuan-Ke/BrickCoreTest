<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">压测增强报告</div>
    </template>
    <template #main>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px;"
        title="增强报告含三类：对比（同场景对照）、汇总（分章并排）、合并+对比（分章+指标对照）。可在执行记录多选后生成，并可为各轮改显示名、附加 AI 提示词。"
      />
      <div class="toolbar">
        <el-radio-group v-model="kindFilter" size="default" @change="onFilterChange">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="compare">对比</el-radio-button>
          <el-radio-button label="merge">汇总</el-radio-button>
          <el-radio-button label="hybrid">合并+对比</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="createByFilter"
          placeholder="创建人"
          clearable
          style="width: 140px"
          @keyup.enter="onFilterChange"
          @clear="onFilterChange"
        />
        <el-date-picker
          v-model="dateRange"
          class="filter-date-range"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          size="default"
          @change="onFilterChange"
        />
        <el-button type="primary" :icon="Refresh" @click="fetchData">刷新</el-button>
        <el-button @click="resetFilters">重置</el-button>
        <el-button @click="router.push('/perf-records')">从执行记录生成</el-button>
        <el-button
          type="success"
          plain
          :disabled="selectedRows.length === 0"
          :loading="exporting"
          @click="handleBatchExport"
        >
          批量导出{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
        <el-button
          type="danger"
          plain
          :disabled="selectedRows.length === 0"
          @click="handleBatchDelete"
        >
          批量删除{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
      </div>

      <el-table
        :data="tableData"
        v-loading="loading"
        stripe
        row-key="id"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" align="center" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
        <el-table-column label="类型" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="kindTagType(reportKind(row))">
              {{ kindLabel(reportKind(row)) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="记录数" width="80" align="center">
          <template #default="{ row }">
            {{ (row.record_ids || []).length }}
          </template>
        </el-table-column>
        <el-table-column label="记录 ID" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            {{ (row.record_ids || []).join(', ') }}
          </template>
        </el-table-column>
        <el-table-column prop="reference_record_id" label="基准" width="80" align="center" />
        <el-table-column label="AI" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.ai_analysis?.summary" size="small" type="success">已有</el-tag>
            <el-tag v-else size="small" type="info">无</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="create_by" label="创建人" width="100" />
        <el-table-column prop="create_time" label="创建时间" width="160" />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="openDetail(row)">查看</el-button>
            <el-button size="small" :loading="exportingId === row.id" @click="exportOne(row)">导出</el-button>
            <el-button type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="onSizeChange"
          @current-change="fetchData"
        />
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { perfComparisonApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { resolveDownloadFilename } from '@/utils/downloadFilename'

const router = useRouter()
const proStore = ProjectStore()

const loading = ref(false)
const exporting = ref(false)
const exportingId = ref(null)
const tableData = ref([])
const page = ref(1)
const size = ref(20)
const total = ref(0)
const kindFilter = ref('')
const createByFilter = ref('')
const dateRange = ref(null)
const selectedRows = ref([])

const reportKind = (row) => row.kind || row.snapshot?.kind || 'compare'
const kindLabel = (k) => ({ merge: '汇总', hybrid: '合并+对比', compare: '对比' }[k] || '对比')
const kindTagType = (k) => ({ merge: 'success', hybrid: 'primary', compare: 'warning' }[k] || 'warning')

const downloadHtmlBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const kindPrefix = (row) => {
  const k = reportKind(row)
  return { merge: '汇总报告', hybrid: '合并对比报告', compare: '对比报告' }[k] || '对比报告'
}

const exportFilenameFor = (row, res) =>
  resolveDownloadFilename(res, {
    title: row.title || kindPrefix(row),
    fallback: kindPrefix(row),
    ext: '.html'
  })

const fetchData = async () => {
  if (!proStore.projectInfo?.id) return
  loading.value = true
  selectedRows.value = []
  try {
    const params = {
      project_id: proStore.projectInfo.id,
      page: page.value,
      size: size.value
    }
    if (kindFilter.value) params.kind = kindFilter.value
    if (createByFilter.value?.trim()) params.create_by = createByFilter.value.trim()
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    const res = await perfComparisonApi.getList(params)
    const data = res.data || res
    tableData.value = data.data || []
    total.value = data.total || 0
    // 当前页删空后回退上一页，避免空白页
    if (tableData.value.length === 0 && total.value > 0 && page.value > 1) {
      page.value -= 1
      await fetchData()
    }
  } catch (err) {
    console.error(err)
    ElMessage.error('获取增强报告列表失败')
  } finally {
    loading.value = false
  }
}

const onFilterChange = () => {
  page.value = 1
  fetchData()
}

const onSizeChange = () => {
  page.value = 1
  fetchData()
}

const resetFilters = () => {
  kindFilter.value = ''
  createByFilter.value = ''
  dateRange.value = null
  page.value = 1
  fetchData()
}

const handleSelectionChange = (selection) => {
  selectedRows.value = selection
}

const openDetail = (row) => {
  router.push(`/perf-comparisons/${row.id}`)
}

const exportOne = async (row) => {
  exportingId.value = row.id
  try {
    const res = await perfComparisonApi.exportHtml(row.id)
    const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: 'text/html' })
    downloadHtmlBlob(blob, exportFilenameFor(row, res))
    ElMessage.success('已导出')
  } catch (err) {
    console.error(err)
    ElMessage.error('导出失败')
  } finally {
    exportingId.value = null
  }
}

const handleBatchExport = async () => {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请选择要导出的报告')
    return
  }
  exporting.value = true
  let ok = 0
  try {
    for (const row of selectedRows.value) {
      try {
        const res = await perfComparisonApi.exportHtml(row.id)
        const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: 'text/html' })
        downloadHtmlBlob(blob, exportFilenameFor(row, res))
        ok += 1
      } catch (e) {
        console.error(e)
      }
    }
    if (ok === selectedRows.value.length) {
      ElMessage.success(`已导出 ${ok} 份 HTML`)
    } else if (ok > 0) {
      ElMessage.warning(`成功导出 ${ok}/${selectedRows.value.length} 份`)
    } else {
      ElMessage.error('批量导出失败')
    }
  } finally {
    exporting.value = false
  }
}

const handleDelete = async (row) => {
  const label =
    { merge: '汇总报告', hybrid: '合并+对比报告', compare: '对比报告' }[reportKind(row)] || '对比报告'
  try {
    await ElMessageBox.confirm(`确定删除${label}「${row.title}」吗？`, '提示', { type: 'warning' })
    await perfComparisonApi.delete(row.id)
    ElMessage.success('已删除')
    await fetchData()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const handleBatchDelete = async () => {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请选择要删除的报告')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedRows.value.length} 条增强报告吗？此操作不可恢复。`,
      '批量删除',
      { type: 'warning' }
    )
    const ids = selectedRows.value.map((r) => r.id)
    await perfComparisonApi.batchDelete(ids)
    ElMessage.success('批量删除成功')
    selectedRows.value = []
    await fetchData()
  } catch (err) {
    if (err !== 'cancel') {
      console.error(err)
      ElMessage.error(err?.response?.data?.detail || '批量删除失败')
    }
  }
}

onMounted(fetchData)
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
.filter-date-range {
  width: 260px;
}
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
