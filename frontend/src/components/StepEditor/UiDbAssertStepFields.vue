<template>
  <div class="ui-db-assert-fields">
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
      步骤执行时由 Runner 调用数据工厂内部 API 连库断言，支持 MySQL / PostgreSQL / Redis。变量语法 <code v-pre>${{变量名}}</code>
    </el-alert>
    <el-form label-width="100px" size="default">
      <el-form-item label="断言名称">
        <el-input v-model="params.name" placeholder="数据库断言" />
      </el-form-item>
      <el-form-item label="数据源">
        <el-select
          v-model="params.datasource_id"
          clearable
          filterable
          placeholder="默认数据源"
          style="width: 100%;"
          :loading="dsLoading"
        >
          <el-option
            v-for="ds in datasources"
            :key="ds.id"
            :label="`${ds.name} (${ds.environment_name})`"
            :value="ds.id"
          >
            <span>{{ ds.name }}</span>
            <el-tag size="small" style="margin-left: 8px;">{{ dbTypeLabel(ds.db_type) }}</el-tag>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item :label="sqlLabel">
        <div class="sql-editor-wrap">
          <div class="sql-editor-head">
            <span class="sql-editor-hint">可放大编辑长 SQL</span>
            <el-tooltip content="放大编辑" placement="top">
              <el-button type="primary" link size="small" :icon="FullScreen" @click="sqlExpandVisible = true">
                放大
              </el-button>
            </el-tooltip>
          </div>
          <MonacoEditor v-model="params.sql" language="sql" height="140px" />
          <div class="sql-toolbar">
            <VarInsertButton :env-id="envId" label="变量" />
            <ToolInsertButton :env-id="envId" label="工具" />
          </div>
        </div>
        <p class="field-hint">{{ sqlHint }}</p>
      </el-form-item>
      <el-form-item label="字段/键">
        <el-input v-model="params.field" :placeholder="fieldPlaceholder" />
      </el-form-item>
      <el-form-item label="操作符">
        <el-select v-model="params.operator" style="width: 100%;">
          <el-option v-for="op in operators" :key="op.value" :label="op.label" :value="op.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="期望值">
        <el-input
          v-model="params.expected"
          :disabled="['exists', 'not_exists'].includes(params.operator)"
          placeholder="支持变量"
        />
      </el-form-item>
    </el-form>

    <el-dialog
      v-model="sqlExpandVisible"
      :title="`编辑 ${sqlLabel}`"
      width="860px"
      top="8vh"
      destroy-on-close
      append-to-body
    >
      <MonacoEditor
        v-if="sqlExpandVisible"
        v-model="params.sql"
        language="sql"
        height="56vh"
      />
      <template #footer>
        <el-button type="primary" @click="sqlExpandVisible = false">完成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { FullScreen } from '@element-plus/icons-vue'
import MonacoEditor from '@/components/MonacoEditor'
import VarInsertButton from '@/components/VarInsertButton.vue'
import ToolInsertButton from '@/components/ToolInsertButton.vue'
import { dataFactoryApi } from '@/api/modules/dataFactory'

const props = defineProps({
  params: { type: Object, required: true },
  projectId: { type: Number, default: null },
  envId: { type: Number, default: null },
})

const datasources = ref([])
const dsLoading = ref(false)
const sqlExpandVisible = ref(false)

const operators = [
  { label: '等于', value: 'equals' },
  { label: '不等于', value: 'not_equals' },
  { label: '大于', value: 'gt' },
  { label: '大于等于', value: 'gte' },
  { label: '小于', value: 'lt' },
  { label: '小于等于', value: 'lte' },
  { label: '包含', value: 'contains' },
  { label: '行数等于', value: 'row_count_equals' },
  { label: '存在记录', value: 'exists' },
  { label: '不存在', value: 'not_exists' },
]

const selectedDs = computed(() =>
  datasources.value.find((d) => d.id === props.params.datasource_id)
)

const sqlLabel = computed(() => {
  const t = (selectedDs.value?.db_type || 'mysql').toLowerCase()
  if (t === 'redis') return 'Redis 命令'
  return 'SQL (SELECT)'
})

const sqlHint = computed(() => {
  const t = (selectedDs.value?.db_type || 'mysql').toLowerCase()
  if (t === 'redis') {
    return '只读命令如 GET key、HGET hash field；database 字段填 DB index（0-15）'
  }
  if (t === 'postgresql') {
    return '仅允许 SELECT / SHOW / EXPLAIN 等只读语句'
  }
  return '仅允许 SELECT 查询；未选数据源时使用环境默认 MySQL 数据源'
})

const fieldPlaceholder = computed(() => {
  const t = (selectedDs.value?.db_type || 'mysql').toLowerCase()
  return t === 'redis' ? '留空则取命令返回值' : '结果列名，如 cnt'
})

function dbTypeLabel(t) {
  const map = { mysql: 'MySQL', postgresql: 'PostgreSQL', redis: 'Redis' }
  return map[(t || 'mysql').toLowerCase()] || t
}

async function loadDatasources() {
  if (!props.projectId) return
  dsLoading.value = true
  try {
    const res = await dataFactoryApi.listDatasources({
      project_id: props.projectId,
      environment_id: props.envId || undefined,
      size: 100,
    })
    datasources.value = res.data?.list || []
  } finally {
    dsLoading.value = false
  }
}

watch(() => [props.projectId, props.envId], loadDatasources, { immediate: true })
</script>

<style scoped>
.sql-editor-wrap {
  width: 100%;
  overflow: hidden;
}
.sql-editor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.sql-editor-hint {
  font-size: 12px;
  color: #909399;
}
.sql-toolbar {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #909399;
}
</style>
