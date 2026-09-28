<template>
  <div class="df-console">
    <div class="search-bar console-toolbar">
      <el-select
        v-model="datasourceId"
        placeholder="选择数据源"
        style="width: 320px"
        filterable
      >
        <el-option
          v-for="ds in filteredDatasources"
          :key="ds.id"
          :label="dsOptionLabel(ds)"
          :value="ds.id"
        />
      </el-select>
      <el-tag v-if="selectedDs" size="small" type="info">
        环境：{{ selectedDs.environment_name || selectedDs.environment_id }}
      </el-tag>
      <el-tag v-if="selectedDs && catalogDefaultTarget" size="small">
        {{ targetLabel }}：{{ catalogDefaultTarget }}
      </el-tag>
      <el-tag v-if="selectedDs" size="small" :type="selectedDs.allow_write ? 'warning' : 'success'">
        {{ selectedDs.allow_write ? '可写' : '只读' }} · {{ dbTypeLabel(selectedDs.db_type) }}
      </el-tag>
      <el-select
        v-model="envFilterId"
        clearable
        placeholder="按环境筛选"
        style="width: 160px"
        filterable
      >
        <el-option v-for="e in envList" :key="e.id" :label="e.name" :value="e.id" />
      </el-select>
      <el-select
        v-model="historyPick"
        clearable
        filterable
        placeholder="语句历史"
        style="width: 200px"
        :disabled="!historyItems.length"
        @change="applyHistory"
      >
        <el-option
          v-for="(h, idx) in historyItems"
          :key="idx"
          :label="h.label"
          :value="idx"
        />
      </el-select>
      <el-button type="primary" :loading="running" :disabled="!canRun || running" @click="runConsole(false)">
        执行
      </el-button>
      <el-button :disabled="!statement.trim()" @click="clearAll">清空</el-button>
      <el-button type="success" plain :disabled="!canSave" @click="saveAsTemplate">另存为模板</el-button>
      <el-button plain :disabled="!rows.length" @click="exportCsv">导出 CSV</el-button>
      <ViaWorkerSelect
        v-model="consoleWorkerId"
        :env-id="envId"
        size="small"
        checkbox-label="经执行机执行"
        :require-df-proxy="true"
        min-engine="1.8.2"
        hint-text="平台访问不到数据源时勾选，由本机空闲压测执行机代发。需引擎 ≥ 1.8.2。"
      />
    </div>

    <div class="console-body">
      <aside class="object-browser">
        <div class="ob-header">
          <span>{{ browserTitle }}</span>
          <el-button
            link
            type="primary"
            size="small"
            :loading="catalogLoading"
            :disabled="!canBrowse"
            @click="refreshCatalog"
          >刷新</el-button>
        </div>
        <el-input
          v-model="objectFilter"
          size="small"
          clearable
          :placeholder="objectFilterPlaceholder"
          :disabled="!canBrowse"
          class="ob-filter"
          @keyup.enter="(isRedis || isEs) ? refreshCatalog() : null"
        />
        <div v-loading="catalogLoading" class="ob-tree-wrap" @scroll="onObjectListScroll">
          <template v-if="visibleObjectNodes.length">
            <div
              v-for="obj in visibleObjectNodes"
              :key="obj.id"
              class="ob-obj"
              :class="{ active: expandedObject === obj.name }"
            >
              <div
                class="ob-obj-row"
                :title="nodeTitle(obj)"
              >
                <span
                  v-if="!isRedis"
                  class="ob-caret"
                  @click.stop="toggleObject(obj)"
                >{{ expandedObject === obj.name ? '▾' : '▸' }}</span>
                <span v-else class="ob-caret">·</span>
                <span class="ob-label" @dblclick.stop="onNodeDblClick(obj)">{{ obj.label }}</span>
                <span v-if="obj.metaHint" class="ob-meta">{{ obj.metaHint }}</span>
              </div>
              <div v-if="!isRedis && expandedObject === obj.name" class="ob-cols">
                <div v-if="isSql" class="ob-struct-actions">
                  <el-button link type="primary" size="small" @click.stop="loadIndexes(obj.name)">索引</el-button>
                  <el-button link type="primary" size="small" @click.stop="loadDdl(obj.name)">建表语句</el-button>
                  <el-button link type="primary" size="small" @click.stop="loadExplain(obj.name)">EXPLAIN</el-button>
                </div>
                <div v-if="isEs" class="ob-struct-actions">
                  <el-button link type="primary" size="small" @click.stop="loadEsSample(obj.name)">样例文档</el-button>
                </div>
                <div v-if="columnsLoading === obj.name" class="ob-cols-loading">加载中…</div>
                <template v-else-if="cachedColumns(obj.name).length">
                  <div
                    v-for="col in cachedColumns(obj.name)"
                    :key="col.name"
                    class="ob-col-row"
                    :title="`${col.name}${col.type ? ` (${col.type})` : ''}`"
                    @click.stop="onColumnClick(col)"
                  >
                    <span class="ob-label">{{ col.name }}</span>
                    <span v-if="col.type" class="ob-meta">{{ col.type }}</span>
                  </div>
                </template>
                <div v-else class="ob-cols-empty">无列/字段</div>
              </div>
            </div>
            <p v-if="objectListMore" class="ob-more">已显示 {{ visibleObjectNodes.length }} / {{ filteredObjectNodes.length }}，继续下滑</p>
          </template>
          <el-empty
            v-else-if="!catalogLoading"
            :description="catalogEmptyText"
            :image-size="48"
          />
        </div>
        <p v-if="catalogHint" class="ob-hint">{{ catalogHint }}</p>
        <p v-if="catalogError" class="ob-error">{{ catalogError }}</p>
        <p class="ob-tip">{{ browserTip }}</p>
      </aside>

      <div class="console-main">
        <div class="editor-wrap">
          <MonacoEditor
            v-if="!isRedis"
            :key="editorLanguage + '-' + (datasourceId || 0)"
            v-model="statement"
            :language="editorLanguage"
            height="220px"
          />
          <el-input
            v-else
            v-model="statement"
            type="textarea"
            :rows="8"
            placeholder="输入 Redis 命令，例如：GET mykey 或 HGETALL hash"
            class="redis-input"
          />
          <p v-if="isEs" class="console-hint">
            ES：纯 JSON 使用默认索引 _search；或首行 <code>GET index/_search</code> 后跟 JSON body。写 API 需开启「允许写操作」并确认。
          </p>
        </div>

        <div v-if="metaLine || rows.length" class="result-meta">
          <span v-if="metaLine">{{ metaLine }}</span>
          <span v-if="rows.length" class="result-actions">
            <el-button link type="primary" size="small" @click="copyResultTsv">复制表格</el-button>
          </span>
        </div>
        <el-alert
          v-if="errorText"
          type="error"
          :closable="false"
          show-icon
          :title="errorText"
          style="margin-top: 8px"
        />
        <el-table
          v-if="columns.length"
          :data="rows"
          stripe
          border
          size="small"
          max-height="360"
          class="result-table"
          empty-text="无数据行"
        >
          <el-table-column
            v-for="col in columns"
            :key="col"
            :prop="col"
            :label="col"
            min-width="120"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <span class="cell-copy" :title="'单击复制'" @click="copyCell(row[col])">{{ formatCell(row[col]) }}</span>
            </template>
          </el-table-column>
        </el-table>
        <el-empty
          v-else-if="ranOnce && !errorText"
          description="执行成功，无结果行（可能是写操作）"
          :image-size="64"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MonacoEditor from '@/components/MonacoEditor'
