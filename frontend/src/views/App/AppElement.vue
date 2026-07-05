<template>
  <PageCard>
    <template #title>
      <el-button v-if="canEdit" size="small" type="primary" icon="Plus" @click="openCreate">元素</el-button>
      <el-button v-if="canEdit" size="small" type="success" plain icon="Aim" @click="goInspector">打开元素探查</el-button>
    </template>
    <template #main>
      <AppH5UsageGuide scope="element" title="App 元素库：H5 与图像识别说明" />
      <div style="margin-bottom: 12px; display: flex; gap: 10px; flex-wrap: wrap;">
        <el-input v-model="searchForm.name" placeholder="搜索元素名" clearable style="width: 200px" @keyup.enter="loadList" />
        <el-select v-model="searchForm.element_type" clearable placeholder="类型" style="width: 120px" @change="loadList">
          <el-option label="控件" value="control" />
          <el-option label="图像" value="image" />
        </el-select>
        <el-button type="primary" icon="Search" @click="loadList">搜索</el-button>
      </div>
      <el-table :data="elementList" stripe :header-cell-style="{ 'text-align': 'center' }" :cell-style="{ 'text-align': 'center' }">
        <el-table-column type="index" label="序号" width="70" />
        <el-table-column prop="name" label="元素名" min-width="140" show-overflow-tooltip />
        <el-table-column prop="element_type" label="类型" width="90">
          <template #default="{ row }">{{ row.element_type === 'image' ? '图像' : '控件' }}</template>
        </el-table-column>
        <el-table-column label="定位器" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ formatLocator(row.locator) }}</template>
        </el-table-column>
        <el-table-column label="预览" width="90">
          <template #default="{ row }">
            <el-image
              v-if="row.element_type === 'image' && templatePreviewUrl(row.locator)"
              :src="templatePreviewUrl(row.locator)"
              fit="contain"
              style="width: 48px; height: 48px"
            />
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
        <el-table-column label="引用" width="72">
          <template #default="{ row }">
            <el-tag v-if="row.ref_total > 0" size="small" type="warning">{{ row.ref_total }}</el-tag>
            <span v-else class="muted-ref">0</span>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="创建人" width="100" />
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button v-if="canEdit" type="primary" plain size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canEdit" type="danger" plain size="small" @click="removeRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
    <template #bottom>
      <el-pagination
        v-model:current-page="page.page"
        v-model:page-size="page.size"
        :total="page.total"
        layout="total, sizes, prev, pager, next"
        @current-change="loadList"
        @size-change="loadList"
      />
    </template>
  </PageCard>

  <el-dialog v-model="dlgVisible" :title="dlgTitle" width="680px" destroy-on-close @closed="resetForm">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
      <el-form-item label="元素名" prop="name">
        <el-input v-model="form.name" maxlength="100" placeholder="逻辑名，步骤中 locator_ref 引用" />
      </el-form-item>
      <el-form-item label="类型" prop="element_type">
        <el-select v-model="form.element_type" style="width: 100%" @change="onElementTypeChange">
          <el-option label="控件" value="control" />
          <el-option label="图像识别" value="image" />
        </el-select>
      </el-form-item>

      <template v-if="form.element_type === 'image'">
        <el-form-item label="识别小图" required>
          <div class="image-upload-row">
            <el-upload
              :show-file-list="false"
              accept="image/png,image/jpeg,image/webp"
              :http-request="handleTemplateUpload"
              :disabled="uploading"
            >
              <el-button type="primary" plain :loading="uploading">上传识别图</el-button>
            </el-upload>
            <el-image
              v-if="templatePreviewSrc"
              :src="templatePreviewSrc"
              fit="contain"
              class="template-preview"
              :preview-src-list="[templatePreviewSrc]"
            />
          </div>
          <div v-if="form.locator.value" class="template-path">{{ form.locator.value }}</div>
          <div class="field-hint">上传<strong>要点击或要识别的 UI 局部截图</strong>（按钮/图标等），不要上传整页截图；也可在元素探查中框选后保存。</div>
        </el-form-item>
        <el-form-item label="相似度阈值">
          <el-slider v-model="form.locator.threshold" :min="0.5" :max="1" :step="0.05" show-input :show-input-controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="RGB 匹配">
          <el-switch v-model="form.locator.rgb" />
        </el-form-item>
        <el-form-item label="中心偏移">
          <el-input
            :model-value="formatLocatorPair(form.locator.record_pos)"
            placeholder="相对屏幕中心偏移，如 0.12,-0.05"
            @update:model-value="(v) => setLocatorPair(form.locator, 'record_pos', v)"
          />
          <div class="field-hint">录制时识别图中心相对屏幕中心的偏移（可选；跨分辨率时建议填写，元素探查保存会自动带入）</div>
        </el-form-item>
        <el-form-item label="录制分辨率">
          <el-input
            :model-value="formatLocatorPair(form.locator.resolution)"
            placeholder="宽,高，如 1080,2400"
            @update:model-value="(v) => setLocatorPair(form.locator, 'resolution', v)"
          />
          <div class="field-hint">截取识别图时手机屏幕分辨率（可选；跨分辨率时建议填写）</div>
        </el-form-item>
      </template>

      <template v-else>
        <el-form-item label="元素上下文">
          <el-select v-model="form.locator.context" style="width: 100%" @change="onLocatorContextChange">
            <el-option label="原生 (Android UI)" :value="APP_LOCATOR_CONTEXT_NATIVE" />
            <el-option label="H5 WebView" value="webview" />
          </el-select>
          <div class="field-hint">原生控件用 resource_id / text 等；H5 页面内元素选 WebView</div>
        </el-form-item>
        <el-form-item label="定位方式" required>
          <el-select v-model="form.locator.by" style="width: 100%">
            <el-option v-for="opt in currentLocatorByOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="定位值" required>
          <el-input v-model="form.locator.value" placeholder="如 resource_id、文本内容、css 选择器等" />
        </el-form-item>
        <el-form-item v-if="!isWebviewLocator(form.locator)" label="匹配序号">
          <el-input-number
            v-model="form.locator.index"
            :min="1"
            :max="99"
            controls-position="right"
            style="width: 140px"
          />
          <span class="field-hint inline">同一定位匹配多个控件时，取第几个（从 1 开始）</span>
        </el-form-item>
        <template v-if="isWebviewLocator(form.locator)">
          <el-form-item label="H5 来源">
            <el-radio-group v-model="form.locator.devtools_source">
              <el-radio value="webview">App WebView</el-radio>
              <el-radio value="chrome">手机 Chrome</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="页面索引">
            <el-input-number v-model="form.locator.page_index" :min="0" :max="99" controls-position="right" style="width: 120px" />
            <span class="field-hint inline">与元素探查探测时的可调试页面序号一致</span>
          </el-form-item>
        </template>
      </template>

      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dlgVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import AppH5UsageGuide from '@/components/App/AppH5UsageGuide.vue'
