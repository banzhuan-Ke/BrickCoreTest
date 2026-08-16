<template>
  <div class="db-assertions-editor">
    <div class="toolbar">
      <el-button type="primary" size="small" icon="Plus" @click="addRow">添加断言</el-button>
      <span class="tip">{{ tipText }}</span>
      <el-button
        class="help-toggle"
        type="primary"
        link
        size="small"
        @click="helpOpen = !helpOpen"
      >
        <el-icon><QuestionFilled /></el-icon>
        使用帮助
        <el-icon class="help-caret">
          <ArrowUp v-if="helpOpen" />
          <ArrowDown v-else />
        </el-icon>
      </el-button>
    </div>

    <div v-show="helpOpen" class="help-panel">
      <div class="help-section">
        <div class="help-h">怎么用</div>
        <ol class="help-list">
          <li>选择与<strong>当前调试/执行环境</strong>一致的数据源（不一致会直接失败）</li>
          <li>填写只读 SQL（MySQL/PG 一般为 <code>SELECT</code>）；可用 <code v-pre>${{变量名}}</code> 引用环境/用例变量</li>
          <li>字段比较（等于、包含等）只取查询结果的<strong>首行</strong>；字段留空或不存在时回退<strong>首行首列</strong>；多行请用 <code>WHERE</code> 收窄</li>
          <li>配好后点「调试断言」可先核对实际值与近 10 行预览，再保存执行</li>
        </ol>
      </div>

      <div class="help-section">
        <div class="help-h">操作符怎么选</div>
        <ul class="help-list plain">
          <li><b>等于 / 不等于 / 包含 / 大小比较</b>：取首行某字段与期望值比较，需填「字段」</li>
          <li><b>行数等于</b>：比较查询返回行数，字段可空，期望填数字</li>
          <li><b>存在记录 / 不存在</b>：只关心有没有行，期望值无需填写</li>
        </ul>
      </div>

      <div class="help-section">
        <div class="help-h">案例</div>
        <div class="example-grid">
          <div v-for="ex in examples" :key="ex.title" class="example-card">
            <div class="example-title">{{ ex.title }}</div>
            <div class="example-desc">{{ ex.desc }}</div>
            <div class="example-meta">
              <span>字段 <code>{{ ex.field || '—' }}</code></span>
              <span>操作符 <code>{{ ex.operator }}</code></span>
              <span>期望 <code>{{ ex.expected || '—' }}</code></span>
            </div>
            <pre class="example-sql">{{ ex.sql }}</pre>
          </div>
        </div>
      </div>
    </div>

    <el-alert
      v-if="orphanDatasourceIds.length"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 8px;"
      :title="orphanDatasourceTitle"
    />
    <el-alert
      v-else-if="!datasources.length"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 8px;"
      :title="emptyDatasourceTitle"
    />
    <el-table :data="modelValue" size="small" border class="config-table">
      <el-table-column label="名称" width="120">
        <template #default="{ $index }">
          <el-input v-model="modelValue[$index].name" size="small" placeholder="断言名称" />
        </template>
      </el-table-column>
      <el-table-column label="数据源" width="200">
        <template #default="{ $index }">
          <el-select v-model="modelValue[$index].datasource_id" size="small" clearable placeholder="默认数据源" style="width: 100%" filterable>
            <el-option v-for="ds in datasources" :key="ds.id" :label="dsLabel(ds)" :value="ds.id" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column :label="sqlColumnLabel" min-width="260">
        <template #default="{ $index }">
          <div class="sql-cell">
            <MonacoEditor
              v-model="modelValue[$index].sql"
              language="sql"
              height="100px"
            />
            <el-tooltip content="放大编辑" placement="top">
              <el-button
                class="sql-expand-btn"
                type="primary"
                link
                size="small"
                :icon="FullScreen"
                @click="openSqlExpand($index)"
              />
            </el-tooltip>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="字段" width="90">
        <template #default="{ $index }">
          <el-input v-model="modelValue[$index].field" size="small" :placeholder="fieldPlaceholder($index)" />
        </template>
      </el-table-column>
      <el-table-column label="操作符" width="130">
        <template #default="{ $index }">
          <el-select v-model="modelValue[$index].operator" size="small" style="width: 100%">
            <el-option v-for="op in operators" :key="op.value" :label="op.label" :value="op.value" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="期望值" width="100">
        <template #default="{ $index }">
          <el-input v-model="modelValue[$index].expected" size="small" :disabled="['exists', 'not_exists'].includes(modelValue[$index].operator)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="removeRow($index)" icon="Delete" />
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="sqlExpandVisible"
      :title="sqlExpandTitle"
      width="860px"
      top="8vh"
      destroy-on-close
      append-to-body
      class="db-assert-sql-expand-dialog"
    >
      <MonacoEditor
        v-if="sqlExpandVisible && sqlExpandIndex != null && modelValue[sqlExpandIndex]"
        v-model="modelValue[sqlExpandIndex].sql"
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
import { computed, ref } from 'vue'
import { QuestionFilled, ArrowDown, ArrowUp, FullScreen } from '@element-plus/icons-vue'
import MonacoEditor from '@/components/MonacoEditor'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  datasources: { type: Array, default: () => [] },
  environmentId: { type: [Number, String], default: null },
})