import ViaWorkerSelect from '@/components/ViaWorkerSelect.vue'
import { dataFactoryApi } from '@/api/modules/dataFactory'

const props = defineProps({
  projectId: { type: Number, required: true },
  envList: { type: Array, default: () => [] },
  datasourceList: { type: Array, default: () => [] },
  initialDatasourceId: { type: Number, default: null },
})

const emit = defineEmits(['saved-template'])

const envFilterId = ref(null)
const datasourceId = ref(null)
const consoleWorkerId = ref(null)
const statement = ref('SELECT 1')
const running = ref(false)
const ranOnce = ref(false)
const rows = ref([])
const columns = ref([])
const errorText = ref('')
const meta = ref(null)

const catalogLoading = ref(false)
const catalogObjects = ref([])
const catalogHint = ref('')
const catalogError = ref('')
const catalogDefaultTarget = ref('')
const catalogLoadedOnce = ref(false)
const objectFilter = ref('')
const columnsCache = ref({})
const expandedObject = ref(null)
const columnsLoading = ref(null)
/** 切换数据源/执行机时递增，丢弃过期 catalog / columns 响应 */
const catalogGen = ref(0)
const execGen = ref(0)
const historyPick = ref(null)
const historyItems = ref([])
const HISTORY_MAX = 20

/** 控制台只列已启用数据源 */
const enabledDatasources = computed(() =>
  (props.datasourceList || []).filter((d) => d.is_enabled !== false)
)

const filteredDatasources = computed(() => {
  const list = enabledDatasources.value
  if (!envFilterId.value) return list
  return list.filter((d) => d.environment_id === envFilterId.value)
})

const selectedDs = computed(() =>
  enabledDatasources.value.find((d) => d.id === datasourceId.value) || null
)

