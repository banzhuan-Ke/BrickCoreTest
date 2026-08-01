<template>
  <div v-if="showBridge" class="report-knowledge-bridge">
    <el-button link type="primary" @click="goSearch">资料检索</el-button>
    <el-button link type="primary" @click="goFolders">打开迭代资料库</el-button>
    <el-button link type="primary" @click="goReportWizard">报告向导</el-button>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useCommunityEdition } from '@/composables/useCommunityEdition.js'
import { openIterationReportWizard } from '@/utils/knowledgeReportNav.js'

const props = defineProps({
  visible: { type: Boolean, default: true },
  projectId: { type: [Number, String], default: null },
  reportType: { type: String, default: '' },
  recordId: { type: [Number, String], default: null },
  folderId: { type: [Number, String], default: null },
  title: { type: String, default: '' }
})

const router = useRouter()
const { isCommunityEdition, loadCommunityEdition } = useCommunityEdition()
const editionReady = ref(false)
const showBridge = computed(() => props.visible && editionReady.value)

onMounted(async () => {
  await loadCommunityEdition()
  editionReady.value = true
})

function goSearch() {
  const query = {}
  if (props.folderId) query.folder_id = String(props.folderId)
  router.push({ path: '/ai-knowledge/search', query })
}

function goFolders() {
  if (props.folderId) {
    router.push(`/ai-knowledge/folders/${props.folderId}`)
  } else {
    router.push('/ai-knowledge/folders')
  }
}

function goReportWizard() {
  if (props.reportType && props.recordId) {
    openIterationReportWizard(router, {
      reportType: props.reportType,
      recordId: props.recordId,
      title: props.title || undefined
    })
    return
  }
  router.push('/ai-knowledge/reports')
}
</script>

<style scoped>
.report-knowledge-bridge {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  margin-bottom: 6px;
}
</style>
