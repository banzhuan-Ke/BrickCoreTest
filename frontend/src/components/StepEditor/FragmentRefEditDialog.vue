<template>
  <el-dialog
    v-model="visible"
    title="配置片段引用"
    width="560px"
    destroy-on-close
    @open="onOpen"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
      片段内可使用 <code v-pre>${{fragment.变量名}}</code> 占位；此处填写引用时的入参，也支持 <code v-pre>${{环境变量}}</code>。
    </el-alert>

    <el-descriptions :column="1" border size="small" style="margin-bottom: 16px;">
      <el-descriptions-item label="片段名称">{{ localStep.params?.fragment_name || '—' }}</el-descriptions-item>
      <el-descriptions-item label="引用版本">
        v{{ localStep.params?.fragment_version || '?' }}
        <el-tag v-if="outdated" size="small" type="warning" style="margin-left: 8px;">片段已有新版本 v{{ latestVersion }}</el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <div v-if="placeholderNames.length" class="vars-section">
      <div class="vars-title">片段变量</div>
      <el-form label-width="120px" size="default">
        <el-form-item v-for="name in placeholderNames" :key="name" :label="name">
          <el-input
            v-model="variables[name]"
            :placeholder="`例如 13800138000 或 \${{username}}`"
            clearable
          />
        </el-form-item>
      </el-form>
    </div>
    <el-empty v-else description="该片段未定义 ${{fragment.xxx}} 占位变量" :image-size="64" />

    <el-form label-width="120px" size="default" style="margin-top: 8px;">
      <el-form-item label="自定义变量">
        <div class="custom-vars">
          <div v-for="(row, idx) in customRows" :key="idx" class="custom-var-row">
            <el-input v-model="row.key" placeholder="变量名" style="width: 140px;" />
            <el-input v-model="row.value" placeholder="值" />
            <el-button link type="danger" @click="removeCustomRow(idx)">删除</el-button>
          </div>
          <el-button link type="primary" @click="addCustomRow">+ 添加变量</el-button>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button v-if="outdated" type="warning" plain @click="syncVersion">同步最新版本号</el-button>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="save">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { uiFragmentApi } from '@/api/modules/ui'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { extractFragmentVarNames, normalizeFragmentVariables } from '@/utils/fragmentVars'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  step: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue', 'save'])

const proStore = ProjectStore()
const localStep = ref({ params: {} })
const placeholderNames = ref([])
const variables = reactive({})
const customRows = ref([])
const latestVersion = ref(null)
const outdated = ref(false)

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

function addCustomRow() {
  customRows.value.push({ key: '', value: '' })
}

function removeCustomRow(idx) {
  customRows.value.splice(idx, 1)
}

async function onOpen() {
  localStep.value = JSON.parse(JSON.stringify(props.step || { params: {} }))
  placeholderNames.value = []
  Object.keys(variables).forEach((k) => delete variables[k])
  customRows.value = []

  const fid = localStep.value.params?.fragment_id
  const projectId = proStore.projectInfo?.id
  if (!fid || !projectId) return

  try {
    const res = await uiFragmentApi.getDetail(fid, projectId)
    const frag = res.data?.data || {}
    placeholderNames.value = extractFragmentVarNames(frag.steps || [])
    const normalized = normalizeFragmentVariables(
      localStep.value.params?.variables,
      placeholderNames.value,
    )
    Object.assign(variables, normalized)

    const known = new Set(placeholderNames.value)
    customRows.value = Object.entries(localStep.value.params?.variables || {})
      .filter(([k]) => !known.has(k))
      .map(([key, value]) => ({ key, value: value ?? '' }))

    latestVersion.value = frag.version
    const pinned = localStep.value.params?.fragment_version
    outdated.value = pinned != null && latestVersion.value != null && pinned < latestVersion.value
  } catch {
    ElMessage.warning('加载片段详情失败')
  }
}

function syncVersion() {
  if (!latestVersion.value) return
  localStep.value.params = {
    ...localStep.value.params,
    fragment_version: latestVersion.value,
  }
  outdated.value = false
  ElMessage.success('已同步至最新版本号')
}

function save() {
  const vars = { ...variables }
  for (const row of customRows.value) {
    const key = (row.key || '').trim()
    if (key) vars[key] = row.value ?? ''
  }
  const updated = {
    ...localStep.value,
    params: {
      ...localStep.value.params,
      variables: vars,
    },
  }
  emit('save', updated)
  visible.value = false
}
</script>

<style scoped>
.vars-title {
  font-weight: 500;
  margin-bottom: 8px;
}
.custom-vars {
  width: 100%;
}
.custom-var-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.custom-var-row .el-input:last-of-type {
  flex: 1;
}
</style>