const envId = computed(() => selectedDs.value?.environment_id || null)

const isRedis = computed(() => (selectedDs.value?.db_type || '').toLowerCase() === 'redis')
const isEs = computed(() => (selectedDs.value?.db_type || '').toLowerCase() === 'elasticsearch')
const isPg = computed(() => (selectedDs.value?.db_type || '').toLowerCase() === 'postgresql')
const isSql = computed(() => !isRedis.value && !isEs.value)
const editorLanguage = computed(() => (isEs.value ? 'json' : 'sql'))
const canBrowse = computed(() => !!selectedDs.value && !!envId.value)

const targetLabel = computed(() => {
  if (isRedis.value) return 'DB'
  if (isEs.value) return '默认索引'
  return '库'
})

const objectFilterPlaceholder = computed(() => {
  if (isRedis.value) return 'SCAN 前缀后点刷新'
  if (isEs.value) return '输入索引名后回车或刷新'
  return '筛选表/索引'
})

const browserTip = computed(() => {
  const viaHint = '目录不自动加载，选好数据源（需经执行机时先勾选）后点「刷新」。'
  if (isRedis.value) return `${viaHint} 填前缀后刷新做 SCAN；双击 key 按类型插入只读命令。`
  if (isEs.value) return `${viaHint} 列表一次只画一部分，滑到底再加载。集群超过 500 个索引时，筛选框输入名字后回车或点刷新，会按名字向 ES 查询。展开字段；双击索引插入查询；「样例文档」取 1 条预览。`
  return `${viaHint} 展开列；可用「索引 / 建表语句 / EXPLAIN」；双击表名插入 SELECT。`
})

const catalogEmptyText = computed(() => {
  if (!selectedDs.value) return '请先选择数据源'
  if (!catalogLoadedOnce.value && !catalogError.value) {
    return consoleWorkerId.value
      ? '已勾选经执行机，点「刷新」加载目录'
      : '点「刷新」加载目录（内网库请先勾选经执行机）'
  }
  if (isRedis.value) return '无 key 或前缀无匹配'
  if (catalogError.value) return '加载失败'
  if (isEs.value && (objectFilter.value || '').trim()) return '没有匹配的索引，换个名字后再刷新'
  return '暂无对象'
})

const defaultStatement = computed(() => {
  if (isRedis.value) return 'GET '
  if (isEs.value) return '{\n  "query": {\n    "match_all": {}\n  },\n  "size": 20\n}'
  return 'SELECT 1'
})

const canRun = computed(() => !!envId.value && !!datasourceId.value && !!statement.value.trim())
const canSave = computed(() => canRun.value)

const metaLine = computed(() => {
  if (!meta.value) return ''
  const parts = []
  if (meta.value.row_count != null) parts.push(`行数 ${meta.value.row_count}`)
  if (meta.value.affected_rows) parts.push(`影响行 ${meta.value.affected_rows}`)
  if (meta.value.elapsed_ms != null) parts.push(`耗时 ${meta.value.elapsed_ms} ms`)
  if (meta.value.truncated) parts.push('已截断')
  if (meta.value.max_rows_applied) parts.push(`上限 ${meta.value.max_rows_applied}`)
  if (meta.value.via_worker) parts.push('经执行机')
  return parts.join(' · ')
})

const objectNodes = computed(() =>
  (catalogObjects.value || []).map((obj) => {
    const kind = obj.kind || 'table'
    const meta = obj.meta || {}
    let metaHint = ''
    if (isRedis.value) {
      metaHint = kind && kind !== 'key' ? kind : ''
    } else if (kind === 'index') {
      const bits = []
      if (meta.docs != null) bits.push(`docs ${meta.docs}`)
      if (meta.store) bits.push(String(meta.store))
      metaHint = bits.join(' · ')
    } else if (meta.rows != null) {
      metaHint = `≈${meta.rows}`
    }
    return {
      id: `obj:${obj.name}`,
      label: obj.name,
      name: obj.name,
      kind,
      nodeType: 'object',
      metaHint,
      isLeaf: isRedis.value,
    }
  })
)

const filteredObjectNodes = computed(() => {
  if (isRedis.value) return objectNodes.value
  const kw = (objectFilter.value || '').trim().toLowerCase()
  if (!kw) return objectNodes.value
  // ES 带 * 的是服务端通配，不能再按字面量在本地滤掉
  if (isEs.value && kw.includes('*')) return objectNodes.value
  return objectNodes.value.filter((n) => String(n.label || '').toLowerCase().includes(kw))
})

const browserTitle = computed(() => {
  const n = catalogLoadedOnce.value && !catalogError.value ? filteredObjectNodes.value.length : null
  const suffix = n == null ? '' : ` ${n}`
  if (isRedis.value) return `Keys${suffix}`
  if (isEs.value) return `索引${suffix}`
  return `表 / 视图${suffix}`
})

