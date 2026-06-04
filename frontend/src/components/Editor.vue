<template>
  <div style="width: 100%">
    <VAceEditor :options="editOption" v-model:value="dataEdit" :lang="lang" :theme="activeTheme"
                :style="{ minHeight: height }"/>
    <el-button plain type="primary" size="small" @click="formatJson">
      JSON格式化
    </el-button>
  </div>
</template>

<script setup>
import {computed, onMounted, ref, watch, inject, nextTick} from 'vue'
import {VAceEditor} from 'vue3-ace-editor'
import ace from 'ace-builds'
import {ElMessage} from 'element-plus'
import modeJsonUrl from 'ace-builds/src-noconflict/mode-json?url'
import themeChromeUrl from 'ace-builds/src-noconflict/theme-chrome?url'
import extSearchboxUrl from 'ace-builds/src-noconflict/ext-searchbox?url'
import workerJsonUrl from 'ace-builds/src-noconflict/worker-json?url'
import 'ace-builds/src-noconflict/mode-json'
import 'ace-builds/src-noconflict/mode-html'
import 'ace-builds/src-noconflict/mode-python'
import 'ace-builds/src-noconflict/ext-language_tools'
import 'ace-builds/src-noconflict/snippets/json'
import 'ace-builds/src-noconflict/snippets/python'
import 'ace-builds/src-noconflict/snippets/html'
import 'ace-builds/src-noconflict/theme-merbivore'
import 'ace-builds/src-noconflict/theme-monokai'
import 'ace-builds/src-noconflict/theme-chrome'
import 'ace-builds/src-noconflict/worker-json'
import 'ace-builds/src-noconflict/worker-html'

ace.config.setModuleUrl('ace/mode/json', modeJsonUrl)
ace.config.setModuleUrl('ace/theme/chrome', themeChromeUrl)
ace.config.setModuleUrl('ace/ext/searchbox', extSearchboxUrl)
ace.config.setModuleUrl('ace/mode/json_worker', workerJsonUrl)

// 注入暗黑模式状态
const isDark = inject('dark-mode', ref(false))
const activeTheme = ref(isDark.value ? 'merbivore' : 'chrome')

const props = defineProps({
  // 语言
  lang: {
    type: String,
    default: 'json'
  },
  // 值
  modelValue: {
    type: [String, Object],
    default: () => '{}'
  },
  // 主题
  theme: {
    type: String,
    default: 'chrome'
  },
  // 高度
  height: {
    type: String,
    default: '200px'
  },
  // 是否只读
  readOnly: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue'])

const dataEdit = computed({
  get() {
    try {
      if (props.lang !== 'json')
        return props.modelValue
      return typeof props.modelValue === 'object'
          ? JSON.stringify(props.modelValue, null, 4)
          : props.modelValue || '{}'
    } catch (e) {
      return ''
    }
  },
  set(value) {
    if (props.lang !== 'json') {
      emit('update:modelValue', value || '')
    } else {
      try {
        const parsedValue = JSON.parse(value)
        emit('update:modelValue', parsedValue)
      } catch (e) {
        emit('update:modelValue', value || '{}')
      }
    }
  }
})

// Ace Editor配置项
const editOption = computed(() => ({
      enableBasicAutocompletion: true,
      enableLiveAutocompletion: true,
      enableSnippets: true,
      tabSize: 4,
      fontSize: 14,
      useWorker: true,
      showPrintMargin: false,
      enableMultiselect: true,
      readOnly: props.readOnly,
      showFoldWidgets: true,
      fadeFoldWidgets: true,
      wrap: true,
      minLines: 10,
      maxLines: Infinity
    })
)

// 格式化Json
function formatJson() {
  if (props.lang === 'json') {
    try {
      const jsObj = JSON.parse(dataEdit.value)
      dataEdit.value = JSON.stringify(jsObj, null, 4)
      ElMessage({
        message: 'JSON数据格式完成！',
        type: 'success',
        duration: 1500,
      })
    } catch (e) {
      ElMessage({
        message: 'JSON数据格式错误！',
        type: 'error',
        duration: 1500,
      })
    }
  }
}

// 生命周期函数
onMounted(() => {
  ace.config.set('basePath', '/node_modules/ace-builds/src-noconflict')
})

// 监听暗黑模式变化
watch(isDark, (newVal) => {
  activeTheme.value = newVal ? 'merbivore' : 'chrome'
  nextTick(() => { // 等待DOM更新
    const editor = ace.edit(document.querySelector('.ace_editor'))
    editor?.setTheme(`ace/theme/${activeTheme.value}`)
  })
})
</script>

<style scoped>
</style>