const emit = defineEmits(['update:modelValue'])

const helpOpen = ref(false)
const sqlExpandVisible = ref(false)
const sqlExpandIndex = ref(null)

const examples = [
  {
    title: '校验字段值',
    desc: '接口创建用户后，用返回的 id 查库，断言用户名正确',
    field: 'username',
    operator: '等于',
    expected: 'banzhuanke',
    sql: 'SELECT username FROM user WHERE id = ${{user_id}} LIMIT 1',
  },
  {
    title: '校验记录存在',
    desc: '确认业务数据已落库（不关心具体字段值）',
    field: '',
    operator: '存在记录',
    expected: '',
    sql: "SELECT id FROM order WHERE order_no = '${{order_no}}' LIMIT 1",
  },
  {
    title: '校验已删除',
    desc: '删除后库中应查不到该记录',
    field: '',
    operator: '不存在',
    expected: '',
    sql: 'SELECT id FROM user WHERE id = ${{deleted_id}}',
  },
  {
    title: '校验行数',
    desc: '例如某状态下应恰好有 1 条记录',
    field: '',
    operator: '行数等于',
    expected: '1',
    sql: "SELECT id FROM task WHERE status = 'pending' AND owner = '${{username}}'",
  },
]

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

const hasRedis = computed(() => (props.datasources || []).some((d) => (d.db_type || '').toLowerCase() === 'redis'))
const hasPg = computed(() => (props.datasources || []).some((d) => (d.db_type || '').toLowerCase() === 'postgresql'))

const availableIds = computed(() => new Set(
  (props.datasources || []).map((d) => Number(d.id)).filter((n) => Number.isFinite(n))
))

const orphanDatasourceIds = computed(() => {
  const ids = new Set()
  for (const row of props.modelValue || []) {
    const id = row?.datasource_id
    if (id == null || id === '') continue
    const num = Number(id)
    if (!Number.isFinite(num) || !availableIds.value.has(num)) {
      ids.add(id)
    }
  }
  return [...ids]
})

const emptyDatasourceTitle = computed(() => {
  if (props.environmentId) {
    return '当前调试环境下暂无可用数据源。请切换环境，或到「数据工厂 → 数据源」为该环境配置。'
  }
  return '暂无可用数据源。请先在「数据工厂 → 数据源」为当前项目配置，并确保有数据工厂查看权限。'
})

const orphanDatasourceTitle = computed(() => {
  const ids = orphanDatasourceIds.value.join('、')
  return `断言中的数据源（id: ${ids}）不属于当前调试环境，调试会失败。请改选下方列表中的数据源，或切换顶部调试环境。`
})

