<template>
  <el-collapse v-model="activeNames" class="case-used-vars-panel">
    <el-collapse-item name="vars">
      <template #title>
        <span class="collapse-title">
          <el-icon><Collection /></el-icon>
          本用例引用变量
          <el-tag v-if="rows.length" size="small" type="info" style="margin-left: 8px">{{ rows.length }} 项</el-tag>
        </span>
      </template>
      <p class="panel-hint">
        自动扫描请求/断言/脚本中的 <code v-pre>${{变量名}}</code>、<code v-pre>${{df:标签}}</code>、<code v-pre>${{dt:...}}</code> 等占位符。
      </p>
      <el-table v-if="rows.length" :data="rows" size="small" border max-height="280">
        <el-table-column label="引用" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="ref-code">{{ row.display }}</code>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.tagType || 'info'" size="small">{{ row.typeLabel }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="count" label="次数" width="64" align="center" />
        <el-table-column label="字段" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.steps.join('、') }}
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="当前用例中未检测到变量占位符" :image-size="56" />
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Collection } from '@element-plus/icons-vue'
import { extractApiCaseVarRefs } from '@/utils/apiCaseVarRefs'

const props = defineProps({
  caseForm: {
    type: Object,
    default: () => ({}),
  },
})

const activeNames = ref([])
const rows = computed(() => extractApiCaseVarRefs(props.caseForm))
</script>

<style scoped lang="scss">
.case-used-vars-panel {
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.collapse-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}

.panel-hint {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

.ref-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}
</style>