import { appElementApi } from '@/api'
import { APP_LOCATOR_BY_OPTIONS, APP_WEBVIEW_LOCATOR_BY_OPTIONS } from '@/datas/AppActionGroup.js'
import { isWebviewLocator, APP_LOCATOR_CONTEXT_NATIVE } from '@/utils/appStepMeta.js'
import { presignTemplateKeys, resolveTemplatePreviewUrl } from '@/utils/appTemplatePresign.js'
import { getApiErrorMessage, isDuplicateElementNameError } from '@/utils/apiError.js'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'

const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()

const canEdit = computed(() => uStore.hasPermission('app_element:edit') || uStore.hasPermission('app_case:edit'))
const nativeLocatorOptions = APP_LOCATOR_BY_OPTIONS.filter((o) => o.value !== 'image')

const currentLocatorByOptions = computed(() =>
  isWebviewLocator(form.locator) ? APP_WEBVIEW_LOCATOR_BY_OPTIONS : nativeLocatorOptions
)

const elementList = ref([])
const page = reactive({ page: 1, size: 10, total: 0 })
const searchForm = reactive({ name: '', element_type: '' })
const dlgVisible = ref(false)
const saving = ref(false)
const uploading = ref(false)
const templatePreviewUrlMap = ref({})
const editingId = ref(null)
const formRef = ref()
const form = reactive({
  name: '',
  element_type: 'control',
  locator: { by: 'resource_id', value: '', index: 1 },
  remark: '',
})
const rules = {
  name: [{ required: true, message: '请输入元素名', trigger: 'blur' }],
}

