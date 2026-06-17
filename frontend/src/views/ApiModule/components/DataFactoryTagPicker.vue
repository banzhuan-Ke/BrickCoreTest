<template>
  <el-dialog v-model="visible" title="数据工厂标签（已保存）" width="720px" append-to-body destroy-on-close class="df-tag-picker-dialog">
    <el-alert type="info" :closable="false" show-icon class="picker-alert">
      <template #title>执行时按「运行所选环境」解析，与下方筛选无关</template>
      <ul class="alert-list">
        <li><strong>项目通用</strong>标签：任意环境执行均可注入。</li>
        <li><strong>某环境专属</strong>标签：仅在该环境执行时有效；换环境可能无法替换。</li>
        <li>跨环境同一语义（如 token、host）：建议用<strong>环境变量</strong>同名 key，各环境配不同值，插入 <code v-pre>${{token}}</code>。</li>
        <li>内置工具（MD5/随机等）无需保存：请用旁边的 <strong>插入工具</strong> → <code v-pre>${{dt:...}}</code>。</li>
      </ul>
    </el-alert>
    <div class="picker-toolbar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索标签名 / 工具名 / 预览 / 范围"
        clearable
        style="flex: 1; min-width: 200px;"
        prefix-icon="Search"
      />
    </div>
    <el-table :data="filteredTagList" v-loading="loading" size="small" max-height="400">
      <el-table-column prop="tag" label="标签" width="120" />
      <el-table-column prop="scope_label" label="生效范围" width="120" show-overflow-tooltip />
      <el-table-column prop="tool_name" label="来源工具" width="100" />
      <el-table-column prop="output_preview" label="预览" show-overflow-tooltip />
      <el-table-column label="引用" width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <code class="ref-code">{{ row.ref }}</code>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="insertRef(row.ref)">插入</el-button>
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { dataFactoryApi } from '@/api/modules/dataFactory'
import { snapshotInsertTarget } from '@/utils/varInsert.js'

const props = defineProps({
  modelValue: Boolean,
  projectId: { type: Number, required: true }
})
const emit = defineEmits(['update:modelValue', 'insert'])

const visible = ref(false)
const tagList = ref([])
const loading = ref(false)
const searchKeyword = ref('')

const filteredTagList = computed(() => {
  const q = searchKeyword.value.trim().toLowerCase()
  if (!q) return tagList.value
  return tagList.value.filter((row) => {
    const hay = `${row.tag} ${row.tool_name} ${row.output_preview} ${row.ref} ${row.scope_label || ''}`.toLowerCase()
    return hay.includes(q)
  })
})

watch(() => props.modelValue, async (v) => {
  visible.value = v
  if (v) {
    searchKeyword.value = ''
    snapshotInsertTarget()
    await loadTags()
  }
})
watch(visible, (v) => emit('update:modelValue', v))

async function loadTags() {
  loading.value = true
  try {
    const res = await dataFactoryApi.listToolTags({
      project_id: props.projectId,
    })
    tagList.value = res.data || []
  } finally {
    loading.value = false
  }
}

function insertRef(refStr) {
  emit('insert', refStr)
  visible.value = false
}
</script>

<style scoped>
.picker-alert {
  margin-bottom: 12px;

  .alert-list {
    margin: 6px 0 0;
    padding-left: 18px;
    font-size: 12px;
    line-height: 1.6;
  }

  code {
    font-family: monospace;
    background: var(--el-fill-color-light);
    padding: 0 3px;
    border-radius: 3px;
  }
}

.picker-toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.ref-code {
  font-size: 12px;
}
</style>
