<template>
  <el-collapse v-model="expanded" class="app-h5-usage-guide">
    <el-collapse-item :name="collapseName">
      <template #title>
        <span class="guide-collapse-title">
          <el-icon><InfoFilled /></el-icon>
          {{ title }}
        </span>
      </template>
      <div class="guide-body">
        <template v-if="scope === 'step'">
          <p v-if="stepHint" class="guide-paragraph">{{ stepHint }}</p>
        </template>
        <template v-else>
        <!-- 用例编辑：驱动模式说明 -->
        <template v-if="showDriverModes">
          <h4 class="guide-section-title">驱动模式怎么选</h4>
          <ul class="guide-list">
            <li v-for="item in APP_DRIVER_MODE_HINTS" :key="item.value">
              <strong>{{ item.label }}</strong>（<code>{{ item.value }}</code>）— {{ item.desc }}
            </li>
          </ul>
        </template>

        <!-- WebView 示例 -->
        <template v-if="showWebviewExample">
          <h4 class="guide-section-title">示例：App 内 WebView（driver_mode = hybrid_web）</h4>
          <ul class="guide-list compact">
            <li>前置：App 调用 <code>WebView.setWebContentsDebuggingEnabled(true)</code></li>
            <li>步骤：启动 App → 切换 WebView → H5 点击/输入/断言</li>
          </ul>
          <pre class="guide-code">{{ APP_WEBVIEW_EXAMPLE_STEPS }}</pre>
        </template>

        <!-- Chrome 示例 -->
        <template v-if="showChromeExample">
          <h4 class="guide-section-title">示例：手机 Chrome H5（driver_mode = mobile_chrome）</h4>
          <ul class="guide-list compact">
            <li>前置：adb 设备在线（USB / WiFi / 模拟器）；Chrome 中打开目标页（或步骤「打开链接」）</li>
            <li>步骤：打开链接 → 切换 Chrome → H5 操作；勿混用「切换 WebView」</li>
          </ul>
          <pre class="guide-code">{{ APP_CHROME_EXAMPLE_STEPS }}</pre>
        </template>

        <!-- Inspector -->
        <template v-if="showInspector">
          <h4 class="guide-section-title">元素探查操作要点</h4>
          <ol class="guide-ol">
            <li v-for="(line, idx) in APP_INSPECTOR_STEPS" :key="idx">{{ line }}</li>
          </ol>
        </template>

        <!-- 元素库 -->
        <template v-if="showElement">
          <h4 class="guide-section-title">H5 元素库</h4>
          <ul class="guide-list">
            <li v-for="(line, idx) in APP_ELEMENT_H5_NOTES" :key="'h5-' + idx">{{ line }}</li>
          </ul>
          <h4 class="guide-section-title">图像识别元素</h4>
          <ul class="guide-list">
            <li v-for="(line, idx) in APP_ELEMENT_VISION_NOTES" :key="'vis-' + idx">{{ line }}</li>
          </ul>
        </template>

        <!-- 图像示例 -->
        <template v-if="showVisionExample">
          <h4 class="guide-section-title">示例：图像识别（driver_mode = hybrid）</h4>
          <pre class="guide-code">{{ APP_VISION_EXAMPLE_STEPS }}</pre>
        </template>

        <!-- 通用注意 -->
        <template v-if="showCommonNotes">
          <h4 class="guide-section-title">注意事项</h4>
          <ul class="guide-list">
            <li v-for="(line, idx) in APP_H5_COMMON_NOTES" :key="idx">{{ line }}</li>
          </ul>
        </template>
        </template>
      </div>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
import { computed, ref } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import {
  APP_DRIVER_MODE_HINTS,
  APP_H5_COMMON_NOTES,
  APP_WEBVIEW_EXAMPLE_STEPS,
  APP_CHROME_EXAMPLE_STEPS,
  APP_INSPECTOR_STEPS,
  APP_ELEMENT_H5_NOTES,
  APP_ELEMENT_VISION_NOTES,
  APP_VISION_EXAMPLE_STEPS,
  APP_STEP_CONTEXT_HINTS,
} from '@/datas/AppH5Guide.js'

const props = defineProps({
  /** case | inspector | element | step */
  scope: {
    type: String,
    default: 'case',
  },
  /** 用例 driver_mode，用于步骤弹窗高亮 */
  driverMode: {
    type: String,
    default: '',
  },
  /** 当前编辑的步骤 method */
  stepMethod: {
    type: String,
    default: '',
  },
  /** 当前步骤是否含图像定位 */
  hasImageLocator: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: 'H5 / WebView / 手机 Chrome 使用说明与示例',
  },
})

const collapseName = 'guide'
const expanded = ref([])

const showDriverModes = computed(() => props.scope === 'case')
const showWebviewExample = computed(() => ['case', 'inspector'].includes(props.scope))
const showChromeExample = computed(() => ['case', 'inspector'].includes(props.scope))
const showInspector = computed(() => props.scope === 'inspector')
const showElement = computed(() => props.scope === 'element')
const showVisionExample = computed(() => ['case', 'element'].includes(props.scope))
const showCommonNotes = computed(() => ['case', 'inspector', 'element'].includes(props.scope))

const stepHint = computed(() => {
  if (props.scope !== 'step') return ''
  const method = props.stepMethod
  if (method && APP_STEP_CONTEXT_HINTS[method]) {
    return APP_STEP_CONTEXT_HINTS[method]
  }
  if (props.hasH5Locator) {
    return APP_STEP_CONTEXT_HINTS.h5_locator
  }
  if (props.hasImageLocator) {
    return APP_STEP_CONTEXT_HINTS.image_locator
  }
  if (props.driverMode === 'mobile_chrome') {
    return '当前用例为手机 Chrome H5 模式：H5 操作前请确保已执行「打开链接」+「切换 Chrome」。'
  }
  if (props.driverMode === 'hybrid_web') {
    return '当前用例为 App WebView 模式：H5 操作前请确保已执行「切换 WebView」。'
  }
  return ''
})
</script>

<script>
export default {
  name: 'AppH5UsageGuide',
}
</script>

<style scoped lang="scss">
.app-h5-usage-guide {
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
  background: var(--el-fill-color-blank);

  :deep(.el-collapse-item__header) {
    padding: 0 12px;
    height: 40px;
    font-size: 13px;
    background: var(--el-fill-color-light);
  }

  :deep(.el-collapse-item__wrap) {
    border-top: 1px solid var(--el-border-color-lighter);
  }

  :deep(.el-collapse-item__content) {
    padding: 12px 14px 14px;
  }
}

.guide-collapse-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-regular);
  font-weight: 500;
}

.guide-section-title {
  margin: 12px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);

  &:first-child {
    margin-top: 0;
  }
}

.guide-list {
  margin: 0;
  padding-left: 1.2em;
  font-size: 13px;
  line-height: 1.55;
  color: var(--el-text-color-regular);

  &.compact {
    margin-bottom: 8px;
  }

  li + li {
    margin-top: 4px;
  }

  code {
    font-size: 12px;
  }
}

.guide-ol {
  margin: 0;
  padding-left: 1.3em;
  font-size: 13px;
  line-height: 1.55;
  color: var(--el-text-color-regular);

  li + li {
    margin-top: 4px;
  }
}

.guide-paragraph {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--el-text-color-regular);
}

.guide-code {
  margin: 0;
  padding: 10px 12px;
  font-size: 11px;
  line-height: 1.45;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  overflow: auto;
  max-height: 200px;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--el-text-color-primary);
}
</style>