const OBJECT_PAGE_SIZE = 40
const visibleObjectCount = ref(OBJECT_PAGE_SIZE)
const visibleObjectNodes = computed(() => filteredObjectNodes.value.slice(0, visibleObjectCount.value))
const objectListMore = computed(() => filteredObjectNodes.value.length > visibleObjectCount.value)

watch([objectFilter, catalogObjects], () => {
  visibleObjectCount.value = OBJECT_PAGE_SIZE
})

function onObjectListScroll(event) {
  if (!objectListMore.value) return
  const el = event.currentTarget
  if (!el || el.scrollTop + el.clientHeight < el.scrollHeight - 24) return
  visibleObjectCount.value += OBJECT_PAGE_SIZE
}

function historyStorageKey() {
  return `df-console-history:${props.projectId}:${datasourceId.value || 0}`
}

function loadHistory() {
  historyPick.value = null
  try {
    const raw = localStorage.getItem(historyStorageKey())
    const list = raw ? JSON.parse(raw) : []
    historyItems.value = Array.isArray(list) ? list.slice(0, HISTORY_MAX) : []
  } catch {
    historyItems.value = []
  }
}

function pushHistory(sql) {
  const text = (sql || '').trim()
  if (!text || !datasourceId.value) return
  const label = text.length > 48 ? `${text.slice(0, 48)}…` : text
  const next = [{ label, sql: text, ts: Date.now() }, ...historyItems.value.filter((h) => h.sql !== text)]
  historyItems.value = next.slice(0, HISTORY_MAX)
  try {
    localStorage.setItem(historyStorageKey(), JSON.stringify(historyItems.value))
  } catch {
    /* quota */
  }
}

function applyHistory(idx) {
  if (idx == null || idx === '') return
  const item = historyItems.value[idx]
  if (item?.sql) statement.value = item.sql
  historyPick.value = null
}

function dbTypeLabel(t) {
  return {
    mysql: 'MySQL',
    postgresql: 'PostgreSQL',
    redis: 'Redis',
    elasticsearch: 'Elasticsearch',
  }[(t || 'mysql').toLowerCase()] || t
}

function dsOptionLabel(ds) {
  const env = ds.environment_name || `环境${ds.environment_id}`
  return `${ds.name} · ${dbTypeLabel(ds.db_type)} · ${env}`
}

