<template>
  <el-dropdown trigger="click" @command="onInsert" max-height="320">
    <el-button :size="size" :type="type" :link="link" :icon="Promotion">
      {{ label }}
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item v-if="projectVars.length" disabled divided>项目变量</el-dropdown-item>
        <el-dropdown-item
          v-for="item in projectVars"
          :key="'p-' + item.key"
          :command="item.key"
        >
          <span class="var-key">{{ item.key }}</span>
          <span class="var-preview">{{ previewValue(item.value) }}</span>
        </el-dropdown-item>

        <el-dropdown-item v-if="envVars.length" disabled divided>环境变量</el-dropdown-item>
        <el-dropdown-item
          v-for="item in envVars"
          :key="'e-' + item.key"
          :command="item.key"
        >
          <span class="var-key">{{ item.key }}</span>
          <span class="var-preview">{{ previewValue(item.value) }}</span>
        </el-dropdown-item>
        <el-dropdown-item v-if="!envVars.length && envId" disabled>
          当前环境暂无变量
        </el-dropdown-item>
        <el-dropdown-item v-if="!envId" disabled>
          请先选择执行环境
        </el-dropdown-item>

        <el-dropdown-item disabled divided>内置变量</el-dropdown-item>
        <el-dropdown-item
          v-for="item in builtinHints"
          :key="'b-' + item.key"
          :command="item.key"
        >
          <span class="var-key">{{ item.key }}</span>
          <span class="var-preview">{{ item.label }}</span>
        </el-dropdown-item>

        <el-dropdown-item v-if="extraVars.length" disabled divided>本用例变量</el-dropdown-item>
        <el-dropdown-item
          v-for="key in extraVars"
          :key="'x-' + key"
          :command="key"
        >
          <span class="var-key">{{ key }}</span>
        </el-dropdown-item>

        <el-dropdown-item v-if="showEnvEdit && envId" divided command="__edit_env__">
          管理环境变量…
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup>
import { computed } from 'vue'
import { Promotion } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { BUILTIN_VAR_HINTS, isSecretKey, varsObjectToList } from '@/utils/globalVars.js'
import { insertVarRef } from '@/utils/varInsert.js'

const props = defineProps({
  envId: { type: Number, default: null },
  extraVars: { type: Array, default: () => [] },
  label: { type: String, default: '插入变量' },
  size: { type: String, default: 'small' },
  type: { type: String, default: 'primary' },
  link: { type: Boolean, default: true },
  showEnvEdit: { type: Boolean, default: true },
})

const emit = defineEmits(['edit-env-vars'])

const proStore = ProjectStore()
const builtinHints = BUILTIN_VAR_HINTS

const projectVars = computed(() => {
  const gv = proStore.projectInfo?.global_vars
  return varsObjectToList(gv && typeof gv === 'object' ? gv : {})
})

const envVars = computed(() => {
  if (!props.envId) return []
  const env = proStore.envList.find((e) => e.id === props.envId)
  return varsObjectToList(env?.global_vars)
})

function previewValue(value) {
  const s = String(value ?? '')
  if (s.length > 24) return s.slice(0, 24) + '…'
  return s
}

async function onInsert(command) {
  if (command === '__edit_env__') {
    emit('edit-env-vars')
    return
  }
  const result = await insertVarRef(command)
  if (result?.ok) {
    const tip =
      result.mode === 'copy'
        ? `已复制 ${formatDisplay(command)}，请粘贴到输入框`
        : `已插入 ${formatDisplay(command)}`
    ElMessage.success(tip)
  } else {
    ElMessage.warning('请先将光标放入输入框')
  }
}

function formatDisplay(name) {
  return `\${{${name}}}`
}
</script>

<style scoped lang="scss">
.var-key {
  font-family: monospace;
  margin-right: 8px;
}

.var-preview {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
