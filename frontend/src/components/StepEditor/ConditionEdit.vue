<template>
  <div class="condition-edit">
    <div class="condition-header">
      <el-icon size="20" color="#e6a23c"><Share /></el-icon>
      <span class="title">条件分支配置</span>
      <el-text type="info" size="small">按顺序匹配第一个满足条件的分支</el-text>
    </div>

    <div class="branches-list">
      <div
        v-for="(branch, index) in localBranches"
        :key="branch.id || `branch_${index}`"
        class="branch-card"
        :class="{ 'is-else': branch.condition?.type === 'else' }"
      >
        <div class="branch-card-header">
          <div class="branch-title">
            <el-tag :type="branch.condition?.type === 'else' ? 'info' : 'primary'" effect="dark" size="small">
              {{ branch.condition?.type === 'else' ? 'ELSE' : `IF ${index + 1}` }}
            </el-tag>
            <el-input
              v-model="branch.name"
              size="small"
              placeholder="分支名称"
              class="branch-name-input"
              @change="updateBranches"
            />
          </div>
          <div class="branch-actions" v-if="branch.condition?.type !== 'else'">
            <el-button link type="danger" size="small" :icon="Delete" @click="removeBranch(index)">删除</el-button>
          </div>
        </div>

        <div v-if="branch.condition?.type !== 'else'" class="condition-config">
          <el-form label-width="80px" size="small">
            <el-form-item label="条件类型">
              <el-select v-model="branch.condition.type" placeholder="选择条件类型" style="width: 100%" @change="updateBranches">
                <el-option v-for="item in conditionTypes" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>

            <template v-if="isElementCondition(branch.condition.type)">
              <el-form-item label="元素定位">
                <template v-if="isAppModule">
                  <div class="app-branch-locator">
                    <div class="app-locator-row">
                      <el-select
                        v-if="!isImageLocator(branch.condition.locator)"
                        v-model="branch.condition.locator.context"
                        placeholder="定位环境"
                        style="width: 120px"
                        @change="onAppLocatorContextChange(branch)"
                      >
                        <el-option label="原生 App" :value="APP_LOCATOR_CONTEXT_NATIVE" />
                        <el-option label="WebView / H5" value="webview" />
                      </el-select>
                      <el-select
                        v-model="branch.condition.locator.by"
                        placeholder="定位方式"
                        style="width: 130px"
                        @change="onAppLocatorByChange(branch)"
                      >
                        <el-option
                          v-for="opt in branchLocatorOptions(branch)"
                          :key="opt.value"
                          :label="opt.label"
                          :value="opt.value"
                        />
                      </el-select>
                      <el-input
                        v-if="!isImageLocator(branch.condition.locator)"
                        v-model="branch.condition.locator.value"
                        placeholder="定位值"
                        style="flex: 1"
                        @change="updateBranches"
                      />
                      <el-input-number
                        v-if="!isImageLocator(branch.condition.locator)"
                        v-model="branch.condition.locator.index"
                        :min="1"
                        :max="99"
                        controls-position="right"
                        style="width: 96px"
                        @change="updateBranches"
                      />
                    </div>
                    <template v-if="isImageLocator(branch.condition.locator)">
                      <el-input
                        v-model="branch.condition.locator.value"
                        placeholder="模板路径或元素库 object_key"
                        size="small"
                        @change="updateBranches"
                      />
                      <div class="app-image-fields">
                        <span class="field-label">阈值</span>
                        <el-slider
                          v-model="branch.condition.locator.threshold"
                          :min="0.5"
                          :max="1"
                          :step="0.05"
                          style="flex: 1"
                          @change="updateBranches"
                        />
                        <span class="field-label">RGB</span>
                        <el-switch v-model="branch.condition.locator.rgb" @change="updateBranches" />
                      </div>
                    </template>
                  </div>
                </template>
                <el-input
                  v-else
                  v-model="branch.condition.locator"
                  placeholder="如: #username 或 xpath=//input"
                  @change="updateBranches"
                />
              </el-form-item>
            </template>

            <template v-if="isTextCompareCondition(branch.condition.type)">
              <el-form-item label="预期值">
                <el-input v-model="branch.condition.expected_value" placeholder="请输入预期文本" @change="updateBranches" />
              </el-form-item>
            </template>

            <template v-if="!isAppModule && branch.condition.type === 'page_title_equals'">
              <el-form-item label="预期标题">
                <el-input v-model="branch.condition.expected_value" placeholder="请输入预期页面标题" />
              </el-form-item>
            </template>

            <template v-if="!isAppModule && branch.condition.type === 'page_url_contains'">
              <el-form-item label="URL包含">
                <el-input v-model="branch.condition.expected_value" placeholder="请输入URL包含的文本" />
              </el-form-item>
            </template>

            <template v-if="!isAppModule && branch.condition.type === 'custom_js'">
              <el-form-item label="JS表达式">
                <el-input
                  v-model="branch.condition.script"
                  type="textarea"
                  :rows="3"
                  placeholder="返回 true/false 的JavaScript表达式"
                />
              </el-form-item>
            </template>

            <el-form-item label="判断方式">
              <el-radio-group v-model="branch.condition.operator" @change="updateBranches">
                <el-radio label="is_true">条件为真</el-radio>
                <el-radio label="is_false">条件为假</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-form>
        </div>

        <div v-else-if="branch.condition?.type === 'else'" class="else-desc">
          <el-text type="info">当以上所有条件都不满足时，执行此分支</el-text>
        </div>
        <div v-else class="else-desc">
          <el-text type="warning">请配置分支条件</el-text>
        </div>
      </div>
    </div>

    <div class="add-branch-action">
      <el-button type="primary" plain :icon="Plus" @click="addBranch">添加条件分支</el-button>
    </div>

    <el-alert title="使用说明" type="info" :closable="false" class="usage-tip">
      <template #default>
        <ol>
          <li>条件按顺序从上到下匹配，执行第一个满足条件的分支</li>
          <li>ELSE 分支必须放在最后，当其他条件都不满足时执行</li>
          <li>App 模块支持原生 / WebView H5 / 图像模板定位（与步骤编辑器一致）</li>
        </ol>
      </template>
    </el-alert>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Share, Delete, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  APP_CONDITION_TYPES,
  defaultAppLocator,
  APP_LOCATOR_CONTEXT_NATIVE,
  prepareAppLocatorForEdit,
  serializeAppLocatorForSave,
  normalizeAppLocator,
  getAppLocatorByOptions,
  isWebviewLocator,
  isImageLocator,
  isAppLocatorFilled,
} from '@/utils/appStepMeta.js'

