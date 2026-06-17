<template>
  <div class="stream-rule-builder">
    <el-divider content-position="left">阶段规则</el-divider>
    <div v-for="(phase, idx) in localRules.phases" :key="'p-' + idx" class="rule-block">
      <div class="rule-block-header">
        <span>阶段 {{ idx + 1 }}</span>
        <el-button type="danger" size="small" text :icon="Delete" @click="removePhase(idx)" :disabled="localRules.phases.length <= 1" />
      </div>
      <el-row :gutter="12">
        <el-col :span="6">
          <el-form-item label="标识 key" label-width="80px">
            <el-input v-model="phase.key" placeholder="如 first_char" @change="emitChange" />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="展示名" label-width="60px">
            <el-input v-model="phase.label" placeholder="首字时间(s)" @change="emitChange" />
          </el-form-item>
        </el-col>
        <el-col :span="4">
          <el-form-item label="type" label-width="50px">
            <el-input v-model="phase.match.type" @change="emitChange" />
          </el-form-item>
        </el-col>
        <el-col :span="4">
          <el-form-item label="agent" label-width="50px">
            <el-input v-model="phase.match.agent" @change="emitChange" />
          </el-form-item>
        </el-col>
        <el-col :span="4">
          <el-form-item label="action" label-width="55px">
            <el-input v-model="phase.match.action" @change="emitChange" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="6">
          <el-form-item label="status" label-width="80px">
            <el-input v-model="phase.match.status" placeholder="可选" @change="emitChange" />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label-width="20px">
            <el-checkbox v-model="phase.match.delta_nonempty" @change="emitChange">delta 非空</el-checkbox>
          </el-form-item>
        </el-col>
      </el-row>
    </div>
    <el-button type="primary" size="small" :icon="Plus" @click="addPhase">添加阶段</el-button>

    <el-divider content-position="left">派生指标</el-divider>
    <div v-for="(d, idx) in localRules.derived" :key="'d-' + idx" class="rule-block compact">
      <el-row :gutter="12" align="middle">
        <el-col :span="5">
          <el-input v-model="d.key" placeholder="key" @change="emitChange" />
        </el-col>
        <el-col :span="5">
          <el-input v-model="d.label" placeholder="展示名" @change="emitChange" />
        </el-col>
        <el-col :span="10">
          <el-input v-model="d.expr" placeholder="表达式 如 first_char - intent_complete" @change="emitChange" />
        </el-col>
        <el-col :span="4">
          <el-button type="danger" size="small" text :icon="Delete" @click="removeDerived(idx)" />
        </el-col>
      </el-row>
    </div>
    <el-button type="primary" size="small" plain :icon="Plus" @click="addDerived">添加派生指标</el-button>
  </div>
</template>

<script setup>
import { reactive, watch } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) }
})
const emit = defineEmits(['update:modelValue'])

const defaultRules = () => ({
  line_prefix: 'data:',
  done_markers: ['[DONE]', 'data:[DONE]'],
  phases: [
    { key: 'intent_complete', label: '意图完成(s)', match: { type: 'think', agent: 'think', action: 'intent', status: 'success' }, trigger: 'first' },
    { key: 'first_char', label: '首字时间(s)', match: { type: 'output_text', agent: 'conventional_summary', delta_nonempty: true }, trigger: 'first' }
  ],
  derived: [
    { key: 'thinking_duration', label: '思考耗时(s)', expr: 'first_char - intent_complete' }
  ],
  extras_extract: []
})

const localRules = reactive(defaultRules())

const syncFromProps = (val) => {
  const base = defaultRules()
  const src = val || {}
  Object.assign(localRules, {
    line_prefix: src.line_prefix || base.line_prefix,
    done_markers: src.done_markers || base.done_markers,
    phases: (src.phases && src.phases.length) ? JSON.parse(JSON.stringify(src.phases)) : base.phases,
    derived: (src.derived && src.derived.length) ? JSON.parse(JSON.stringify(src.derived)) : base.derived,
    extras_extract: src.extras_extract || []
  })
}

watch(() => props.modelValue, (v) => syncFromProps(v), { immediate: true, deep: true })

const emitChange = () => {
  emit('update:modelValue', JSON.parse(JSON.stringify(localRules)))
}

const addPhase = () => {
  localRules.phases.push({ key: '', label: '', match: { type: '', agent: '' }, trigger: 'first' })
  emitChange()
}
const removePhase = (idx) => {
  localRules.phases.splice(idx, 1)
  emitChange()
}
const addDerived = () => {
  localRules.derived.push({ key: '', label: '', expr: '' })
  emitChange()
}
const removeDerived = (idx) => {
  localRules.derived.splice(idx, 1)
  emitChange()
}
</script>

<style scoped>
.stream-rule-builder { width: 100%; }
.rule-block {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  background: var(--el-fill-color-blank);
}
.rule-block.compact { padding: 8px 12px; }
.rule-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
}
</style>
