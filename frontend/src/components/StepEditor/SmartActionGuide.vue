<template>
  <div class="smart-action-guide" :class="{ 'is-fill': isFill }">
    <div class="smart-action-guide__head">
      <div class="smart-action-guide__badge">{{ isFill ? '智能输入' : '智能点击' }}</div>
      <p class="smart-action-guide__summary">
        {{ isFill
          ? '先消歧再输入：同页多字段同名时，靠「区域」锁定表单，避免填错框。'
          : '先消歧再点击：同页多个相同按钮时，靠「区域 + 后置」锁定目标，避免点错。' }}
      </p>
    </div>

    <el-collapse v-model="openPanels" class="smart-action-guide__collapse">
      <el-collapse-item name="usage">
        <template #title>
          <span>完整用法</span>
          <span class="smart-action-guide__panel-hint">怎么填、注意点</span>
        </template>
        <ol class="smart-action-guide__list">
          <li v-for="(line, i) in usageLines" :key="i">{{ line }}</li>
        </ol>
        <ul class="smart-action-guide__bullets">
          <li v-for="(line, i) in cautionLines" :key="'c' + i">{{ line }}</li>
        </ul>
      </el-collapse-item>

      <el-collapse-item name="example">
        <template #title>
          <span>填写示例</span>
          <span class="smart-action-guide__panel-hint">可对照抄</span>
        </template>
        <div class="smart-action-guide__example">
          <div class="smart-action-guide__example-scene">
            <span class="label">场景</span>
            <span>{{ example.scene }}</span>
          </div>
          <div
            v-for="(row, i) in example.fields"
            :key="i"
            class="smart-action-guide__example-row"
          >
            <span class="label">{{ row.label }}</span>
            <code>{{ row.value }}</code>
          </div>
          <p v-if="example.note" class="smart-action-guide__example-note">{{ example.note }}</p>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  method: {
    type: String,
    default: 'smart_click',
  },
})

/** 默认全部收起，需要时再展开 */
const openPanels = ref([])

const isFill = computed(() => props.method === 'smart_fill')

const usageLines = computed(() => {
  if (isFill.value) {
    return [
      '必填「要点谁」与「本步要做什么」；「输入内容」填要写入的值。',
      '同页多个相同 label（如两个「名称」）时，用「在哪个区域」缩小范围，例如「创建弹窗」「筛选区」。',
      '「候选定位」可选：有录制/拾取结果可粘贴；没有也能靠文案 + 区域消歧。',
      '「控件类型」可选，常见填 textbox，帮助组成更稳的候选。',
      '「填完后应看到」可不填：执行侧默认校验输入框的值等于本次输入内容。',
    ]
  }
  return [
    '必填「要点谁」与「本步要做什么」，写清要点哪个按钮（如「新增」「确定」）。',
    '同页多处相同文案时，务必填「在哪个区域」，例如「顶部工具栏」「确认删除弹窗」。',
    '「候选定位」可选；有录制定位或 AI 自愈结果可填，作为消歧起点之一。',
    '「控件类型」可选（如 button），与目标文案组成更稳的候选。',
    '「点完后应看到」：点完期望出现/消失的内容。删除、提交、发布等危险操作必须配置。',
  ]
})

const cautionLines = computed(() => [
  '与普通点击/输入不同：多个候选时会打分，分差不够会直接失败，不会默认点第一个。',
  '本步成功点中后若后置校验失败：只失败本步，不会换第二候选，也不会走定位器自愈（Heal）。',
  '可从普通「元素点击 / 元素输入」一键转为智能步骤，保留原 locator 与录制候选。',
])

const example = computed(() => {
  if (isFill.value) {
    return {
      scene: '创建用户弹窗里有「用户名」输入框，页面其它区域也有同名筛选框',
      fields: [
        { label: '要点谁', value: '用户名' },
        { label: '本步要做', value: '在创建用户弹窗中填写登录名' },
        { label: '输入内容', value: 'demo_user' },
        { label: '区域', value: '创建用户弹窗' },
        { label: '控件类型', value: 'textbox' },
        { label: '填完后', value: '可不填（默认校验输入值）' },
      ],
      note: '若仍歧义，可再补「候选定位」指向弹窗内 input。',
    }
  }
  return {
    scene: '列表页顶部有「新增」，行内操作列也有「新增」子项',
    fields: [
      { label: '要点谁', value: '新增' },
      { label: '本步要做', value: '点击顶部工具栏新增，打开创建弹窗' },
      { label: '区域', value: '顶部工具栏' },
      { label: '控件类型', value: 'button' },
      { label: '点完后', value: '类型=文本可见，文本=创建（或「新建」）' },
    ],
    note: '危险操作示例：目标「删除」+ 区域「确认弹窗」+ 后置「文本可见：删除成功」。',
  }
})
</script>

<style scoped lang="scss">
.smart-action-guide {
  margin: 0 0 14px;
  padding: 12px 14px 6px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: linear-gradient(180deg, var(--el-fill-color-blank) 0%, var(--el-fill-color-extra-light) 100%);
}

.smart-action-guide__head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 4px;
}

.smart-action-guide__badge {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 20px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.smart-action-guide.is-fill .smart-action-guide__badge {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.smart-action-guide__summary {
  margin: 0;
  flex: 1;
  font-size: 13px;
  line-height: 1.55;
  color: var(--el-text-color-regular);
}

.smart-action-guide__collapse {
  border: none;
  --el-collapse-header-height: 36px;
  --el-collapse-header-bg-color: transparent;
  --el-collapse-content-bg-color: transparent;

  :deep(.el-collapse-item__header) {
    padding: 0 2px;
    font-size: 13px;
    font-weight: 500;
    color: var(--el-color-primary);
    border-bottom: none;
  }

  :deep(.el-collapse-item__wrap) {
    border-bottom: none;
  }

  :deep(.el-collapse-item__content) {
    padding: 0 2px 10px;
  }

  :deep(.el-collapse-item + .el-collapse-item) {
    border-top: 1px dashed var(--el-border-color-lighter);
  }
}

.smart-action-guide__panel-hint {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

.smart-action-guide__list {
  margin: 0 0 8px;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--el-text-color-regular);

  li + li {
    margin-top: 4px;
  }
}

.smart-action-guide__bullets {
  margin: 0;
  padding: 8px 10px 8px 26px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);

  li + li {
    margin-top: 4px;
  }
}

.smart-action-guide__example {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  border: 1px dashed var(--el-border-color);
}

.smart-action-guide__example-scene,
.smart-action-guide__example-row {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 8px;
  align-items: start;
  font-size: 12px;
  line-height: 1.5;
}

.smart-action-guide__example .label {
  color: var(--el-text-color-secondary);
}

.smart-action-guide__example-scene span:last-child {
  color: var(--el-text-color-primary);
  font-weight: 500;
}

.smart-action-guide__example-row code {
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
  font-size: 12px;
  word-break: break-all;
  white-space: pre-wrap;
}

.smart-action-guide__example-note {
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}
</style>