const props = defineProps({
  branches: { type: Array, default: () => [] },
  module: { type: String, default: 'web' },
})

const emit = defineEmits(['update:branches'])
const isAppModule = computed(() => props.module === 'app')
const localBranches = ref([])

watch(() => props.branches, (newBranches) => {
  const cloned = JSON.parse(JSON.stringify(newBranches || []))
  if (isAppModule.value) {
    for (const branch of cloned) {
      const cond = branch.condition
      if (!cond || cond.type === 'else') continue
      if (!cond.locator || typeof cond.locator !== 'object') {
        cond.locator = defaultAppLocator()
      } else {
        cond.locator = normalizeAppLocator(cond.locator)
      }
    }
  }
  localBranches.value = cloned
}, { immediate: true, deep: true })

function updateBranches() {
  emit('update:branches', JSON.parse(JSON.stringify(localBranches.value)))
}

const conditionTypes = computed(() => {
  if (isAppModule.value) return APP_CONDITION_TYPES
  return [
    { label: '元素可见', value: 'element_visible' },
    { label: '元素存在', value: 'element_exist' },
    { label: '元素文本等于', value: 'element_text_equals' },
    { label: '元素文本包含', value: 'element_text_contains' },
    { label: '页面标题等于', value: 'page_title_equals' },
    { label: '页面URL包含', value: 'page_url_contains' },
    { label: '自定义JS表达式', value: 'custom_js' },
  ]
})

function branchLocatorOptions(branch) {
  const opts = getAppLocatorByOptions(branch.condition?.locator || {})
  if (branch.condition?.type === 'element_text_contains') {
    return opts.filter((o) => o.value !== 'image')
  }
  return opts
}

