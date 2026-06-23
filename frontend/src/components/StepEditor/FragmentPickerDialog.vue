<template>
  <el-dialog
    v-model="visible"
    title="插入步骤片段"
    width="720px"
    destroy-on-close
    @open="loadList"
  >
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索片段名称"
        clearable
        style="width: 220px;"
        @keyup.enter="loadList"
      />
      <el-button type="primary" icon="Search" @click="loadList">搜索</el-button>
      <el-button link type="primary" @click="goManage">管理片段</el-button>
    </div>
    <el-table
      :data="fragmentList"
      v-loading="loading"
      highlight-current-row
      @current-change="onSelect"
      max-height="360"
      border
      stripe
    >
      <el-table-column prop="name" label="片段名称" min-width="140" show-overflow-tooltip />
      <el-table-column prop="tags" label="分类" width="100" show-overflow-tooltip />
      <el-table-column label="步骤数" width="80" align="center">
        <template #default="{ row }">{{ row.step_count }}</template>
      </el-table-column>
      <el-table-column label="版本" width="70" align="center">
        <template #default="{ row }">v{{ row.version }}</template>
      </el-table-column>
      <el-table-column prop="description" label="说明" min-width="160" show-overflow-tooltip />
    </el-table>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!selected" @click="confirm">插入</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { uiFragmentApi } from '@/api/modules/ui'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { buildFragmentRefStep } from '@/utils/stepHelper'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  excludeFragmentId: { type: [Number, String], default: null },
})
const emit = defineEmits(['update:modelValue', 'insert'])

const router = useRouter()
const proStore = ProjectStore()
const keyword = ref('')
const loading = ref(false)
const fragmentList = ref([])
const selected = ref(null)

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

async function loadList() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  loading.value = true
  try {
    const res = await uiFragmentApi.getList({
      project_id: projectId,
      keyword: keyword.value || undefined,
      page: 1,
      size: 100,
    })
    fragmentList.value = (res.data?.data?.items || []).filter(
      (row) => !props.excludeFragmentId || row.id !== Number(props.excludeFragmentId)
    )
  } finally {
    loading.value = false
  }
}

function onSelect(row) {
  selected.value = row
}

function confirm() {
  if (!selected.value) {
    ElMessage.warning('请选择一个片段')
    return
  }
  const frag = selected.value
  emit('insert', buildFragmentRefStep(frag))
  visible.value = false
  selected.value = null
}

function goManage() {
  visible.value = false
  router.push('/ui-fragments')
}
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}
</style>
