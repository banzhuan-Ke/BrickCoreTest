<template>
  <div class="locator-selector">
    <el-autocomplete
      v-model="inputValue"
      :fetch-suggestions="fetchSuggestions"
      clearable
      placeholder="输入或选择定位表达式"
      style="width: 100%"
      @select="handleSelect"
      @blur="commitValue"
    />
    <div class="locator-hint">
      <el-tooltip placement="top" :show-after="300">
        <template #content>
          <div style="max-width: 360px; line-height: 1.8">
            <strong>支持的定位语法：</strong><br/>
            • CSS: <code>#id</code>、<code>.class</code>、<code>div.button</code><br/>
            • XPath: <code>//div</code>、<code>//span[@class='x']</code><br/>
            • get_by_text: <code>get_by_text=控制台</code><br/>
            • get_by_role: <code>get_by_role=button, 提交</code><br/>
            • get_by_label: <code>get_by_label=用户名</code><br/>
            • get_by_placeholder: <code>get_by_placeholder=请输入</code><br/>
            • iframe 嵌套: <code>iframe||#id</code>
          </div>
        </template>
        <el-link type="primary" :underline="false" style="font-size: 12px">
          <el-icon><InfoFilled /></el-icon> 定位语法说明
        </el-link>
      </el-tooltip>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  meta: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue'])

const inputValue = ref(props.modelValue || '')

watch(
  () => props.modelValue,
  (val) => {
    if (val !== inputValue.value) {
      inputValue.value = val || ''
    }
  }
)

function commitValue() {
  emit('update:modelValue', inputValue.value || '')
}

function handleSelect(item) {
  inputValue.value = item.value
  emit('update:modelValue', item.value)
}

watch(inputValue, (val) => {
  emit('update:modelValue', val || '')
})

// 常见短词：在页面上极易重复出现，不适合单独用 get_by_text 定位
const COMMON_SHORT_TEXTS = new Set([
  '登入', '登录', '确定', '取消', '提交', '保存', '新增', '删除', '编辑',
  '搜索', '查询', '重置', '下一步', '上一步', '完成', '关闭', '返回',
  '更多', '展开', '收起', '详情', '操作', '管理', '设置', '首页', '退出',
  '导入', '导出', '下载', '上传', '预览', '复制', '粘贴', '全选', '清空',
])

const DEFAULT_TEMPLATES = [
  { label: '模板: get_by_role=, （角色定位）', value: 'get_by_role=, ' },
  { label: '模板: get_by_text=（文本定位）', value: 'get_by_text=' },
  { label: '模板: get_by_label=（标签定位）', value: 'get_by_label=' },
  { label: '模板: get_by_placeholder=（placeholder）', value: 'get_by_placeholder=' },
  { label: '模板: #id（ID 定位）', value: '#' },
  { label: '模板: .class（class 定位）', value: '.' },
  { label: '模板: //tag（XPath 定位）', value: '//' },
]

const candidateOptions = computed(() => {
  const opts = []
  const m = props.meta || {}

  const engineCandidates = m.candidates || []
  if (engineCandidates.length > 0) {
    engineCandidates.forEach((cand) => {
      let label = cand
      if (cand.startsWith('[data-testid=')) label = `testid 定位: ${cand}`
      else if (cand.startsWith('#')) label = `ID 定位: ${cand}`
      else if (cand.startsWith('get_by_role=')) label = `角色定位: ${cand}`
      else if (cand.startsWith('get_by_text=')) label = `文本定位: ${cand}`
      else if (cand.startsWith('get_by_label=')) label = `标签定位: ${cand}`
      else if (cand.startsWith('get_by_placeholder=')) label = `placeholder 定位: ${cand}`
      else if (cand.startsWith('//')) label = `XPath: ${cand}`
      else if (cand.includes('.')) label = `class 定位: ${cand}`
      else label = `定位: ${cand}`
      opts.push({ label, value: cand })
    })
    return opts
  }

  const tag = (m.tag || '').toLowerCase()
  const text = (m.text || '').trim()
  const id = (m.id || '').trim()
  const name = (m.name || '').trim()
  const cls = (m.class || '').trim()
  const aria = (m.ariaLabel || '').trim()
  const placeholder = (m.placeholder || '').trim()
  const dataTestid = (m.dataTestid || '').trim()
  const role = (m.role || '').trim()
  const title = (m.title || '').trim()
  const isCommonShortText = text && COMMON_SHORT_TEXTS.has(text)

  if (dataTestid) {
    opts.push({ label: `testid 定位: [data-testid="${dataTestid}"]`, value: `[data-testid="${dataTestid}"]` })
  }
  if (id) {
    opts.push({ label: `ID 定位: #${id}`, value: `#${id}` })
  }
  if (role && text && !isCommonShortText && text.length < 30 && !/^\d+$/.test(text)) {
    opts.push({ label: `角色定位: get_by_role=${role}, ${text}`, value: `get_by_role=${role}, ${text}` })
  }
  if (cls) {
    const classList = cls.split(/\s+/).filter(c => c && !c.startsWith('ng-') && !c.startsWith('v-') && c.length < 30)
    if (classList.length > 0) {
      const prefix = tag || '*'
      opts.push({ label: `class 定位: ${prefix}.${classList[0]}`, value: `${prefix}.${classList[0]}` })
    }
  }
  if (name) {
    const prefix = tag || '*'
    opts.push({ label: `name 定位: ${prefix}[name="${name}"]`, value: `${prefix}[name="${name}"]` })
  }
  if (aria) {
    const prefix = tag || '*'
    opts.push({ label: `aria 定位: ${prefix}[aria-label="${aria}"]`, value: `${prefix}[aria-label="${aria}"]` })
  }
  if (placeholder && ['input', 'textarea'].includes(tag)) {
    opts.push({ label: `placeholder 定位: ${tag}[placeholder="${placeholder}"]`, value: `${tag}[placeholder="${placeholder}"]` })
  }
  if (title) {
    const prefix = tag || '*'
    opts.push({ label: `title 定位: ${prefix}[title="${title}"]`, value: `${prefix}[title="${title}"]` })
  }
  if (text && text.length < 30 && !/^\d+$/.test(text) && !isCommonShortText) {
    opts.push({ label: `文本定位: get_by_text=${text}`, value: `get_by_text=${text}` })
  }
  if (tag && text) {
    const classPart = cls ? `[@class='${cls.split(/\s+/)[0]}']` : ''
    opts.push({
      label: `XPath: //${tag}${classPart}[contains(text(),'${text}')]`,
      value: `//${tag}${classPart}[contains(text(),'${text}')]`
    })
  }

  if (opts.length === 0) {
    return DEFAULT_TEMPLATES
  }
  return opts
})

function fetchSuggestions(queryString, cb) {
  const q = (queryString || '').toLowerCase()
  const list = candidateOptions.value
    .filter(opt => !q || opt.label.toLowerCase().includes(q) || opt.value.toLowerCase().includes(q))
    .map(opt => ({ value: opt.value, label: opt.label }))
  cb(list)
}
</script>

<style scoped>
.locator-selector {
  width: 100%;
}
.locator-hint {
  margin-top: 4px;
  text-align: right;
}
</style>