function onAppLocatorContextChange(branch) {
  const loc = branch.condition.locator
  if (loc.context === 'webview') {
    if (!['css', 'xpath', 'text', 'id'].includes(String(loc.by || ''))) {
      loc.by = 'css'
    }
  } else if (!isImageLocator(loc)) {
    loc.context = APP_LOCATOR_CONTEXT_NATIVE
    if (['css', 'id', 'xpath'].includes(String(loc.by || ''))) {
      loc.by = 'resource_id'
    }
  }
  updateBranches()
}

function onAppLocatorByChange(branch) {
  const loc = branch.condition.locator
  if (isImageLocator(loc)) {
    loc.threshold = loc.threshold ?? 0.8
    loc.rgb = !!loc.rgb
    delete loc.context
    delete loc.index
  } else if (isWebviewLocator(loc)) {
    loc.context = 'webview'
    loc.index = loc.index ?? 1
  } else {
    loc.context = APP_LOCATOR_CONTEXT_NATIVE
    loc.index = loc.index ?? 1
    delete loc.threshold
    delete loc.rgb
  }
  updateBranches()
}

function isElementCondition(type) {
  return ['element_visible', 'element_exist', 'element_text_equals', 'element_text_contains'].includes(type)
}

function isTextCompareCondition(type) {
  return ['element_text_equals', 'element_text_contains'].includes(type)
}

function addBranch() {
  const elseIndex = localBranches.value.findIndex((b) => b.condition?.type === 'else')
  const newBranch = {
    id: `branch_${Date.now()}`,
    name: `分支${localBranches.value.length}`,
    condition: isAppModule.value
      ? { type: 'element_exist', locator: defaultAppLocator(), operator: 'is_true', expected_value: '' }
      : { type: 'element_visible', locator: '', operator: 'is_true', expected_value: '' },
    steps: [],
  }
  if (elseIndex >= 0) localBranches.value.splice(elseIndex, 0, newBranch)
  else localBranches.value.push(newBranch)
  updateBranches()
  ElMessage.success('分支已添加')
}

function removeBranch(index) {
  const branch = localBranches.value[index]
  if (branch.condition?.type === 'else') {
    ElMessage.warning('ELSE 分支不能删除')
    return
  }
  localBranches.value.splice(index, 1)
  updateBranches()
  ElMessage.success('分支已删除')
}

defineExpose({
  validateAppBranches() {
    if (!isAppModule.value) return null
    for (const branch of localBranches.value) {
      const cond = branch.condition
      if (!cond || cond.type === 'else') continue
      if (isElementCondition(cond.type) && !isAppLocatorFilled(cond.locator)) {
        return `分支「${branch.name || '未命名'}」请填写完整元素定位`
      }
      if (isTextCompareCondition(cond.type) && !String(cond.expected_value || '').trim()) {
        return `分支「${branch.name || '未命名'}」请填写预期文本`
      }
    }
    return null
  },
})
</script>

<style scoped lang="scss">
.condition-edit {
  padding: 10px;
}

.app-locator-row {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
  flex-wrap: wrap;
}

.app-branch-locator {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.app-image-fields {
  display: flex;
  align-items: center;
  gap: 10px;

  .field-label {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    white-space: nowrap;
  }
}

.condition-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--el-border-color-lighter);

  .title {
    font-size: 16px;
    font-weight: 500;
  }
}

.branches-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.branch-card {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  overflow: hidden;

  &.is-else {
    background: #f5f7fa;
    border-style: dashed;
  }
}

.branch-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-lighter);

  .branch-title {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;

    .branch-name-input {
      width: 200px;
    }
  }
}

.condition-config {
  padding: 16px;
}

.else-desc {
  padding: 16px;
  text-align: center;
}

.add-branch-action {
  margin-top: 16px;
  text-align: center;
}

.usage-tip {
  margin-top: 20px;

  ol {
    margin: 8px 0 0 16px;
    padding: 0;

    li {
      margin-bottom: 4px;
      line-height: 1.6;
    }
  }
}
</style>
