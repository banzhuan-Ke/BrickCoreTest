<template>
  <div ref="containerRef" class="monaco-editor-host" :style="hostStyle" />
</template>

<script setup>
import { onMounted, onBeforeUnmount, watch, ref, shallowRef, inject, computed } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  language: { type: String, default: 'sql' },
  height: { type: String, default: '160px' },
  readOnly: { type: Boolean, default: false },
  theme: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const isDark = inject('dark-mode', ref(false))
const containerRef = ref(null)
const editor = shallowRef(null)
let monacoApi = null
let resizeObserver = null

const hostStyle = computed(() => ({
  height: props.height,
  minHeight: props.height,
  maxHeight: props.height,
}))

function resolveTheme() {
  if (props.theme) return props.theme
  return isDark.value ? 'vs-dark' : 'vs'
}

async function initEditor() {
  if (!containerRef.value || editor.value) return
  const { loadMonaco } = await import('@/utils/monacoLoader.js')
  monacoApi = await loadMonaco()
  const instance = monacoApi.editor.create(containerRef.value, {
    value: props.modelValue || '',
    language: props.language,
    theme: resolveTheme(),
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    automaticLayout: false,
    readOnly: props.readOnly,
    fontSize: 13,
    lineNumbers: 'on',
    wordWrap: 'on',
    tabSize: 2,
  })
  instance.onDidChangeModelContent(() => {
    emit('update:modelValue', instance.getValue())
  })
  editor.value = instance
  instance.layout()
  if (typeof ResizeObserver !== 'undefined' && containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      editor.value?.layout()
    })
    resizeObserver.observe(containerRef.value)
  }
}

onMounted(() => {
  initEditor()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  editor.value?.dispose()
  editor.value = null
})

watch(() => props.modelValue, (val) => {
  const inst = editor.value
  if (!inst) return
  if (inst.getValue() !== (val || '')) {
    inst.setValue(val || '')
  }
})

watch(() => props.language, (lang) => {
  if (!editor.value || !monacoApi) return
  const model = editor.value.getModel()
  if (model) monacoApi.editor.setModelLanguage(model, lang)
})

watch(() => props.readOnly, (ro) => {
  editor.value?.updateOptions({ readOnly: ro })
})

watch([() => props.theme, isDark], () => {
  if (editor.value && monacoApi) {
    monacoApi.editor.setTheme(resolveTheme())
  }
})

watch(() => props.height, () => {
  editor.value?.layout()
})
</script>

<style scoped>
.monaco-editor-host {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  position: relative;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 1;
  box-sizing: border-box;
}
.monaco-editor-host :deep(.monaco-editor),
.monaco-editor-host :deep(.monaco-editor .overflow-guard) {
  position: absolute !important;
  inset: 0;
}
</style>