function formatCell(v) {
  if (v == null) return ''
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function nodeTitle(data) {
  const bits = [data.label || data.name]
  if (data.kind) bits.push(data.kind)
  if (data.metaHint) bits.push(data.metaHint)
  return bits.join(' · ')
}

function quoteIdent(name) {
  if (isPg.value) return `"${name}"`
  return `\`${name}\``
}

function sampleForObject(name, kind, opts = {}) {
  if (isEs.value) {
    const size = opts.size != null ? opts.size : 20
    return `GET ${name}/_search\n${JSON.stringify({ query: { match_all: {} }, size }, null, 2)}`
  }
  if (isRedis.value) {
    const t = (kind || 'string').toLowerCase()
    if (t === 'hash') return `HGETALL ${name}`
    if (t === 'list') return `LRANGE ${name} 0 19`
    if (t === 'set') return `SMEMBERS ${name}`
    if (t === 'zset') return `ZRANGE ${name} 0 19`
    return `GET ${name}`
  }
  return `SELECT * FROM ${quoteIdent(name)} LIMIT 20`
}

function looksLikeWrite(text, dbType) {
  const s = (text || '').trim()
  if (!s) return false
  const type = (dbType || '').toLowerCase()
  if (type === 'redis') {
    const op = s.split(/\s+/)[0]?.toUpperCase()
    return ['SET', 'DEL', 'HSET', 'HDEL', 'LPUSH', 'RPUSH', 'SADD', 'ZADD'].includes(op)
  }
  if (type === 'elasticsearch') {
    if (s.startsWith('{')) return false
    const upper = s.toUpperCase()
    if (upper === 'PING' || upper === 'HEALTH') return false
    const first = s.split('\n')[0].trim()
    const m = /^(GET|POST|PUT|DELETE|HEAD)\s+(\S+)/i.exec(first)
    if (!m) return false
    const method = m[1].toUpperCase()
    const path = ('/' + m[2].replace(/^\//, '')).toLowerCase()
    if (method === 'GET' || method === 'HEAD') return false
    if (method === 'DELETE' || method === 'PUT') return true
    if (method === 'POST') {
      const readMarkers = [
        '/_search', '/_msearch', '/_count', '/_explain', '/_validate', '/_field_caps',
        '/_mapping', '/_settings', '/_aliases', '/_stats', '/_cat/', '/_cluster/',
        '/_nodes/', '/_resolve/', '/_sql',
      ]
      return !readMarkers.some((x) => path.includes(x))
    }
    return true
  }
  return /\b(INSERT|UPDATE|DELETE|REPLACE)\b/i.test(s)
}

function insertText(text) {
  const cur = statement.value || ''
  if (!cur.trim() || cur.trim() === 'SELECT 1' || cur.trim() === 'GET ') {
    statement.value = text
    return
  }
  const needsSpace = cur.length && !/\s$/.test(cur)
  statement.value = cur + (needsSpace ? ' ' : '') + text
}

function onColumnClick(col) {
  if (!col?.name) return
  insertText(isEs.value ? col.name : quoteIdent(col.name))
}

function onNodeDblClick(data) {
  if (data?.name) {
    statement.value = sampleForObject(data.name, data.kind)
    ElMessage.success(`已插入样例查询：${data.name}`)
  }
}

async function toggleObject(obj) {
  if (!obj?.name) return
  if (expandedObject.value === obj.name) {
    expandedObject.value = null
    return
  }
  expandedObject.value = obj.name
  const cacheKey = columnCacheKey(obj.name)
  if (!Array.isArray(columnsCache.value[cacheKey])) {
    await loadColumns(obj.name)
  }
}

function columnCacheKey(objectName) {
  return `${datasourceId.value || 0}::${objectName}`
}

function cachedColumns(objectName) {
  return columnsCache.value[columnCacheKey(objectName)] || []
}

async function loadColumns(objectName) {
  if (!canBrowse.value) return []
  const gen = catalogGen.value
  const dsId = datasourceId.value
  const cacheKey = `${dsId || 0}::${objectName}`
  if (Array.isArray(columnsCache.value[cacheKey])) {
    return columnsCache.value[cacheKey]
  }
  columnsLoading.value = objectName
  try {
    const res = await dataFactoryApi.fetchConsoleCatalog({
      project_id: props.projectId,
      environment_id: envId.value,
      datasource_id: dsId,
      scope: 'columns',
      object_name: objectName,
      ...(consoleWorkerId.value ? { worker_id: Number(consoleWorkerId.value) } : {}),
    })
    if (gen !== catalogGen.value || dsId !== datasourceId.value) return []
    const data = res.data || {}
    if (!data.success) {
      ElMessage.warning(data.error || '读取列/字段失败')
      // 失败不写空缓存，避免刷新前永久「无列」
      return []
    }
    const cols = data.columns || []
    columnsCache.value = { ...columnsCache.value, [cacheKey]: cols }
    return cols
  } catch (e) {
    if (gen !== catalogGen.value || dsId !== datasourceId.value) return []
    const detail = e?.response?.data?.detail
    ElMessage.warning(typeof detail === 'string' ? detail : e?.message || '读取列/字段失败')
    return []
  } finally {
    if (gen === catalogGen.value && columnsLoading.value === objectName) {
      columnsLoading.value = null
    }
  }
}

function clearExecutionResult() {
  rows.value = []
  columns.value = []
  errorText.value = ''
  meta.value = null
  ranOnce.value = false
}

async function refreshCatalog() {
  const gen = ++catalogGen.value
  catalogObjects.value = []
  columnsCache.value = {}
  expandedObject.value = null
  columnsLoading.value = null
  catalogHint.value = ''
  catalogError.value = ''
  catalogLoadedOnce.value = false
  // 保留 default_target 直到新响应覆盖
  if (!selectedDs.value || !envId.value) return
  catalogLoading.value = true
  const dsId = datasourceId.value
  const workerId = consoleWorkerId.value
  try {
    const payload = {
      project_id: props.projectId,
      environment_id: envId.value,
      datasource_id: dsId,
      scope: 'objects',
      ...(workerId ? { worker_id: Number(workerId) } : {}),
    }
    if (isRedis.value || isEs.value) {
      const prefix = (objectFilter.value || '').trim()
      if (prefix) payload.object_name = prefix
    }
    const res = await dataFactoryApi.fetchConsoleCatalog(payload)
    if (gen !== catalogGen.value) return
    const data = res.data || {}
    catalogHint.value = data.hint || ''
    catalogDefaultTarget.value = data.default_target || selectedDs.value?.database_name || ''
    catalogLoadedOnce.value = true
    if (!data.success) {
      catalogError.value = data.error || '读取目录失败'
      catalogObjects.value = []
      return
    }
    catalogObjects.value = data.objects || []
  } catch (e) {
    if (gen !== catalogGen.value) return
    catalogLoadedOnce.value = true
    const detail = e?.response?.data?.detail
    catalogError.value = typeof detail === 'string' ? detail : e?.message || '读取目录失败'
    catalogObjects.value = []
  } finally {
    if (gen === catalogGen.value) catalogLoading.value = false
  }
}

function resetCatalogPanel() {
  catalogGen.value += 1
  catalogLoading.value = false
  catalogObjects.value = []
  columnsCache.value = {}
  expandedObject.value = null
  columnsLoading.value = null
  catalogHint.value = ''
  catalogError.value = ''
  catalogLoadedOnce.value = false
  catalogDefaultTarget.value = selectedDs.value?.database_name || ''
}

async function loadIndexes(tableName) {
  if (!canBrowse.value || !isSql.value) return
  const gen = catalogGen.value
  const dsId = datasourceId.value
  try {
    const res = await dataFactoryApi.fetchConsoleCatalog({
      project_id: props.projectId,
      environment_id: envId.value,
      datasource_id: dsId,
      scope: 'indexes',
      object_name: tableName,
      ...(consoleWorkerId.value ? { worker_id: Number(consoleWorkerId.value) } : {}),
    })
    if (gen !== catalogGen.value || dsId !== datasourceId.value) return
    const data = res.data || {}
    if (!data.success) {
      ElMessage.warning(data.error || '读取索引失败')
      return
    }
    const indexes = data.indexes || []
    if (!indexes.length) {
      ElMessage.info('该表无索引')
      return
    }
    const lines = indexes.map((ix) => {
      if (ix.definition) return `-- ${ix.name}\n${ix.definition}`
      const uniq = ix.unique ? 'UNIQUE ' : ''
      return `-- ${uniq}INDEX ${ix.name} (${ix.columns || ''}) ${ix.type || ''}`.trim()
    })
    statement.value = lines.join('\n\n')
    ElMessage.success(`已填入 ${indexes.length} 条索引信息`)
  } catch (e) {
    if (gen !== catalogGen.value || dsId !== datasourceId.value) return
    const detail = e?.response?.data?.detail
    ElMessage.warning(typeof detail === 'string' ? detail : e?.message || '读取索引失败')
  }
}

async function loadDdl(tableName) {
  if (!canBrowse.value || !isSql.value) return
  const gen = catalogGen.value
  const dsId = datasourceId.value
  try {
    const res = await dataFactoryApi.fetchConsoleCatalog({
      project_id: props.projectId,
      environment_id: envId.value,
      datasource_id: dsId,
      scope: 'ddl',
      object_name: tableName,
      ...(consoleWorkerId.value ? { worker_id: Number(consoleWorkerId.value) } : {}),
    })
    if (gen !== catalogGen.value || dsId !== datasourceId.value) return
    const data = res.data || {}
    if (!data.success || !data.ddl) {
      ElMessage.warning(data.error || '读取建表语句失败')
      return
    }
    statement.value = data.ddl
    ElMessage.success('已填入建表语句（只读展示，不会自动执行）')
  } catch (e) {
    if (gen !== catalogGen.value || dsId !== datasourceId.value) return
    const detail = e?.response?.data?.detail
    ElMessage.warning(typeof detail === 'string' ? detail : e?.message || '读取建表语句失败')
  }
}

function loadExplain(tableName) {
  if (!tableName || !isSql.value) return
  statement.value = `EXPLAIN ${sampleForObject(tableName)}`
  ElMessage.success('已填入 EXPLAIN（只读；点执行查看计划）')
}

async function loadEsSample(indexName) {
  if (!canBrowse.value || !isEs.value || !indexName) return
  const gen = catalogGen.value
  const dsId = datasourceId.value
  try {
    const res = await dataFactoryApi.fetchConsoleCatalog({
      project_id: props.projectId,
      environment_id: envId.value,
      datasource_id: dsId,
      scope: 'sample',
      object_name: indexName,
      ...(consoleWorkerId.value ? { worker_id: Number(consoleWorkerId.value) } : {}),
    })
    if (gen !== catalogGen.value || dsId !== datasourceId.value) return
    const data = res.data || {}
    if (!data.success) {
      ElMessage.warning(data.error || '读取样例失败')
      return
    }
    statement.value = sampleForObject(indexName, 'index', { size: 1 })
    const sample = data.sample
    if (sample && typeof sample === 'object') {
      rows.value = [sample]
      columns.value = Object.keys(sample)
      ranOnce.value = true
      errorText.value = ''
      meta.value = { row_count: 1, via_worker: !!data.via_worker }
      ElMessage.success('已取 1 条样例并填入 size:1 查询')
    } else {
      clearExecutionResult()
      ElMessage.info('索引暂无文档；已填入 size:1 查询，可点执行')
    }
  } catch (e) {
    if (gen !== catalogGen.value || dsId !== datasourceId.value) return
    const detail = e?.response?.data?.detail
    ElMessage.warning(typeof detail === 'string' ? detail : e?.message || '读取样例失败')
  }
}

async function copyCell(v) {
  const text = formatCell(v)
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制单元格')
  } catch {
    ElMessage.warning('复制失败')
  }
}

async function copyResultTsv() {
  if (!rows.value.length) return
  const cols = columns.value
  const lines = [cols.join('\t')]
  for (const row of rows.value) {
    lines.push(cols.map((c) => formatCell(row[c]).replace(/\t/g, ' ').replace(/\n/g, ' ')).join('\t'))
  }
  try {
    await navigator.clipboard.writeText(lines.join('\n'))
    ElMessage.success('已复制表格')
  } catch {
    ElMessage.warning('复制失败')
  }
}

function exportCsv() {
  if (!rows.value.length) return
  const cols = columns.value
  const esc = (v) => {
    const s = formatCell(v)
    if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
    return s
  }
  const lines = [cols.map(esc).join(',')]
  for (const row of rows.value) {
    lines.push(cols.map((c) => esc(row[c])).join(','))
  }
  const blob = new Blob([`\ufeff${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `df-console-${datasourceId.value || 0}-${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 CSV')
}

watch(
  () => filteredDatasources.value,
  (list) => {
    if (!list.length) {
      datasourceId.value = null
      return
    }
    const still = list.some((d) => d.id === datasourceId.value)
    if (!still) datasourceId.value = list[0].id
  },
  { immediate: true }
)

watch(
  () => [props.initialDatasourceId, enabledDatasources.value],
  () => {
    const want = Number(props.initialDatasourceId)
    if (!(want > 0)) return
    const ds = enabledDatasources.value.find((d) => d.id === want)
    if (!ds) return
    datasourceId.value = ds.id
    envFilterId.value = null
  },
  { immediate: true }
)

/** 切换数据源类型时重置编辑器，避免 SQL/Redis/ES 语句串到错误驱动 */
const prevConsoleDbType = ref(null)
watch(
  () => (selectedDs.value?.db_type || '').toLowerCase(),
  (type) => {
    if (!type) return
    if (prevConsoleDbType.value && prevConsoleDbType.value !== type) {
      statement.value = defaultStatement.value
      rows.value = []
      columns.value = []
      errorText.value = ''
      meta.value = null
      ranOnce.value = false
    } else if (!prevConsoleDbType.value) {
      const cur = (statement.value || '').trim()
      if (!cur || cur === 'SELECT 1') {
        statement.value = defaultStatement.value
      }
    }
    prevConsoleDbType.value = type
  }
)

watch(
  () => [datasourceId.value, consoleWorkerId.value],
  (curr, prev) => {
    const [dsId, workerId] = curr || []
    const [prevDsId, prevWorkerId] = prev || []
    // 进入页 / 切数据源 / 切执行机：只清空目录，不自动请求（内网库常需先勾选经执行机）
    if (!prev || dsId !== prevDsId || workerId !== prevWorkerId) {
      if (prev && (dsId !== prevDsId || workerId !== prevWorkerId)) {
        execGen.value += 1
        running.value = false
        clearExecutionResult()
      }
      resetCatalogPanel()
      loadHistory()
    }
  }
)

function clearAll() {
  statement.value = defaultStatement.value
  rows.value = []
  columns.value = []
  errorText.value = ''
  meta.value = null
  ranOnce.value = false
}

async function runConsole(forceConfirm) {
  if (!canRun.value || running.value) return
  const ds = selectedDs.value
  const dsId = datasourceId.value
  const workerId = consoleWorkerId.value
  const myExec = ++execGen.value
  const sql = statement.value.trim()
  const isWrite = looksLikeWrite(sql, ds?.db_type)
  let confirmWrite = !!forceConfirm

  if (isWrite && !confirmWrite) {
    if (!ds?.allow_write) {
      ElMessage.warning('当前数据源为只读，无法执行写操作')
      return
    }
    try {
      await ElMessageBox.confirm(
        '将执行写操作并可能修改业务库数据，是否继续？',
        '写操作确认',
        { type: 'warning', confirmButtonText: '确认执行', cancelButtonText: '取消' }
      )
      confirmWrite = true
    } catch {
      return
    }
  }

  running.value = true
  errorText.value = ''
  try {
    const res = await dataFactoryApi.executeConsole({
      project_id: props.projectId,
      environment_id: envId.value,
      datasource_id: dsId,
      sql,
      variables: {},
      confirm_write: confirmWrite,
      ...(workerId ? { worker_id: Number(workerId) } : {}),
    })
    if (myExec !== execGen.value || dsId !== datasourceId.value) return
    const data = res.data || {}
    if (data.requires_confirm) {
      try {
        await ElMessageBox.confirm(data.error || '写操作需确认', '写操作确认', {
          type: 'warning',
          confirmButtonText: '确认执行',
        })
        await runConsole(true)
      } catch {
        /* cancel */
      }
      return
    }
    ranOnce.value = true
    if (!data.success) {
      errorText.value = data.error || '执行失败'
      rows.value = []
      columns.value = []
      meta.value = { elapsed_ms: data.elapsed_ms }
      return
    }
    rows.value = data.rows || []
    columns.value = data.columns?.length
      ? data.columns
      : rows.value[0]
        ? Object.keys(rows.value[0])
        : []
    meta.value = {
      row_count: data.row_count,
      affected_rows: data.affected_rows,
      elapsed_ms: data.elapsed_ms,
      truncated: data.truncated,
      max_rows_applied: data.max_rows_applied,
      via_worker: !!data.via_worker,
    }
    pushHistory(sql)
    ElMessage.success(
      data.truncated
        ? '执行成功（结果已截断）'
        : data.via_worker
          ? '执行成功（经执行机）'
          : '执行成功'
    )
  } catch (e) {
    if (myExec !== execGen.value || dsId !== datasourceId.value) return
    const detail = e?.response?.data?.detail
    errorText.value = typeof detail === 'string' ? detail : e?.message || '执行失败'
    rows.value = []
    columns.value = []
  } finally {
    if (myExec === execGen.value) running.value = false
  }
}

async function saveAsTemplate() {
  if (!canSave.value) return
  try {
    const { value: name } = await ElMessageBox.prompt('模板名称', '另存为 SQL 模板', {
      inputValue: `控制台_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}`,
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '请输入名称',
    })
    let templateType = 'query'
    if (!isRedis.value && !isEs.value) {
      try {
        const { value: t } = await ElMessageBox.prompt(
          '类型：query / setup / teardown（默认 query）',
          '模板类型',
          { inputValue: 'query', confirmButtonText: '确定' }
        )
        if (['query', 'setup', 'teardown'].includes(String(t || '').trim())) {
          templateType = String(t).trim()
        }
      } catch {
        /* 用默认 query */
      }
    }
    await dataFactoryApi.createSqlTemplate({
      project_id: props.projectId,
      name: String(name).trim(),
      template_type: templateType,
      datasource_id: datasourceId.value,
      sql_text: statement.value.trim(),
      description: '由查询控制台另存',
    })
    ElMessage.success('已保存为模板')
    emit('saved-template')
  } catch {
    /* cancel */
  }
}
</script>

<style scoped>
.console-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.console-body {
  display: flex;
  gap: 12px;
  align-items: stretch;
  min-height: 360px;
}
.object-browser {
  width: 260px;
  flex-shrink: 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  background: var(--el-fill-color-blank);
}
.ob-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}
.ob-filter {
  margin-bottom: 6px;
}
.ob-tree-wrap {
  flex: 1;
  min-height: 200px;
  max-height: 420px;
  overflow: auto;
}
.ob-more {
  margin: 4px 6px 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ob-obj {
  border-radius: 3px;
}
.ob-obj.active {
  background: var(--el-fill-color-light);
}
.ob-obj-row,
.ob-col-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 4px 6px;
  cursor: pointer;
  border-radius: 3px;
  font-size: 12px;
  line-height: 1.4;
}
.ob-obj-row:hover,
.ob-col-row:hover {
  background: var(--el-fill-color);
}
.ob-caret {
  width: 12px;
  flex-shrink: 0;
  color: var(--el-text-color-secondary);
}
.ob-cols {
  padding: 0 0 4px 18px;
}
.ob-struct-actions {
  display: flex;
  gap: 4px;
  padding: 2px 6px 4px;
}
.ob-cols-loading,
.ob-cols-empty {
  padding: 4px 6px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.ob-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ob-meta {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.ob-hint,
.ob-tip {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
.ob-error {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--el-color-danger);
  line-height: 1.4;
}
.console-main {
  flex: 1;
  min-width: 0;
}
.editor-wrap {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
}
.redis-input :deep(textarea) {
  font-family: Consolas, Monaco, monospace;
}
.console-hint {
  margin: 8px 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.result-meta {
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.result-actions {
  flex-shrink: 0;
}
.cell-copy {
  cursor: pointer;
}
.cell-copy:hover {
  color: var(--el-color-primary);
}
.result-table {
  margin-top: 8px;
}
@media (max-width: 900px) {
  .console-body {
    flex-direction: column;
  }
  .object-browser {
    width: 100%;
  }
}
</style>