const tipText = computed(() => {
  const parts = [
    '变量语法 ${{变量名}}',
    '字段比较取首行（字段缺失回退首列）',
    '数据源须与顶部调试环境一致',
  ]
  if (hasRedis.value) parts.push('Redis 用 GET/HGET 等只读命令')
  if (hasPg.value) parts.push('PostgreSQL 支持 SELECT')
  else parts.push('MySQL/PostgreSQL 仅 SELECT')
  return parts.join('；')
})

const sqlColumnLabel = computed(() => (hasRedis.value ? 'SQL / Redis 命令' : 'SQL (SELECT)'))

const sqlExpandTitle = computed(() => {
  const name = props.modelValue?.[sqlExpandIndex.value]?.name
  const base = sqlColumnLabel.value
  return name ? `编辑 ${base} · ${name}` : `编辑 ${base}`
})

function openSqlExpand(index) {
  sqlExpandIndex.value = index
  sqlExpandVisible.value = true
}

function dsById(id) {
  return (props.datasources || []).find((d) => d.id === id)
}

function dsLabel(ds) {
  const t = (ds.db_type || 'mysql').toLowerCase()
  const tag = { mysql: 'MySQL', postgresql: 'PG', redis: 'Redis' }[t] || t
  const env = ds.environment_name ? ` · ${ds.environment_name}` : ''
  return `${ds.name} [${tag}]${env}`
}

function fieldPlaceholder(index) {
  const ds = dsById(props.modelValue?.[index]?.datasource_id)
  return (ds?.db_type || '').toLowerCase() === 'redis' ? '可选' : '结果列名，如 username'
}

function addRow() {
  const next = [...(props.modelValue || []), {
    name: '',
    datasource_id: null,
    sql: '',
    field: '',
    operator: 'equals',
    expected: '',
  }]
  emit('update:modelValue', next)
}

function removeRow(index) {
  if (sqlExpandVisible.value && sqlExpandIndex.value != null) {
    if (index === sqlExpandIndex.value) {
      sqlExpandVisible.value = false
      sqlExpandIndex.value = null
    } else if (index < sqlExpandIndex.value) {
      sqlExpandIndex.value -= 1
    }
  }
  const next = [...(props.modelValue || [])]
  next.splice(index, 1)
  emit('update:modelValue', next)
}
</script>

<style scoped lang="scss">
.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-bottom: 8px;
}

.tip {
  flex: 1;
  min-width: 160px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}

.help-toggle {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.help-caret {
  margin-left: 2px;
}

.help-panel {
  margin-bottom: 10px;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}

.help-section + .help-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.help-h {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 6px;
}

.help-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--el-text-color-regular);

  &.plain {
    padding-left: 16px;
    list-style: disc;
  }

  li + li {
    margin-top: 2px;
  }

  code {
    padding: 0 4px;
    border-radius: 3px;
    background: var(--el-fill-color);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11px;
  }
}

.example-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.example-card {
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-light);
  min-width: 0;
}

.example-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.example-desc {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.45;
}

.example-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--el-text-color-secondary);

  code {
    color: var(--el-color-primary);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
}

.example-sql {
  margin: 8px 0 0;
  padding: 8px 10px;
  border-radius: 4px;
  border: 1px solid var(--el-border-color-extra-light);
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-all;
}

.config-table {
  width: 100%;
}

.sql-cell {
  position: relative;
}

.sql-expand-btn {
  position: absolute;
  top: 2px;
  right: 4px;
  z-index: 2;
  padding: 2px;
  background: var(--el-bg-color);
  border-radius: 4px;
  opacity: 0.85;
}

.sql-cell:hover .sql-expand-btn {
  opacity: 1;
}

@media (max-width: 900px) {
  .example-grid {
    grid-template-columns: 1fr;
  }

  .help-toggle {
    margin-left: 0;
  }
}
</style>
