<template>
  <el-button v-if="showButton" type="primary" plain @click="go">
    生成本轮迭代报告
  </el-button>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useCommunityEdition } from '@/composables/useCommunityEdition.js'
import { openIterationReportWizard } from '@/utils/knowledgeReportNav.js'

const props = defineProps({
  visible: { type: Boolean, default: true },
  reportType: { type: String, required: true },
  recordId: { type: [Number, String], required: true },
  title: { type: String, default: '' }
})

const router = useRouter()
const { isCommunityEdition, loadCommunityEdition } = useCommunityEdition()
const editionReady = ref(false)
const showButton = computed(() => props.visible && editionReady.value)

onMounted(async () => {
  await loadCommunityEdition()
  editionReady.value = true
})

function go() {
  if (!props.recordId) return
  openIterationReportWizard(router, {
    reportType: props.reportType,
    recordId: props.recordId,
    title: props.title || undefined
  })
}
</script>
