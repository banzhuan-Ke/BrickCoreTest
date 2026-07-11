<template>
  <div class="embed-config-panel">
    <div style="margin-bottom: 16px;">
      <el-button type="primary" icon="Plus" @click="openDialog()">新增配置</el-button>
    </div>

    <el-table :data="configList" stripe border v-loading="loading">
      <el-table-column prop="name" label="配置名称" min-width="140" />
      <el-table-column prop="provider" label="供应商" width="110">
        <template #default="{ row }">
          <el-tag size="small">{{ providerLabel(row.provider) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="model" label="Embedding 模型" min-width="160" />
      <el-table-column prop="dimensions" label="维度" width="72" align="center" />
      <el-table-column prop="api_key" label="API Key" min-width="140">
        <template #default="{ row }">
          <span class="key-mask">{{ row.api_key }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="is_default" label="默认" width="72" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="is_enabled" label="启用" width="80">
        <template #default="{ row }">
          <el-switch v-model="row.is_enabled" size="small" @change="val => toggleEnabled(row, val)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button circle size="small" type="success" :loading="row._testing" icon="VideoPlay" @click="testConfig(row)" />
          <el-button v-if="!row.is_default" circle size="small" icon="Star" @click="setDefault(row)" />
          <el-button circle size="small" type="primary" icon="Edit" @click="openDialog(row)" />
          <el-button circle size="small" type="danger" icon="Delete" @click="removeConfig(row)" />
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog.visible" :title="dialog.id ? '编辑 Embedding 配置' : '新增 Embedding 配置'" width="520px" destroy-on-close>
      <el-form :model="dialog.form" label-width="120px">
        <el-form-item label="配置名称" required>
          <el-input v-model="dialog.form.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="供应商" required>
          <el-select v-model="dialog.form.provider" style="width: 100%;">
            <el-option v-for="p in providerOptions" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="Embedding 模型" required>
          <el-input v-model="dialog.form.model" placeholder="如 text-embedding-v4" />
        </el-form-item>
        <el-form-item label="向量维度">
          <el-select v-model="dialog.form.dimensions" style="width: 100%;">
            <el-option v-for="d in dimensionOptions" :key="d" :label="String(d)" :value="d" />
          </el-select>
          <div class="field-hint">通义 text-embedding-v3/v4 默认 1024；切换维度后需重建向量索引</div>
        </el-form-item>
        <el-form-item label="API Key" required>
          <el-input v-model="dialog.form.api_key" type="password" show-password placeholder="留空则不修改（编辑时）" />
        </el-form-item>
        <el-form-item label="API Base">
          <el-input v-model="dialog.form.api_base" placeholder="可选，OpenAI 兼容地址" />
        </el-form-item>
        <el-form-item label="超时(秒)">
          <el-input-number v-model="dialog.form.timeout" :min="5" :max="600" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="dialog.form.is_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.saving" @click="saveDialog">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { embedConfigApi } from '@/api/modules/ai.js'

const loading = ref(false)
const configList = ref([])

const providerOptions = [
  { value: 'qwen', label: '通义千问' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'custom', label: '自定义 OpenAI 兼容' }
]

const dimensionOptions = [64, 128, 256, 512, 768, 1024, 1536, 2048]

const providerMap = Object.fromEntries(providerOptions.map(p => [p.value, p.label]))
function providerLabel(v) {
  return providerMap[v] || v
}

const dialog = reactive({
  visible: false,
  id: null,
  saving: false,
  form: {
    name: 'Embedding 配置',
    provider: 'qwen',
    model: 'text-embedding-v4',
    dimensions: 1024,
    api_key: '',
    api_base: '',
    timeout: 120,
    is_enabled: true
  }
})

async function loadList() {
  loading.value = true
  try {
    const res = await embedConfigApi.getList({ size: 200 })
    if (res.data?.code === 200) {
      configList.value = (res.data.data?.list || []).map(r => ({ ...r, _testing: false }))
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function openDialog(row) {
  dialog.id = row?.id || null
  dialog.form = row
    ? {
        name: row.name,
        provider: row.provider,
        model: row.model,
        dimensions: row.dimensions || 1024,
        api_key: '',
        api_base: row.api_base || '',
        timeout: row.timeout || 120,
        is_enabled: row.is_enabled !== false
      }
    : {
        name: 'Embedding 配置',
        provider: 'qwen',
        model: 'text-embedding-v4',
        dimensions: 1024,
        api_key: '',
        api_base: '',
        timeout: 120,
        is_enabled: true
      }
  dialog.visible = true
}

async function saveDialog() {
  if (!dialog.form.name?.trim()) {
    ElMessage.warning('请填写配置名称')
    return
  }
  if (!dialog.id && !dialog.form.api_key?.trim()) {
    ElMessage.warning('请填写 API Key')
    return
  }
  dialog.saving = true
  try {
    const payload = { ...dialog.form }
    if (dialog.id && !payload.api_key) {
      delete payload.api_key
    }
    if (dialog.id) {
      await embedConfigApi.update(dialog.id, payload)
    } else {
      await embedConfigApi.create(payload)
    }
    ElMessage.success('已保存')
    dialog.visible = false
    await loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.response?.data?.message || '保存失败')
  } finally {
    dialog.saving = false
  }
}

async function toggleEnabled(row, val) {
  try {
    await embedConfigApi.update(row.id, { is_enabled: val })
  } catch (e) {
    row.is_enabled = !val
    ElMessage.error('更新失败')
  }
}

async function setDefault(row) {
  try {
    await embedConfigApi.setDefault(row.id)
    ElMessage.success('已设为默认')
    await loadList()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function testConfig(row) {
  row._testing = true
  try {
    const res = await embedConfigApi.test(row.id)
    if (res.data?.code === 200) {
      ElMessage.success(`连通成功，向量维度 ${res.data.data?.dimension ?? '—'}`)
    } else {
      ElMessage.error(res.data?.message || '测试失败')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '测试失败')
  } finally {
    row._testing = false
  }
}

async function removeConfig(row) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.name}」？`, '确认', { type: 'warning' })
    await embedConfigApi.delete(row.id)
    ElMessage.success('已删除')
    await loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

onMounted(loadList)
</script>

<style scoped>
.key-mask {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.field-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
</style>