const dlgTitle = computed(() => (editingId.value ? '编辑元素' : '新建元素'))

const templatePreviewSrc = computed(() =>
  resolveTemplatePreviewUrl(form.locator?.value, templatePreviewUrlMap.value)
)

function defaultImageLocator() {
  return { by: 'image', value: '', threshold: 0.8, rgb: false }
}

function formatLocatorPair(value) {
  if (value == null || value === '') return ''
  if (Array.isArray(value) && value.length >= 2) return `${value[0]},${value[1]}`
  if (typeof value === 'object' && value.x != null && value.y != null) return `${value.x},${value.y}`
  return String(value)
}

function setLocatorPair(loc, field, text) {
  if (!loc) return
  const parts = String(text || '').split(',').map((s) => s.trim()).filter(Boolean)
  if (parts.length >= 2) {
    const a = Number(parts[0])
    const b = Number(parts[1])
    if (!Number.isNaN(a) && !Number.isNaN(b)) loc[field] = [a, b]
  } else {
    delete loc[field]
  }
}

function defaultControlLocator() {
  return { by: 'resource_id', value: '', index: 1, context: APP_LOCATOR_CONTEXT_NATIVE }
}

function normalizeLocatorContext(locator) {
  if (!locator || typeof locator !== 'object') return
  if (!locator.context || locator.context === 'native') {
    locator.context = APP_LOCATOR_CONTEXT_NATIVE
  }
}

function formatLocator(locator) {
  if (!locator || typeof locator !== 'object') return ''
  const v = locator.value ?? ''
  if (locator.by === 'image') {
    const th = locator.threshold != null ? ` threshold=${locator.threshold}` : ''
    return `image=${typeof v === 'object' ? JSON.stringify(v) : v}${th}`
  }
  const prefix = locator.context === 'webview' ? '[WebView] ' : ''
  return `${prefix}${locator.by || ''}=${typeof v === 'object' ? JSON.stringify(v) : v}`
}

function templatePreviewUrl(locator) {
  return resolveTemplatePreviewUrl(locator?.value, templatePreviewUrlMap.value)
}

async function hydrateTemplatePreviews(rows) {
  const keys = (rows || [])
    .filter((r) => r.element_type === 'image')
    .map((r) => r.locator?.value)
    .filter(Boolean)
  const urlMap = await presignTemplateKeys(keys, proStore.projectInfo.id)
  templatePreviewUrlMap.value = { ...templatePreviewUrlMap.value, ...urlMap }
}

function onElementTypeChange(type) {
  if (type === 'image') {
    form.locator = defaultImageLocator()
  } else {
    form.locator = { by: 'resource_id', value: '', index: 1, context: APP_LOCATOR_CONTEXT_NATIVE }
  }
}

function onLocatorContextChange() {
  if (form.locator.context === 'webview' && !['css', 'xpath', 'text', 'id'].includes(form.locator.by)) {
    form.locator.by = 'css'
  }
  if (form.locator.context === APP_LOCATOR_CONTEXT_NATIVE && ['css', 'id'].includes(form.locator.by)) {
    form.locator.by = 'resource_id'
  }
  if (form.locator.context === 'webview') {
    if (form.locator.devtools_source == null) form.locator.devtools_source = 'webview'
    if (form.locator.page_index == null) form.locator.page_index = 0
  } else {
    delete form.locator.devtools_source
    delete form.locator.page_index
  }
}

async function handleTemplateUpload(options) {
  const file = options.file
  if (!file) return
  uploading.value = true
  try {
    const res = await appElementApi.uploadTemplate(proStore.projectInfo.id, file)
    const data = res.data?.data || res.data
    const objectKey = data?.object_key || ''
    const accessUrl = data?.access_url || ''
    if (!objectKey) {
      ElMessage.error('上传失败：未返回 object_key')
      return
    }
    form.locator.value = objectKey
    if (accessUrl) {
      templatePreviewUrlMap.value = { ...templatePreviewUrlMap.value, [objectKey]: accessUrl }
    }
    ElMessage.success('识别图已上传')
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e, '识别图上传失败'))
  } finally {
    uploading.value = false
  }
}

