<template>
  <div class="locator-selector">
    <el-autocomplete
      v-model="inputValue"
      :fetch-suggestions="fetchSuggestions"
      :trigger-on-focus="true"
      clearable
      placeholder="点击展开候选定位（可输入搜索）"
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
            • iframe 嵌套: <code>iframe||#id</code>、<code>iframe||get_by_text=提交</code><br/>
            • 区域链式: <code>header >> get_by_text=设置</code>
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

/** 绝对 XPath 必须以 xpath= 交给 Playwright，否则会当 CSS 解析报 Unexpected token "/" */
function ensureLocatorEngine(value) {
  const v = String(value || '').trim()
  if (!v) return v
  if (v.startsWith('xpath=') || v.startsWith('css=') || v.startsWith('text=')) return v
  if (v.startsWith('/') && !v.startsWith('//')) return `xpath=${v}`
  return v
}

const inputValue = ref(ensureLocatorEngine(props.modelValue || ''))

watch(
  () => props.modelValue,
  (val) => {
    const next = ensureLocatorEngine(val || '')
    if (next !== inputValue.value) {
      inputValue.value = next
    }
    if (next !== (val || '')) {
      emit('update:modelValue', next)
    }
  }
)

function commitValue() {
  const next = ensureLocatorEngine(inputValue.value || '')
  inputValue.value = next
  emit('update:modelValue', next)
}

function handleSelect(item) {
  const next = ensureLocatorEngine(item.value)
  inputValue.value = next
  emit('update:modelValue', next)
}

watch(inputValue, (val) => {
  // 输入过程不强制改写，失焦/选择时再加 xpath=
  emit('update:modelValue', val || '')
})

// 文本含 $ 时 Playwright 的 :has-text() CSS 会解析失败，应只用 get_by_text
function isUnsafeHasText(text) {
  return /[$\\]/.test(text || '')
}

