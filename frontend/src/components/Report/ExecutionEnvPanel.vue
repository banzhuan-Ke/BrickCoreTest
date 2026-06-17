<template>
  <div class="execution-env-panel" v-if="hasEnv">
    <!-- 运行参数 -->
    <div class="env-block">
      <div class="env-block-title">运行参数</div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item
          v-for="item in basicItems"
          :key="item.key"
          :label="item.label"
        >
          <template v-if="item.key === 'headless'">
            <el-tag size="small" :type="item.value ? 'info' : 'success'">
              {{ item.value ? '是（后台运行）' : '否（可见浏览器）' }}
            </el-tag>
          </template>
          <template v-else-if="item.key === 'browser'">
            <el-tag size="small" type="primary">{{ item.value }}</el-tag>
          </template>
          <span v-else>{{ item.value }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 环境变量 -->
    <div class="env-block" v-if="variableRows.length">
      <div class="env-block-title">
        环境变量
        <el-tag size="small" type="info">{{ variableRows.length }} 个</el-tag>
      </div>
      <el-table :data="variableRows" size="small" border class="env-var-table">
        <el-table-column prop="name" label="变量名" width="160">
          <template #default="{ row }">
            <code class="var-name">{{ row.name }}</code>
          </template>
        </el-table-column>
        <el-table-column label="值" min-width="220">
          <template #default="{ row }">
            <div class="var-value-cell">
              <el-tooltip
                v-if="row.display.length > 80 || row.sensitive"
                :content="row.sensitive && !row.revealed ? '点击右侧按钮查看完整内容' : row.value"
                placement="top"
                :show-after="200"
                popper-class="execution-env-value-tooltip"
              >
                <span class="var-value-text">{{ row.display }}</span>
              </el-tooltip>
              <span v-else class="var-value-text">{{ row.display }}</span>
              <el-button
                v-if="row.sensitive"
                link
                type="primary"
                size="small"
                class="var-reveal-btn"
                @click="toggleReveal(row.name)"
              >
                {{ revealedKeys.has(row.name) ? '隐藏' : '查看' }}
              </el-button>
              <el-button
                link
                type="primary"
                size="small"
                class="var-copy-btn"
                @click="copyValue(row.value)"
              >
                复制
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="说明" width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.dynamic" size="small" type="warning" effect="plain">动态</el-tag>
            <el-tag v-else-if="row.sensitive" size="small" type="danger" effect="plain">敏感</el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 用例命名规范 -->
    <div class="env-block" v-if="namingItems.length">
      <div class="env-block-title">用例命名规范</div>
      <div class="naming-list">
        <div v-for="(item, idx) in namingItems" :key="idx" class="naming-item">
          <span class="naming-name">{{ item.name }}</span>
          <el-tag size="small" :type="item.enabled ? 'success' : 'info'">
            {{ item.enabled ? '已启用' : '未启用' }}
          </el-tag>
          <span v-if="item.version != null" class="text-muted">v{{ item.version }}</span>
        </div>
      </div>
    </div>

    <!-- 其他配置 -->
    <div class="env-block" v-if="otherItems.length">
      <div class="env-block-title">其他配置</div>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item
          v-for="item in otherItems"
          :key="item.key"
          :label="item.label"
        >
          <EnvValueCell :value="item.value" />
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 原始 JSON（折叠） -->
    <el-collapse v-model="rawJsonOpen" class="env-raw-collapse">
      <el-collapse-item name="raw" title="查看完整 JSON（高级）">
        <VueJsonPretty :data="env" :showIcon="true" class="env-json-raw" />
      </el-collapse-item>
    </el-collapse>
  </div>
  <el-empty v-else description="暂无环境配置" :image-size="48" />
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import EnvValueCell from '@/components/Report/EnvValueCell.vue'
import {
  BASIC_ENV_FIELDS,
  buildBasicEnvItems,
  buildOtherEnvItems,
  buildVariableRows,
  buildNamingItems,
  maskSensitiveValue
} from '@/utils/executionEnv.js'

const props = defineProps({
  env: {
    type: Object,
    default: () => null
  }
})

const rawJsonOpen = ref([])
const revealedKeys = ref(new Set())

const hasEnv = computed(() => props.env && typeof props.env === 'object' && Object.keys(props.env).length > 0)

const basicItems = computed(() => buildBasicEnvItems(props.env, BASIC_ENV_FIELDS))

const variableRows = computed(() => {
  return buildVariableRows(props.env?.variables).map((row) => ({
    ...row,
    display: row.sensitive && !revealedKeys.value.has(row.name)
      ? maskSensitiveValue(row.value)
      : row.value
  }))
})

const namingItems = computed(() => buildNamingItems(props.env?.case_naming))

const otherItems = computed(() => buildOtherEnvItems(props.env, BASIC_ENV_FIELDS))

function toggleReveal(name) {
  const next = new Set(revealedKeys.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  revealedKeys.value = next
}

async function copyValue(value) {
  try {
    await navigator.clipboard.writeText(String(value ?? ''))
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped lang="scss">
.execution-env-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.env-block {
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;

  .env-block-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 12px;
    color: var(--el-text-color-primary);
  }
}

.env-var-table {
  background: var(--el-bg-color);
  border-radius: 6px;
  overflow: hidden;
}

.var-name {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: var(--el-color-primary);
}

.var-value-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.var-value-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}

.var-reveal-btn,
.var-copy-btn {
  flex-shrink: 0;
  padding: 0 4px;
}

.naming-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.naming-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--el-bg-color);
  border-radius: 6px;

  .naming-name {
    font-weight: 500;
  }
}

.env-raw-collapse {
  border: none;
  background: transparent;

  :deep(.el-collapse-item__header) {
    font-size: 13px;
    color: var(--el-text-color-secondary);
    background: transparent;
    border: none;
    padding-left: 0;
  }

  :deep(.el-collapse-item__wrap) {
    border: none;
    background: transparent;
  }

  :deep(.el-collapse-item__content) {
    padding-bottom: 0;
  }
}

.env-json-raw {
  padding: 12px;
  background: var(--el-bg-color);
  border-radius: 8px;
  max-height: 360px;
  overflow: auto;
}

.text-muted {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
</style>

<style lang="scss">
.execution-env-value-tooltip {
  max-width: min(720px, 92vw) !important;

  .el-popper__content,
  & {
    white-space: pre-wrap;
    word-break: break-all;
    line-height: 1.5;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 12px;
  }
}
</style>
