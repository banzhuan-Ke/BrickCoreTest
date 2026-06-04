<template>
  <el-dialog
    v-model="visible"
    title="接口变更同步检测"
    width="800px"
    destroy-on-close
    class="sync-diff-dialog"
  >
    <div v-if="apiData" class="sync-diff-header">
      <el-tag :type="getMethodType(apiData.method)" size="small">{{ apiData.method }}</el-tag>
      <span class="api-path">{{ apiData.path }}</span>
      <span class="api-name">{{ apiData.name }}</span>
    </div>

    <div v-if="diffData" class="sync-diff-summary">
      关联用例共 <strong>{{ diffData.total_cases }}</strong> 条，其中
      <el-tag v-if="diffData.diff_count" type="danger" size="small" effect="dark" style="margin-left: 6px;">
        {{ diffData.diff_count }} 条不一致
      </el-tag>
      <el-tag v-if="diffData.warning_count" type="warning" size="small" effect="dark" style="margin-left: 6px;">
        {{ diffData.warning_count }} 条未完全覆盖
      </el-tag>
    </div>

    <el-table
      v-if="diffData?.inconsistent_cases?.length"
      :data="diffData.inconsistent_cases"
      size="small"
      border
      class="diff-table"
    >
      <el-table-column label="用例名称" width="160">
        <template #default="{ row }">
          <el-tooltip :content="`用例 ID: ${row.case_id}`" placement="top">
            <span class="case-name">{{ row.case_name }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="差异详情" min-width="400">
        <template #default="{ row }">
          <div class="diff-list">
            <div
              v-for="(diff, idx) in row.diffs"
              :key="'d-' + idx"
              class="diff-item diff-error"
            >
              <el-icon><CircleCloseFilled /></el-icon>
              <span>{{ diff }}</span>
            </div>
            <div
              v-for="(warn, idx) in row.warnings"
              :key="'w-' + idx"
              class="diff-item diff-warn"
            >
              <el-icon><WarningFilled /></el-icon>
              <span>{{ warn }}</span>
            </div>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" @click="goToCaseList">
        前往用例列表处理
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCloseFilled, WarningFilled } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: Boolean,
  apiData: Object,
  diffData: Object
})

const emit = defineEmits(['update:modelValue'])

const router = useRouter()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const getMethodType = (method) => {
  const map = { GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger', PATCH: 'info' }
  return map[method] || ''
}

const goToCaseList = () => {
  visible.value = false
  if (props.apiData?.id) {
    router.push(`/api-case?api_id=${props.apiData.id}`)
  }
}
</script>

<style scoped lang="scss">
.sync-diff-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 15px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--el-border-color-lighter);

  .api-path {
    font-family: 'Consolas', monospace;
    color: var(--el-text-color-secondary);
    font-size: 13px;
  }

  .api-name {
    font-weight: 500;
    color: var(--el-text-color-primary);
  }
}

.sync-diff-summary {
  margin-bottom: 15px;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.diff-table {
  .case-name {
    font-weight: 500;
  }

  .diff-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .diff-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    line-height: 1.4;

    .el-icon {
      font-size: 14px;
      flex-shrink: 0;
    }
  }

  .diff-error {
    color: var(--el-color-danger);
  }

  .diff-warn {
    color: var(--el-color-warning);
  }
}
</style>
