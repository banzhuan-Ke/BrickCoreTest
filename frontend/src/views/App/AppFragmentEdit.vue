<template>
  <el-card>
    <template #header><h3>{{ isNew ? '新建 App 片段' : '编辑 App 片段' }}</h3></template>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="片段名称" prop="name"><el-input v-model="form.name" maxlength="100" /></el-form-item>
      <el-form-item label="分类标签"><el-input v-model="form.tags" placeholder="如：登录、导航" /></el-form-item>
      <el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
      <el-form-item v-if="!isNew" label="版本"><el-tag type="info">v{{ form.version }}</el-tag></el-form-item>
    </el-form>
    <div class="steps-toolbar">
      <el-button plain type="primary" @click="fragmentPickerVisible = true">插入片段</el-button>
    </div>
    <StepEditor v-model:steps="form.steps" module="app" />
    <FragmentPickerDialog
      v-model="fragmentPickerVisible"
      domain="app"
      :exclude-fragment-id="isNew ? null : fragmentId"
      @insert="onFragmentInsert"
    />
    <div style="margin-top: 20px;">
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      <el-button @click="router.back()">取消</el-button>
    </div>
  </el-card>
</template>

<script setup>
import { computed, onMounted, provide, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { StepEditor } from '@/components/StepEditor'
import FragmentPickerDialog from '@/components/StepEditor/FragmentPickerDialog.vue'
import { appFragmentApi } from '@/api/modules/app'
import { ProjectStore } from '@/stores/module/ProjectStore'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const varInsertEnvId = ref(proStore.envList[0]?.id || null)
provide('varInsertEnvId', varInsertEnvId)
const fragmentId = route.params.id
const isNew = computed(() => !fragmentId || route.name === 'appFragmentNew')
const formRef = ref()
const saving = ref(false)
const fragmentPickerVisible = ref(false)

const form = reactive({
  name: '',
  tags: '',
  description: '',
  version: 1,
  steps: [],
})

const rules = { name: [{ required: true, message: '请输入片段名称', trigger: 'blur' }] }

function onFragmentInsert(refStep) {
  form.steps = [...(form.steps || []), refStep]
}

async function loadDetail() {
  if (isNew.value) return
  const res = await appFragmentApi.detail(fragmentId, proStore.projectInfo.id)
  const data = res.data?.data || res.data || {}
  form.name = data.name
  form.tags = data.tags || ''
  form.description = data.description || ''
  form.version = data.version || 1
  form.steps = data.steps || []
}

async function save() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload = {
      project_id: proStore.projectInfo.id,
      name: form.name,
      tags: form.tags,
      description: form.description,
      steps: form.steps,
    }
    if (isNew.value) {
      await appFragmentApi.create(payload)
    } else {
      await appFragmentApi.update(fragmentId, payload, proStore.projectInfo.id)
    }
    ElMessage.success('已保存')
    router.push({ name: 'appFragmentList' })
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadDetail)
</script>

<style scoped>
.steps-toolbar { margin: 12px 0; }
</style>
