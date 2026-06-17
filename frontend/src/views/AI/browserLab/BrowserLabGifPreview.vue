<template>
  <div class="gif-preview-page">
    <div v-if="loading" class="hint">加载中…</div>
    <div v-else-if="error" class="hint error">{{ error }}</div>
    <img v-else-if="gifSrc" :src="gifSrc" alt="回放 GIF" class="gif-img" />
    <div v-else class="hint">暂无回放 GIF</div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { browserLabApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

const route = useRoute()
const taskId = computed(() => route.params.taskId)
const projectId = computed(() => {
  const q = route.query.project_id
  if (q != null && q !== '') return Number(q)
  return ProjectStore().projectInfo?.id
})

const loading = ref(false)
const error = ref('')
const gifSrc = ref('')
let objectUrl = ''

function revokeGif() {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl)
    objectUrl = ''
  }
  gifSrc.value = ''
}

async function loadGif() {
  error.value = ''
  revokeGif()
  if (!taskId.value) {
    error.value = '缺少任务 ID'
    return
  }
  if (!projectId.value) {
    error.value = '缺少项目 ID，请从执行记录/报告页打开链接'
    return
  }
  loading.value = true
  try {
    const res = await browserLabApi.getTask(taskId.value, projectId.value)
    if (res.data?.code !== 200) {
      error.value = res.data?.message || '加载失败'
      return
    }
    const task = res.data.data
    if (!task?.gif_url && !task?.gif_path) {
      error.value = '该任务未生成 GIF'
      return
    }
    const blob = await browserLabApi.fetchGifBlob(taskId.value, projectId.value)
    objectUrl = URL.createObjectURL(blob)
    gifSrc.value = objectUrl
    document.title = `回放 GIF #${taskId.value}`
  } catch (e) {
    error.value = e?.message || 'GIF 加载失败，请确认已登录且有查看权限'
  } finally {
    loading.value = false
  }
}

onMounted(loadGif)
watch([taskId, projectId], loadGif)
onBeforeUnmount(revokeGif)
</script>

<style scoped>
.gif-preview-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #111827;
  padding: 16px;
  box-sizing: border-box;
}
.gif-img {
  max-width: 100%;
  max-height: 100vh;
  object-fit: contain;
}
.hint {
  color: #9ca3af;
  font-size: 14px;
}
.hint.error {
  color: #f87171;
}
</style>
