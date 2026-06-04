<template>
  <div class="assertion-groups-editor">
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
        <el-select v-model="group.condition.type" size="small" style="width: 110px">
          <el-option label="状态码" value="status_code" />
          <el-option label="JSON路径" value="json_path" />
          <el-option label="Header" value="header" />
          <el-option label="包含" value="contains" />
          <el-option label="不包含" value="not_contains" />
        </el-select>
        <el-input
          v-if="group.condition.type !== 'status_code' && !['contains', 'not_contains'].includes(group.condition.type)"
          v-model="group.condition.target"
          size="small"
          placeholder="$.code"
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
          <el-table-column label="类型" width="110">
            <template #default="{ $index }">
              <el-select v-model="group.assertions[$index].type" size="small">
                <el-option label="状态码" value="status_code" />
                <el-option label="JSON路径" value="json_path" />
                <el-option label="Header" value="header" />
                <el-option label="包含" value="contains" />
                <el-option label="不包含" value="not_contains" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="目标" width="130">
            <template #default="{ $index }">
              <el-input v-model="group.assertions[$index].target" size="small" placeholder="$.data.id" />
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
              <span v-else class="operator-fixed">包含</span>
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
.group-actions { margin-left: auto; }
.condition-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  padding: 8px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}
.cond-label { font-size: 13px; color: var(--el-text-color-secondary); }
.sub-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 13px;
}
.group-toolbar { display: flex; gap: 8px; margin-top: 8px; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 8px; }
.operator-fixed { font-size: 12px; color: #606266; }
</style>
