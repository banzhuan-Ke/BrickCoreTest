<template>
  <div class="assertion-groups-editor">
    <p class="hint top-hint">条件与断言均可针对状态码、响应体或响应头；选响应头时目标填 Header 名。</p>
    <div v-for="(group, gIndex) in modelValue" :key="gIndex" class="group-card">
      <div class="group-header">
        <el-input v-model="group.name" size="small" placeholder="分支名称，如：成功响应" style="width: 200px" />
        <el-tag v-if="group.is_else" type="info" size="small">Else 分支</el-tag>
        <el-tag v-else-if="group.condition" type="warning" size="small">条件分支</el-tag>
        <div class="group-actions">
          <el-button type="danger" link size="small" @click="removeGroup(gIndex)" icon="Delete">删除组</el-button>
        </div>
      </div>

      <div v-if="!group.is_else" class="condition-row">
        <span class="cond-label">当满足：</span>
        <HttpAssertionTypeSelect
          v-model="group.condition.type"
          size="small"
          select-style="width: 168px"
          @update:model-value="onConditionTypeChange(group.condition)"
        />
        <el-input
          v-if="assertionNeedsTarget(group.condition.type)"
          v-model="group.condition.target"
          size="small"
          :placeholder="assertionTargetPlaceholder(group.condition.type)"
          style="width: 140px"
        />
        <el-select
          v-if="!['contains', 'not_contains'].includes(group.condition.type)"
          v-model="group.condition.operator"
          size="small"
          style="width: 110px"
        >
          <el-option label="等于" value="equals" />
          <el-option label="不等于" value="not_equals" />
          <el-option label="大于" value="gt" />
          <el-option label="小于" value="lt" />
          <el-option label="包含" value="contains" />
        </el-select>
        <el-input v-model="group.condition.expected" size="small" placeholder="期望值" style="width: 120px" />
      </div>

      <div class="group-assertions">
        <div class="sub-title">
          <span>本分支断言</span>
          <el-button type="primary" link size="small" @click="addAssertion(gIndex)" icon="Plus">添加断言</el-button>
        </div>
        <el-table :data="group.assertions" size="small" border>
          <el-table-column label="断言方式" min-width="160">
            <template #default="{ $index }">
              <HttpAssertionTypeSelect
                v-model="group.assertions[$index].type"
                size="small"
                @update:model-value="onConditionTypeChange(group.assertions[$index])"
              />
            </template>
          </el-table-column>
          <el-table-column label="目标" width="130">
            <template #default="{ $index }">
              <el-input
                v-if="assertionNeedsTarget(group.assertions[$index].type)"
                v-model="group.assertions[$index].target"
                size="small"
                :placeholder="assertionTargetPlaceholder(group.assertions[$index].type)"
              />
              <span v-else class="target-na">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作符" width="100">
            <template #default="{ $index }">
              <el-select
                v-if="!['contains', 'not_contains'].includes(group.assertions[$index].type)"
                v-model="group.assertions[$index].operator"
                size="small"
              >
                <el-option label="等于" value="equals" />
                <el-option label="不等于" value="not_equals" />
                <el-option label="包含" value="contains" />
                <el-option label="大于" value="gt" />
                <el-option label="小于" value="lt" />
              </el-select>
              <span v-else class="operator-fixed">{{ group.assertions[$index].type === 'not_contains' ? '不包含' : '包含' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期望值">
            <template #default="{ $index }">
              <el-input v-model="group.assertions[$index].expected" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="{ $index }">
              <el-button type="danger" link size="small" @click="removeAssertion(gIndex, $index)" icon="Delete" />
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div class="group-toolbar">
      <el-button size="small" @click="addConditionGroup" icon="Plus">添加条件分支</el-button>
      <el-button size="small" @click="addElseGroup" icon="Plus">添加 Else 分支</el-button>
    </div>
    <p class="hint">按顺序匹配：命中第一个满足条件的分支后执行其断言；Else 分支在前序均未命中时执行。</p>
  </div>
</template>

<script setup>
import HttpAssertionTypeSelect from './HttpAssertionTypeSelect.vue'
import {
  assertionNeedsTarget,
  assertionTargetPlaceholder,
} from '../utils/httpExtractAssertUi.js'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const defaultCondition = () => ({
  type: 'json_path',
  target: '$.code',
  operator: 'equals',
  expected: '0',
})

const defaultAssertion = () => ({
  type: 'status_code',
  target: '',
  operator: 'equals',
  expected: '200',
  description: '',
})

const update = (val) => emit('update:modelValue', val)

const onConditionTypeChange = (row) => {
  if (!row) return
  if (row.type === 'contains') {
    row.operator = 'contains'
  } else if (row.type === 'not_contains') {
    row.operator = 'not_contains'
  } else if (!row.operator) {
    row.operator = 'equals'
  }
  if (!assertionNeedsTarget(row.type)) {
    row.target = ''
  }
}

const addConditionGroup = () => {
  update([
    ...props.modelValue,
    { name: `分支 ${props.modelValue.length + 1}`, condition: defaultCondition(), is_else: false, assertions: [defaultAssertion()] },
  ])
}

const addElseGroup = () => {
  if (props.modelValue.some(g => g.is_else)) {
    return
  }
  update([
    ...props.modelValue,
    { name: 'Else', condition: null, is_else: true, assertions: [defaultAssertion()] },
  ])
}

const removeGroup = (index) => {
  const next = [...props.modelValue]
  next.splice(index, 1)
  update(next)
}

const addAssertion = (gIndex) => {
  const next = props.modelValue.map((g, i) =>
    i === gIndex ? { ...g, assertions: [...(g.assertions || []), defaultAssertion()] } : g
  )
  update(next)
}

const removeAssertion = (gIndex, aIndex) => {
  const next = props.modelValue.map((g, i) => {
    if (i !== gIndex) return g
    const assertions = [...(g.assertions || [])]
    assertions.splice(aIndex, 1)
    return { ...g, assertions }
  })
  update(next)
}
</script>

<style scoped>
.group-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  background: var(--el-fill-color-blank);
}
.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.group-actions {
  margin-left: auto;
}
.condition-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.cond-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.sub-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
}
.group-toolbar {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
.hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.top-hint {
  margin-top: 0;
  margin-bottom: 10px;
}
.operator-fixed,
.target-na {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
