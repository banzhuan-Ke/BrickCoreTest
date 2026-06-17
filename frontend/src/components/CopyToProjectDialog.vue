<template>
  <el-dialog v-model="visible" :title="title" width="480px" destroy-on-close @closed="reset">
    <el-form label-width="96px">
      <el-form-item label="目标项目" required>
        <el-select v-model="form.target_project_id" filterable placeholder="选择目标项目" style="width: 100%">
          <el-option
            v-for="p in projectOptions"
            :key="p.id"
            :label="p.name"
            :value="p.id"
            :disabled="p.id === currentProjectId"
          />
        </el-select>
      </el-form-item>
      <el-form-item v-if="showCatalog" label="目标目录">
        <CatalogTreeSelect
          v-model="form.target_catalog_id"
          :project-id="form.target_project_id || currentProjectId"
          placeholder="不选则保持原目录/无目录"
          clearable
        />
      </el-form-item>
      <el-form-item label="新名称">
        <el-input v-model="form.new_name" :placeholder="defaultNameHint" clearable />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">确定复制</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import { projectApi } from '@/api/modules/sys'
import { ProjectStore } from '@/stores/module/ProjectStore'

const props = defineProps({
  modelValue: Boolean,
  title: { type: String, default: '复制到其他项目' },
  assetName: { type: String, default: '' },
  showCatalog: { type: Boolean, default: true },
  submitFn: { type: Function, required: true },
})

const emit = defineEmits(['update:modelValue', 'success'])

const proStore = ProjectStore()
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const currentProjectId = computed(() => proStore.projectInfo?.id)
const projectOptions = ref([])
const submitting = ref(false)
const form = reactive({
  target_project_id: null,
  target_catalog_id: null,
  new_name: '',
})

const defaultNameHint = computed(() => (props.assetName ? `${props.assetName}_副本` : '留空则自动加 _副本'))

async function loadProjects() {
  try {
    const res = await projectApi.getProjectList({ page: 1, size: 200 })
    projectOptions.value = res.data?.data || res.data?.items || res.data || []
  } catch {
    projectOptions.value = []
  }
}

function reset() {
  form.target_project_id = null
  form.target_catalog_id = null
  form.new_name = ''
}

watch(visible, (v) => {
  if (v) loadProjects()
})

async function submit() {
  if (!form.target_project_id) {
    ElMessage.warning('请选择目标项目')
    return
  }
  submitting.value = true
  try {
    await props.submitFn({
      target_project_id: form.target_project_id,
      target_catalog_id: form.target_catalog_id || undefined,
      new_name: form.new_name?.trim() || undefined,
    })
    ElMessage.success('复制成功')
    visible.value = false
    emit('success')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '复制失败')
  } finally {
    submitting.value = false
  }
}
</script>