async function loadList() {
  const res = await appElementApi.list({
    project_id: proStore.projectInfo.id,
    page: page.page,
    size: page.size,
    name: searchForm.name || undefined,
    element_type: searchForm.element_type || undefined,
  })
  const rows = res.data?.data || []
  page.total = res.data?.total || 0
  elementList.value = await Promise.all(
    rows.map(async (row) => {
      try {
        const refRes = await appElementApi.references(row.id)
        const refs = refRes.data?.data || refRes.data || {}
        return { ...row, ref_total: refs.total || 0 }
      } catch {
        return { ...row, ref_total: 0 }
      }
    }),
  )
  await hydrateTemplatePreviews(elementList.value)
}

function goInspector() {
  router.push({ name: 'appInspector' })
}

function resetForm() {
  editingId.value = null
  form.name = ''
  form.element_type = 'control'
  form.locator = defaultControlLocator()
  form.remark = ''
}

function openCreate() {
  resetForm()
  dlgVisible.value = true
}

async function openEdit(row) {
  editingId.value = row.id
  form.name = row.name
  form.element_type = row.element_type || 'control'
  if (row.element_type === 'image') {
    form.locator = {
      by: 'image',
      value: row.locator?.value || '',
      threshold: row.locator?.threshold ?? 0.8,
      rgb: !!row.locator?.rgb,
      record_pos: row.locator?.record_pos,
      resolution: row.locator?.resolution,
    }
  } else {
    form.locator = {
      ...(row.locator || { by: 'resource_id', value: '' }),
      index: row.locator?.index || 1,
      context: row.locator?.context || APP_LOCATOR_CONTEXT_NATIVE,
      page_index: row.locator?.page_index,
      devtools_source: row.locator?.devtools_source,
    }
    normalizeLocatorContext(form.locator)
  }
  form.remark = row.remark || ''
  if (row.element_type === 'image' && form.locator.value) {
    await hydrateTemplatePreviews([row])
  }
  dlgVisible.value = true
}

async function save() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.element_type === 'image') {
    if (!String(form.locator.value || '').trim()) {
      ElMessage.warning('请上传识别小图')
      return
    }
    form.locator.by = 'image'
  } else if (!form.locator.by || !String(form.locator.value || '').trim()) {
    ElMessage.warning('请填写定位方式与定位值')
    return
  }
  saving.value = true
  try {
    const locator = { ...form.locator }
    normalizeLocatorContext(locator)
    const payload = {
      name: form.name.trim(),
      project_id: proStore.projectInfo.id,
      element_type: form.element_type,
      locator,
      remark: form.remark,
      username: uStore.userInfo?.username,
    }
    if (editingId.value) {
      await appElementApi.update(editingId.value, payload)
      ElMessage.success('已更新')
    } else {
      await appElementApi.create(payload)
      ElMessage.success('已创建')
    }
    dlgVisible.value = false
    loadList()
  } catch (e) {
    const msg = getApiErrorMessage(e, '保存失败')
    if (isDuplicateElementNameError(e)) {
      ElMessage.warning(msg)
    } else {
      ElMessage.error(msg)
    }
  } finally {
    saving.value = false
  }
}

async function removeRow(row) {
  try {
    const refRes = await appElementApi.references(row.id)
    const refs = refRes.data?.data || refRes.data || {}
    if (refs.total > 0) {
      const sample = [...(refs.cases || []), ...(refs.suites || []), ...(refs.fragments || [])].slice(0, 3)
      const names = sample.map((item) => item.name).filter(Boolean).join('、')
      ElMessage.warning(`元素「${row.name}」仍被 ${refs.total} 处引用${names ? `（如 ${names}）` : ''}，请先移除引用再删除`)
      return
    }
    await ElMessageBox.confirm(`确定删除元素「${row.name}」？`, '提示', { type: 'warning' })
    await appElementApi.remove(row.id)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(getApiErrorMessage(e, '删除失败'))
  }
}

loadList()
</script>

<style scoped>
.image-upload-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.template-preview {
  width: 80px;
  height: 80px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
}
.template-path {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  word-break: break-all;
}
.field-hint {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}
.field-hint.inline {
  margin-top: 0;
  margin-left: 8px;
}
.muted-ref {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