// 常见短词：在页面上极易重复出现，不适合单独用 get_by_text 定位
const COMMON_SHORT_TEXTS = new Set([
  '登入', '登录', '确定', '取消', '提交', '保存', '新增', '删除', '编辑',
  '搜索', '查询', '重置', '下一步', '上一步', '完成', '关闭', '返回',
  '更多', '展开', '收起', '详情', '操作', '管理', '设置', '首页', '退出',
  '导入', '导出', '下载', '上传', '预览', '复制', '粘贴', '全选', '清空',
  '运行', '报告', '查看', '启用', '禁用', '刷新', '同步', '发布',
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

function labelForCandidate(cand) {
  const raw = cand
  cand = ensureLocatorEngine(cand)
  if (cand.startsWith('[data-testid=')) return `testid 定位: ${cand}`
  if (cand.startsWith('#')) return `ID 定位: ${cand}`
  if (cand.includes('el-select-dropdown__item') || cand.includes('ui-env-option') || cand.includes('ant-select-item')) {
    return `下拉选项: ${cand}`
  }
  if (cand.includes('el-table') || cand.includes('ant-table') || cand.includes('//tbody/tr[')) {
    return `表格定位: ${cand}`
  }
  if ((cand.includes('nth-of-type(') || cand.includes(' > ')) && (cand.includes('.el-') || cand.includes('.ant-') || cand.includes('.ui-'))) {
    return `组件路径: ${cand}`
  }
  if (cand.includes('nth-of-type(') && cand.includes(' > ')) return `结构路径: ${cand}`
  if (cand.startsWith('xpath=/html') || cand.startsWith('/html')) return `绝对 XPath: ${cand}`
  if (cand.startsWith('get_by_role=')) return `角色定位: ${cand}`
  if (cand.startsWith('get_by_text=')) return `文本定位: ${cand}`
  if (cand.startsWith('get_by_label=')) return `标签定位: ${cand}`
  if (cand.startsWith('get_by_placeholder=')) return `placeholder 定位: ${cand}`
  if (cand.startsWith('//') || cand.startsWith('(//')) return `XPath: ${cand}`
  if (cand.includes('.')) return `class 定位: ${raw}`
  return `定位: ${cand}`
}

function buildMetaFallbackOptions(m) {
  const opts = []
  const tag = (m.tag || '').toLowerCase()
  const text = (m.accessibleName || m.text || '').trim()
  const region = (m.region || '').trim()
  const popupRoot = (m.popupRoot || '').trim()
  const matchIndex = Number(m.matchIndex) || 0
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
  if (role && text && text.length < 30 && !/^\d+$/.test(text)) {
    const roleLabel = isCommonShortText ? `角色定位(常见词慎用): get_by_role=${role}, ${text}` : `角色定位: get_by_role=${role}, ${text}`
    opts.push({ label: roleLabel, value: `get_by_role=${role}, ${text}` })
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
    opts.push({ label: `get_by_placeholder: get_by_placeholder=${placeholder}`, value: `get_by_placeholder=${placeholder}` })
  }
  if (title) {
    const prefix = tag || '*'
    opts.push({ label: `title 定位: ${prefix}[title="${title}"]`, value: `${prefix}[title="${title}"]` })
  }
  if (text && text.length < 30 && !/^\d+$/.test(text)) {
    const textLabel = isCommonShortText ? `文本定位(常见词慎用): get_by_text=${text}` : `文本定位: get_by_text=${text}`
    opts.push({ label: textLabel, value: `get_by_text=${text}` })
  }
  if (popupRoot && text && text.length < 40) {
    opts.push({ label: `弹窗内定位: ${popupRoot} >> get_by_text=${text}`, value: `${popupRoot} >> get_by_text=${text}` })
    if (role) {
      opts.push({ label: `弹窗内角色: ${popupRoot} >> get_by_role=${role}, ${text}`, value: `${popupRoot} >> get_by_role=${role}, ${text}` })
    }
  }
  const rowContext = (m.rowContext || '').trim()
  if (rowContext && rowContext.length >= 2) {
    const rowKey = rowContext.slice(0, 48).replace(/'/g, '')
    const inputType = (m.inputType || '').toLowerCase()
    if (inputType === 'checkbox' || role === 'checkbox') {
      opts.push({
        label: `表格行复选框: //tr[contains(.,"${rowKey}")]//input[@type="checkbox"]`,
        value: `//tr[contains(.,"${rowKey}")]//input[@type="checkbox"]`,
      })
    }
    if (text && text.length < 40) {
      const t = text.slice(0, 32).replace(/"/g, '')
      if (role === 'button' || tag === 'button') {
        opts.push({
          label: `表格行按钮: //tr[contains(.,"${rowKey}")]//button[normalize-space()="${t}"]`,
          value: `//tr[contains(.,"${rowKey}")]//button[normalize-space()="${t}"]`,
        })
      }
      opts.push({
        label: `表格行精确文本: //tr[contains(.,"${rowKey}")]//*[normalize-space()="${t}"]`,
        value: `//tr[contains(.,"${rowKey}")]//*[normalize-space()="${t}"]`,
      })
    }
  }
  if (tag && text) {
    const classPart = cls ? `[@class='${cls.split(/\s+/)[0]}']` : ''
    opts.push({
      label: `XPath: //${tag}${classPart}[contains(.,"${text}")]`,
      value: `//${tag}${classPart}[contains(.,"${text}")]`
    })
  }
  if (region && text) {
    opts.push({ label: `区域+文本: ${region} >> get_by_text=${text}`, value: `${region} >> get_by_text=${text}` })
    if (role) {
      opts.push({ label: `区域+角色: ${region} >> get_by_role=${role}, ${text}`, value: `${region} >> get_by_role=${role}, ${text}` })
    }
    if (!isUnsafeHasText(text)) {
      opts.push({ label: `区域+has-text: ${region} ${tag}:has-text("${text}")`, value: `${region} ${tag}:has-text("${text}")` })
    }
  }
  if (matchIndex > 1 && text) {
    opts.push({
      label: `提示: 页面上第 ${matchIndex} 个「${text}」，可设 params.index=${matchIndex}`,
      value: `get_by_text=${text}`
    })
  }
  const structurePath = (m.structurePath || '').trim()
  const cssPath = (m.cssPath || '').trim()
  if (cssPath) {
    opts.push({ label: `组件路径: ${cssPath}`, value: cssPath })
  }
  if (structurePath && structurePath !== cssPath) {
    opts.push({ label: `结构路径: ${structurePath}`, value: structurePath })
  }
  const tableXPath = (m.tableXPath || '').trim()
  if (tableXPath) {
    opts.push({ label: `表格定位: ${tableXPath}`, value: tableXPath })
  }
  const dropdownXPath = (m.dropdownXPath || '').trim()
  if (dropdownXPath) {
    opts.push({ label: `下拉选项: ${dropdownXPath}`, value: dropdownXPath })
  }
  const absoluteXPath = (m.absoluteXPath || '').trim()
  if (absoluteXPath) {
    const absVal = ensureLocatorEngine(absoluteXPath)
    opts.push({ label: `绝对 XPath: ${absVal}`, value: absVal })
  }
  return opts
}

const candidateOptions = computed(() => {
  const m = props.meta || {}
  const seen = new Set()
  const opts = []

  const pushOpt = (label, value) => {
    const normalized = ensureLocatorEngine(value)
    if (!normalized || seen.has(normalized)) return
    seen.add(normalized)
    opts.push({ label: label || labelForCandidate(normalized), value: normalized })
  }

  ;(m.candidates || []).forEach((cand) => {
    pushOpt(labelForCandidate(cand), cand)
  })

  buildMetaFallbackOptions(m).forEach((opt) => {
    pushOpt(opt.label, opt.value)
  })

  if (opts.length === 0) {
    return DEFAULT_TEMPLATES
  }
  return opts
})

function fetchSuggestions(queryString, cb) {
  const q = (queryString || '').toLowerCase().trim()
  const model = (props.modelValue || '').toLowerCase().trim()
  // 聚焦已有 locator 时展示全部候选；仅当用户主动改字搜索时才过滤
  const showAll = !q || q === model
  const list = candidateOptions.value
    .filter(opt => showAll || opt.label.toLowerCase().includes(q) || opt.value.toLowerCase().includes(q))
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
