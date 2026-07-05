<template>
  <PageCard class="app-inspector-page">
    <template #title><span>元素探查</span></template>
    <template #main>
      <el-form inline class="toolbar">
        <el-form-item label="执行设备" required>
          <el-select v-model="deviceId" placeholder="在线 App Runner" filterable style="width: 260px" :disabled="!!sessionId">
            <el-option
              v-for="d in appDevices"
              :key="d.id"
              :label="`${d.name || d.username} (${d.app_udid || d.id})`"
              :value="d.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="UDID">
          <el-input v-model="appUdid" placeholder="留空用设备登记值" style="width: 200px" :disabled="!!sessionId" />
        </el-form-item>
        <el-form-item>
          <el-button v-if="!sessionId" type="primary" :loading="connecting" @click="connectSession">连接</el-button>
          <el-button v-else type="warning" plain @click="disconnectSession">断开</el-button>
          <el-button type="success" :loading="dumping" :disabled="!sessionId" @click="refreshDump">刷新控件树</el-button>
        </el-form-item>
        <el-form-item v-if="sessionId" label="实时投屏">
          <el-switch v-model="liveMirror" active-text="开" inactive-text="关" @change="onLiveMirrorChange" />
        </el-form-item>
      </el-form>

      <AppH5UsageGuide scope="inspector" title="元素探查与 H5 探测说明（含示例）" />

      <el-alert
        v-if="inspectorContext && inspectorHasStepTarget"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #title>
          正在为用例{{ inspectorStepLabel }} 选择元素；选定后点击「回填到用例步骤」
          <el-button link type="primary" size="small" style="margin-left: 8px" @click="cancelInspectorReturn">取消返回</el-button>
        </template>
      </el-alert>

      <el-alert v-if="sessionMeta.package" type="info" :closable="false" show-icon style="margin-bottom: 12px">
        <template #title>
          当前应用：{{ sessionMeta.package }}
          <span v-if="sessionMeta.activity"> / {{ sessionMeta.activity }}</span>
        </template>
      </el-alert>

      <el-alert
        v-if="sessionId && (hasWebViewLayer || chromeContexts.length)"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #title>检测到 H5 页面（App WebView 或 Chrome）</template>
        <div class="webview-hint-body">
          <div class="devtools-source-row">
            <span class="ctx-label">H5 来源：</span>
            <el-radio-group v-model="devtoolsSource" size="small">
              <el-radio-button value="webview">App WebView</el-radio-button>
              <el-radio-button value="chrome">手机 Chrome</el-radio-button>
            </el-radio-group>
          </div>
          <p v-if="activeH5Hint">{{ activeH5Hint }}</p>
          <p v-else-if="devtoolsSource === 'chrome'">
            请先在手机 Chrome 中打开目标 H5（可用步骤「打开链接」），再探测 DOM。
          </p>
          <p v-else>原生控件树只能看到 WebView 容器。请切换到「H5 DOM」标签并探测内部元素。</p>
          <div v-if="activeH5Contexts.length" class="webview-context-row">
            <span class="ctx-label">可调试页面：</span>
            <el-select v-model="webviewPageIndex" size="small" style="width: min(420px, 100%)">
              <el-option
                v-for="(ctx, idx) in activeH5Contexts"
                :key="idx"
                :label="formatWebContextLabel(ctx, idx)"
                :value="idx"
              />
            </el-select>
            <el-button
              type="primary"
              size="small"
              :loading="webviewProbing"
              :disabled="!sessionId"
              @click="probeWebviewDom"
            >
              探测 H5 DOM
            </el-button>
          </div>
          <el-button
            v-else
            type="primary"
            size="small"
            plain
            :loading="webviewProbing"
            @click="probeWebviewDom"
          >
            尝试探测 H5 DOM
          </el-button>
        </div>
      </el-alert>

      <el-alert
        v-if="sessionId && webviewError && treeTab === 'h5'"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        :title="webviewError"
      />

      <div v-if="!sessionId" class="empty-hint">
        <p>请选择在线 App Runner（本机 adb 已连接真机 / WiFi / 模拟器），在设备上打开要分析的页面，点击「刷新控件树」。</p>
      </div>

      <div v-else ref="layoutRef" class="inspector-layout" :style="layoutGridStyle">
        <div class="tree-panel inspector-col">
          <el-tabs v-model="treeTab" class="tree-tabs">
            <el-tab-pane label="原生控件" name="native">
              <div class="col-body tree-col-body">
                <el-tree
                  v-if="treeData.length"
                  ref="treeRef"
                  class="inspector-tree"
                  :data="treeData"
                  node-key="index"
                  :current-node-key="selectedNode?.index"
                  :props="{ label: 'label', children: 'children' }"
                  highlight-current
                  default-expand-all
                  @node-click="onNodeClick"
                />
                <el-empty v-else description="点击「刷新控件树」获取界面结构" />
              </div>
            </el-tab-pane>
            <el-tab-pane label="H5 DOM" name="h5">
              <div class="col-body tree-col-body">
                <div v-if="webviewProbing" class="h5-loading">
                  <el-icon class="is-loading"><Loading /></el-icon>
                  正在抓取 H5 DOM…
                </div>
                <el-tree
                  v-else-if="webTreeData.length"
                  ref="webTreeRef"
                  class="inspector-tree"
                  :data="webTreeData"
                  node-key="index"
                  :current-node-key="selectedWebNode?.index"
                  :props="{ label: 'label', children: 'children' }"
                  highlight-current
                  default-expand-all
                  @node-click="onWebNodeClick"
                />
                <el-empty v-else description="请先刷新控件树，再点击「探测 H5 DOM」" />
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>

        <div
          class="col-splitter"
          title="拖动调整控件树宽度"
          @mousedown="onSplitterMouseDown('left', $event)"
        />

        <div class="screenshot-panel inspector-col">
          <div class="panel-title row-between">
            <span>
              截图
              <span class="panel-hint">（{{ screenshotModeHint }}）</span>
            </span>
            <el-radio-group v-model="screenshotMode" size="small" @change="onScreenshotModeChange">
              <el-radio-button value="pick">点选</el-radio-button>
              <el-radio-button value="crop">框选</el-radio-button>
              <el-radio-button value="explore">探索</el-radio-button>
            </el-radio-group>
          </div>
          <div v-if="screenshotMode === 'explore' && canEdit" class="explore-toolbar">
            <el-button size="small" :loading="exploring" @click="exploreBack">返回</el-button>
            <el-button size="small" :loading="exploring" @click="exploreHome">主页</el-button>
            <el-button size="small" :loading="exploring" @click="exploreInput">输入</el-button>
            <el-button size="small" :loading="dumping" @click="manualRefreshTree">刷新控件树</el-button>
            <el-button size="small" :loading="mirrorBusy" @click="manualRefreshScreenshot">刷新截图</el-button>
            <el-checkbox v-model="exploreRefreshTree" size="small">点击后刷新控件树</el-checkbox>
          </div>
          <p v-if="screenshotMode === 'explore'" class="explore-hint">
            弹窗/中间态时优先点「刷新截图」；需要重新抓树或断言时再点「刷新控件树」。
          </p>
          <div class="screenshot-wrap">
            <div
              v-if="screenshotUrl"
              ref="screenshotStageRef"
              class="screenshot-stage"
              :class="{ 'is-crop-mode': screenshotMode === 'crop' }"
              :title="screenshotMode === 'crop' ? '拖选截图区域' : screenshotMode === 'explore' ? '点击截图试操作设备' : '点击截图上的控件进行定位'"
              @mousedown="onScreenshotMouseDown"
              @click="onScreenshotClick"
            >
              <img
                ref="screenshotImgRef"
                :src="screenshotUrl"
                alt="screenshot"
                class="screenshot"
                draggable="false"
                @load="updateImageLayout"
                @error="onScreenshotError"
              />
              <div v-if="highlightStyle && screenshotMode === 'pick'" class="node-highlight" :style="highlightStyle" />
              <div v-if="cropHighlightStyle" class="crop-highlight" :style="cropHighlightStyle" />
            </div>
            <el-empty v-else description="暂无截图" />
          </div>
        </div>

        <div
          class="col-splitter"
          title="拖动调整详情区宽度"
          @mousedown="onSplitterMouseDown('right', $event)"
        />

        <div class="props-panel inspector-col">
          <div v-if="treeTab === 'h5' && selectedWebNode" class="node-detail">
            <div class="panel-title row-between">
              <span>选中 H5 元素</span>
            </div>
            <table class="attr-table">
              <thead>
                <tr>
                  <th class="attr-col-name">Attr</th>
                  <th class="attr-col-value">Value</th>
                  <th class="attr-col-action" />
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in webPrimaryAttributes" :key="row.key">
                  <td class="attr-name">{{ row.label }}</td>
                  <td class="attr-value">{{ row.value }}</td>
                  <td class="attr-action">
                    <el-button
                      v-if="row.copyable"
                      link
                      type="primary"
                      size="small"
                      @click="copyText(row.value, row.label)"
                    >
                      复制
                    </el-button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div class="code-section">
              <div class="code-section-head">
                <span class="suggest-title">推荐定位器（WebView）</span>
                <el-button link type="primary" size="small" :disabled="!suggestedWebLocator" @click="copyWebLocator">
                  复制
                </el-button>
              </div>
              <code class="locator-code">{{ suggestWebText }}</code>
              <el-button
                v-if="inspectorContext && inspectorHasStepTarget"
                type="primary"
                size="small"
                style="margin-top: 8px"
                :disabled="!suggestedWebLocator"
                @click="applyLocatorToStep"
              >
                回填到用例{{ inspectorStepLabel }}
              </el-button>
            </div>
            <div v-if="webPlaywrightHint" class="code-section">
              <div class="code-section-head">
                <span class="suggest-title">Playwright 片段（Phase 2 执行参考）</span>
                <el-button link type="primary" size="small" @click="copyText(webPlaywrightHint, 'Playwright 片段')">复制</el-button>
              </div>
              <code class="locator-code">{{ webPlaywrightHint }}</code>
            </div>
            <el-divider />
            <el-form label-width="72px" size="small" class="save-form">
              <el-form-item label="元素名" required>
                <el-input v-model="saveForm.name" placeholder="保存到元素库的名称" />
              </el-form-item>
              <el-form-item>
                <el-button v-if="canEdit" type="primary" :loading="saving" :disabled="!canSaveWeb" @click="saveWebToLibrary">
                  保存 H5 元素
                </el-button>
              </el-form-item>
            </el-form>
          </div>
          <div v-else-if="treeTab === 'native' && selectedNode" class="node-detail">
            <div class="panel-title row-between">
              <span>选中元素</span>
              <el-button v-if="canSelectParent" size="small" link type="primary" @click="selectParentNode">
                上一级控件
              </el-button>
            </div>
            <div v-if="nodeCandidates.length > 1" class="overlap-candidates">
              <div class="suggest-title">重叠控件（点击切换）</div>
              <div class="candidate-chips">
                <el-tag
                  v-for="n in nodeCandidates"
                  :key="n.index"
                  :type="selectedNode?.index === n.index ? 'primary' : 'info'"
                  effect="plain"
                  class="candidate-tag"
                  @click="selectNode(n)"
                >
                  {{ formatCandidateLabel(n) }}
                </el-tag>
              </div>
            </div>
            <table class="attr-table">
              <thead>
                <tr>
                  <th class="attr-col-name">Attr</th>
                  <th class="attr-col-value">Value</th>
                  <th class="attr-col-action" />
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in primaryAttributes" :key="row.key">
                  <td class="attr-name">{{ row.label }}</td>
                  <td class="attr-value">{{ row.value }}</td>
                  <td class="attr-action">
                    <el-button
                      v-if="row.copyable"
                      link
                      type="primary"
                      size="small"
                      @click="copyText(row.value, row.label)"
                    >
                      复制
                    </el-button>
                  </td>
                </tr>
              </tbody>
            </table>

            <el-collapse v-if="extraAttributes.length" class="extra-attrs">
              <el-collapse-item title="更多属性" name="extra">
                <table class="attr-table attr-table-compact">
                  <tbody>
                    <tr v-for="row in extraAttributes" :key="row.key">
                      <td class="attr-name">{{ row.label }}</td>
                      <td class="attr-value">{{ row.value }}</td>
                    </tr>
                  </tbody>
                </table>
              </el-collapse-item>
            </el-collapse>

            <div class="code-section">
              <div class="code-section-head">
                <span class="suggest-title">推荐定位器</span>
                <el-button link type="primary" size="small" :disabled="!suggestedLocator" @click="copyLocator">
                  复制
                </el-button>
              </div>
              <code class="locator-code">{{ suggestText }}</code>
              <el-button
                v-if="inspectorContext && inspectorHasStepTarget"
                type="primary"
                size="small"
                style="margin-top: 8px"
                :disabled="!suggestedLocator"
                @click="applyLocatorToStep"
              >
                回填到用例{{ inspectorStepLabel }}
              </el-button>
            </div>

            <div v-if="xpathText" class="code-section">
              <div class="code-section-head">
                <span class="suggest-title">XPath 备选</span>
                <el-button link type="primary" size="small" @click="copyText(xpathText, 'XPath')">复制</el-button>
              </div>
              <code class="locator-code">{{ xpathText }}</code>
            </div>

            <div v-if="u2Code" class="code-section">
              <div class="code-section-head">
                <span class="suggest-title">u2 代码片段</span>
                <el-button link type="primary" size="small" @click="copyText(u2Code, 'u2 代码')">复制</el-button>
              </div>
              <code class="locator-code">{{ u2Code }}</code>
            </div>

            <div class="ai-suggest-section">
              <div class="suggest-title">AI 辅助</div>
              <el-checkbox v-model="aiUseVision" size="small" :disabled="!sessionId">
                结合当前会话截图（Vision）
              </el-checkbox>
              <el-select
                v-if="aiUseVision"
                v-model="visionConfigId"
                size="small"
                placeholder="Vision 模型"
                filterable
                clearable
                style="width: 100%; margin-top: 8px"
              >
                <el-option
                  v-for="c in visionConfigs"
                  :key="c.id"
                  :label="`${c.name} (${c.model})`"
                  :value="c.id"
                />
              </el-select>
              <div class="ai-suggest-btns">
                <el-button
                  size="small"
                  type="primary"
                  plain
                  :loading="aiSuggesting === 'name'"
                  @click="runAiSuggest('name')"
                >
                  ✨ AI 命名
                </el-button>
                <el-button
                  size="small"
                  type="warning"
                  plain
                  :loading="aiSuggesting === 'steps'"
                  @click="runAiSuggest('steps')"
                >
                  ✨ AI 生成步骤
                </el-button>
              </div>
            </div>

            <el-divider />
            <el-form label-width="72px" size="small" class="save-form">
              <el-form-item label="元素名" required>
                <el-input v-model="saveForm.name" placeholder="保存到元素库的名称" />
              </el-form-item>
              <el-form-item>
                <el-button v-if="canEdit" type="primary" :loading="saving" :disabled="!canSave" @click="saveToLibrary">保存到元素库</el-button>
              </el-form-item>
            </el-form>
          </div>
          <div v-else-if="cropRect" class="node-detail">
            <div class="panel-title">截图裁剪区域</div>
            <p class="crop-meta">选区 {{ cropRect.width }} × {{ cropRect.height }} px（设备坐标）</p>
            <el-form label-width="72px" size="small" class="save-form">
              <el-form-item label="元素名" required>
                <el-input v-model="saveForm.name" placeholder="识别图在元素库中的名称" />
              </el-form-item>
              <el-form-item>
                <el-button v-if="canEdit" type="primary" :loading="saving" :disabled="!canSaveCrop" @click="saveCropToLibrary">
                  保存识别图到元素库
                </el-button>
                <el-button link type="info" @click="clearCropRect">清除选区</el-button>
              </el-form-item>
            </el-form>
          </div>
          <div v-else class="props-empty">
            <el-empty :description="treeTab === 'h5' ? '在 H5 DOM 树中选择元素' : '点击截图或左侧控件树选择元素'" />
          </div>
        </div>
      </div>
    </template>
  </PageCard>

  <el-dialog v-model="aiStepsDialogVisible" title="AI 生成的 App 步骤" width="720px" destroy-on-close>
    <el-alert
      v-if="aiStepsErrors.length"
      type="warning"
      :closable="false"
      show-icon
      :title="`有 ${aiStepsErrors.length} 条校验提示`"
      style="margin-bottom: 12px"
    />
    <div v-for="(step, index) in aiGeneratedSteps" :key="index" class="ai-step-row">
      <div class="ai-step-head">
        <span>#{{ index + 1 }}</span>
        <code>{{ step.keyword }}.{{ step.method }}</code>
        <span v-if="step.desc" class="ai-step-desc">{{ step.desc }}</span>
      </div>
      <pre class="ai-step-params">{{ JSON.stringify(step.params, null, 2) }}</pre>
    </div>
    <template #footer>
      <el-button @click="aiStepsDialogVisible = false">关闭</el-button>
      <el-button @click="copyAiSteps">复制 JSON</el-button>
      <template v-if="inspectorContext?.returnPath && aiGeneratedSteps.length">
        <el-radio-group v-model="aiApplyMode" size="small" style="margin-right: 12px">
          <el-radio value="append">追加</el-radio>
          <el-radio value="replace">替换</el-radio>
        </el-radio-group>
        <el-button type="primary" @click="applyAiStepsToCase">应用到用例</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import PageCard from '@/components/PageCard.vue'
import AppH5UsageGuide from '@/components/App/AppH5UsageGuide.vue'
import { appElementApi, appInspectorApi, deviceApi } from '@/api'
import { aiGenerateApi, aiConfigApi } from '@/api/modules/ai'
import { getApiErrorMessage, isDuplicateElementNameError } from '@/utils/apiError.js'
import {
  buildU2Code,
  formatLocatorJson,
  formatLocatorText,
  getExtraAttributes,
  getPrimaryAttributes,
  suggestLocator,
  suggestXpath,
} from '@/utils/appInspectorLocator.js'
import {
  decorateWebNodes,
  formatWebContextLabel,
  formatWebLocatorJson,
  formatWebLocatorText,
  getWebPrimaryAttributes,
  isWebViewNativeNode,
  suggestWebLocator,
  buildWebPlaywrightHint,
} from '@/utils/appWebviewLocator.js'
import { copyToClipboard } from '@/utils/clipboard.js'
import {
  clearAppInspectorContext,
  clearAppInspectorCaseDraft,
  getAppInspectorContext,
  setAppInspectorResult,
  formatInspectorStepPathLabel,
} from '@/utils/appInspectorContext.js'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()

const canEdit = computed(() => uStore.hasPermission('app_element:edit') || uStore.hasPermission('app_case:edit'))

const devices = ref([])
const deviceId = ref('')
const appUdid = ref('')
const sessionId = ref('')
const connecting = ref(false)
const dumping = ref(false)
const saving = ref(false)
const treeData = ref([])
const screenshotUrl = ref('')
let screenshotObjectUrl = ''
const selectedNode = ref(null)
const screenshotStageRef = ref(null)
const screenshotImgRef = ref(null)
const treeRef = ref(null)
const imageLayout = ref(null)
const screenshotMode = ref('pick')
const exploring = ref(false)
const exploreRefreshTree = ref(false)
const liveMirror = ref(false)
const mirrorBusy = ref(false)
const cropDrag = ref(null)
const cropRect = ref(null)
let cropDidDrag = false
const nodeCandidates = ref([])
const nodeIndexMap = ref({})
const sessionMeta = reactive({ package: '', activity: '' })
const saveForm = reactive({ name: '' })
const aiSuggesting = ref('')
const aiUseVision = ref(false)
const visionConfigId = ref(null)
const aiConfigList = ref([])
const aiStepsDialogVisible = ref(false)
const aiGeneratedSteps = ref([])
const aiStepsErrors = ref([])
const aiApplyMode = ref('append')
const inspectorContext = ref(null)

const inspectorStepLabel = computed(() => {
  const ctx = inspectorContext.value
  if (!ctx) return ''
  if (Array.isArray(ctx.stepPath) && ctx.stepPath.length) {
    return formatInspectorStepPathLabel(ctx.stepPath)
  }
  if (typeof ctx.stepIndex === 'number') {
    return `步骤 ${ctx.stepIndex + 1}`
  }
  return ''
})

const inspectorHasStepTarget = computed(() => {
  const ctx = inspectorContext.value
  if (!ctx) return false
  if (Array.isArray(ctx.stepPath) && ctx.stepPath.length) return true
  return typeof ctx.stepIndex === 'number'
})
const layoutRef = ref(null)
const treeColWidth = ref(280)
const propsColWidth = ref(360)
const treeTab = ref('native')
const webTreeRef = ref(null)
const webviewNodes = ref([])
const webviewContexts = ref([])
const webviewHint = ref('')
const webviewDom = ref(null)
const webviewError = ref('')
const webviewProbing = ref(false)
const webviewPageIndex = ref(0)
const devtoolsSource = ref('webview')
const chromeContexts = ref([])
const chromeHint = ref('')
const selectedWebNode = ref(null)
let webviewPollTimer = null

const COL_MIN_TREE = 180
const COL_MIN_PROPS = 220
const COL_MIN_SCREEN = 240
const COL_SPLITTER = 6
const COL_WIDTH_STORAGE_KEY = 'app_inspector_col_widths'

const POLL_INTERVAL_MS = 1200
const POLL_MAX_ATTEMPTS = 90
const MIRROR_INTERVAL_MS = 2500

let pollTimer = null
let pollAttempts = 0
let explorePollTimer = null
let explorePollAttempts = 0
let mirrorTimer = null
let webviewPollAttempts = 0
let resizeObserver = null
let dragState = null

const layoutGridStyle = computed(() => ({
  gridTemplateColumns: `${treeColWidth.value}px ${COL_SPLITTER}px minmax(${COL_MIN_SCREEN}px, 1fr) ${COL_SPLITTER}px ${propsColWidth.value}px`,
}))

const screenshotModeHint = computed(() => {
  if (screenshotMode.value === 'crop') return '拖选区域保存识别图'
  if (screenshotMode.value === 'explore') return '点击截图试操作设备'
  return '点击定位控件'
})

function loadColWidths() {
  try {
    const raw = localStorage.getItem(COL_WIDTH_STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (parsed.tree > 0) treeColWidth.value = parsed.tree
    if (parsed.props > 0) propsColWidth.value = parsed.props
  } catch {
    /* ignore */
  }
}

function saveColWidths() {
  try {
    localStorage.setItem(
      COL_WIDTH_STORAGE_KEY,
      JSON.stringify({ tree: treeColWidth.value, props: propsColWidth.value })
    )
  } catch {
    /* ignore */
  }
}

function clampColWidths() {
  const layout = layoutRef.value
  if (!layout) return
  const available = layout.clientWidth - COL_SPLITTER * 2
  const maxTree = Math.max(COL_MIN_TREE, available - COL_MIN_PROPS - COL_MIN_SCREEN)
  const maxProps = Math.max(COL_MIN_PROPS, available - COL_MIN_TREE - COL_MIN_SCREEN)
  treeColWidth.value = Math.min(Math.max(treeColWidth.value, COL_MIN_TREE), maxTree)
  propsColWidth.value = Math.min(Math.max(propsColWidth.value, COL_MIN_PROPS), maxProps)
}

function onSplitterMouseMove(e) {
  if (!dragState) return
  const dx = e.clientX - dragState.startX
  const available = dragState.layoutWidth - COL_SPLITTER * 2

  if (dragState.which === 'left') {
    let next = dragState.startTree + dx
    const maxTree = available - COL_MIN_PROPS - COL_MIN_SCREEN
    treeColWidth.value = Math.min(Math.max(next, COL_MIN_TREE), Math.max(COL_MIN_TREE, maxTree))
  } else {
    let next = dragState.startProps - dx
    const maxProps = available - COL_MIN_TREE - COL_MIN_SCREEN
    propsColWidth.value = Math.min(Math.max(next, COL_MIN_PROPS), Math.max(COL_MIN_PROPS, maxProps))
  }
  nextTick(updateImageLayout)
}

function onSplitterMouseUp() {
  if (!dragState) return
  dragState = null
  document.body.classList.remove('inspector-col-resizing')
  document.removeEventListener('mousemove', onSplitterMouseMove)
  document.removeEventListener('mouseup', onSplitterMouseUp)
  saveColWidths()
  updateImageLayout()
}

function onSplitterMouseDown(which, e) {
  e.preventDefault()
  const layout = layoutRef.value
  if (!layout) return
  dragState = {
    which,
    startX: e.clientX,
    startTree: treeColWidth.value,
    startProps: propsColWidth.value,
    layoutWidth: layout.clientWidth,
  }
  document.body.classList.add('inspector-col-resizing')
  document.addEventListener('mousemove', onSplitterMouseMove)
  document.addEventListener('mouseup', onSplitterMouseUp)
}

function bindScreenshotResizeObserver() {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  const el = screenshotStageRef.value
  if (!el || typeof ResizeObserver === 'undefined') return
  resizeObserver = new ResizeObserver(() => updateImageLayout())
  resizeObserver.observe(el)
}

const appDevices = computed(() =>
  (devices.value || []).filter((d) => {
    const types = d.runner_engine_types || ['web']
    return d.status === '在线' && types.includes('app')
  })
)

const suggestedLocator = computed(() => suggestLocator(selectedNode.value))

const suggestedWebLocator = computed(() => suggestWebLocator(selectedWebNode.value))

const suggestWebText = computed(() => {
  const loc = suggestedWebLocator.value
  if (!loc) return '请选择 H5 元素'
  return formatWebLocatorText(loc)
})

const webPlaywrightHint = computed(() => buildWebPlaywrightHint(selectedWebNode.value))

const webPrimaryAttributes = computed(() => getWebPrimaryAttributes(selectedWebNode.value))

const webTreeData = computed(() => decorateWebNodes(webviewDom.value?.nodes || []))

const hasWebViewLayer = computed(() => {
  if (webviewNodes.value.length) return true
  return treeData.value.some((n) => containsWebView(n))
})

const activeH5Contexts = computed(() =>
  devtoolsSource.value === 'chrome' ? chromeContexts.value : webviewContexts.value
)

const activeH5Hint = computed(() =>
  devtoolsSource.value === 'chrome' ? chromeHint.value : webviewHint.value
)

function containsWebView(node) {
  if (!node) return false
  if (isWebViewNativeNode(node)) return true
  return (node.children || []).some((c) => containsWebView(c))
}

const suggestText = computed(() => {
  const loc = suggestedLocator.value
  if (!loc) return '无可推荐定位（请选择有 text/resource-id 的节点）'
  return formatLocatorText(loc)
})

const xpathText = computed(() => suggestXpath(selectedNode.value))

const u2Code = computed(() => buildU2Code(selectedNode.value))

const primaryAttributes = computed(() => getPrimaryAttributes(selectedNode.value))

const extraAttributes = computed(() => getExtraAttributes(selectedNode.value))

const canSave = computed(() => !!(saveForm.name.trim() && suggestedLocator.value))

function isVisionModel(model) {
  const m = (model || '').toLowerCase()
  return m.includes('vl') || m.includes('vision') || m.includes('gpt-4o')
}

const visionConfigs = computed(() => aiConfigList.value.filter((c) => isVisionModel(c.model)))

async function loadAiConfigs() {
  if (aiConfigList.value.length) return
  try {
    let list = []
    try {
      const res = await aiConfigApi.getSelectOptions()
      if (res.data?.code === 200) list = res.data.data || []
    } catch {
      const res = await aiConfigApi.getList({ size: 200 })
      if (res.data?.code === 200) list = res.data.data?.list || []
    }
    aiConfigList.value = list.filter((c) => c.is_enabled !== false)
    if (!visionConfigId.value) {
      const def = visionConfigs.value.find((c) => c.is_default) || visionConfigs.value[0]
      if (def) visionConfigId.value = def.id
    }
  } catch {
    /* ignore */
  }
}

function buildNodeAttributes(node) {
  if (!node) return {}
  const attrs = {
    resource_id: node.resource_id,
    text: node.text,
    class: node.class,
    content_desc: node.content_desc,
    package: node.package,
    clickable: node.clickable,
    enabled: node.enabled,
  }
  if (node.rect) {
    const { x, y, width, height } = node.rect
    attrs.bounds = `[${x},${y}][${x + width},${y + height}]`
  }
  return attrs
}

async function runAiSuggest(intent) {
  if (!selectedNode.value) return
  await loadAiConfigs()
  aiSuggesting.value = intent
  try {
    const res = await aiGenerateApi.suggestAppInspector({
      session_id: sessionId.value || undefined,
      node_attributes: buildNodeAttributes(selectedNode.value),
      suggested_locator: suggestedLocator.value || undefined,
      driver_mode: inspectorContext.value?.driverMode || 'hybrid',
      intent,
      vision_config_id: aiUseVision.value && sessionId.value ? visionConfigId.value || undefined : undefined,
    })
    const data = res.data?.data
    if (!data) {
      ElMessage.error(res.data?.message || 'AI 建议失败')
      return
    }
    if (intent === 'name' && data.element_name) {
      saveForm.name = data.element_name
      ElMessage.success('已填入元素名，请核对后保存')
    }
    if (intent === 'steps' && data.steps?.length) {
      aiGeneratedSteps.value = data.steps
      aiStepsErrors.value = data.errors || []
      aiStepsDialogVisible.value = true
      if (data.element_name && !saveForm.name.trim()) {
        saveForm.name = data.element_name
      }
    } else if (intent === 'steps') {
      ElMessage.warning('未生成有效步骤，请换选控件或补充 Vision')
    }
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e, 'AI 建议失败'))
  } finally {
    aiSuggesting.value = ''
  }
}

async function copyAiSteps() {
  if (!aiGeneratedSteps.value.length) return
  const ok = await copyToClipboard(JSON.stringify(aiGeneratedSteps.value, null, 2))
  if (ok) ElMessage.success('已复制步骤 JSON')
  else ElMessage.error('复制失败')
}

function cancelInspectorReturn() {
  clearAppInspectorContext()
  clearAppInspectorCaseDraft()
  inspectorContext.value = null
}

function navigateBackToCase() {
  const ctx = inspectorContext.value
  if (!ctx?.returnPath) {
    ElMessage.warning('无法返回用例编辑页')
    return false
  }
  clearAppInspectorContext()
  inspectorContext.value = null
  router.push(ctx.returnPath)
  return true
}

function buildLocatorForApply() {
  if (treeTab.value === 'h5') {
    const loc = suggestedWebLocator.value
    if (!loc?.by) return null
    return {
      ...loc,
      page_index: webviewPageIndex.value,
      devtools_source: devtoolsSource.value,
    }
  }
  return suggestedLocator.value
}

function applyLocatorToStep() {
  const ctx = inspectorContext.value
  if (!ctx || !inspectorHasStepTarget.value) return
  const loc = buildLocatorForApply()
  if (!loc?.by) {
    ElMessage.warning('请先选择元素并确认定位器')
    return
  }
  const stepPath = Array.isArray(ctx.stepPath) && ctx.stepPath.length
    ? ctx.stepPath
    : (typeof ctx.stepIndex === 'number' ? [ctx.stepIndex] : null)
  setAppInspectorResult({
    type: 'locator',
    stepPath,
    stepIndex: stepPath?.[stepPath.length - 1],
    caseId: ctx.caseId || null,
    locator: JSON.parse(JSON.stringify(loc)),
  })
  navigateBackToCase()
}

function applyAiStepsToCase() {
  if (!inspectorContext.value?.returnPath || !aiGeneratedSteps.value.length) return
  setAppInspectorResult({
    type: 'steps',
    steps: JSON.parse(JSON.stringify(aiGeneratedSteps.value)),
    mode: aiApplyMode.value,
    caseId: inspectorContext.value?.caseId || null,
  })
  aiStepsDialogVisible.value = false
  navigateBackToCase()
}

const canSaveWeb = computed(() => !!(saveForm.name.trim() && suggestedWebLocator.value))

const canSaveCrop = computed(() => !!(saveForm.name.trim() && cropRect.value?.width >= 8 && cropRect.value?.height >= 8))

const canSelectParent = computed(() => {
  const idx = selectedNode.value?.index
  return !!(idx && String(idx).includes('/'))
})

const highlightStyle = computed(() => {
  const node = selectedNode.value
  const layout = imageLayout.value
  if (!node?.rect || !layout) return null
  const { x, y, width, height } = node.rect
  if (!width || !height) return null
  return {
    left: `${layout.offsetX + x * layout.scale}px`,
    top: `${layout.offsetY + y * layout.scale}px`,
    width: `${Math.max(width * layout.scale, 2)}px`,
    height: `${Math.max(height * layout.scale, 2)}px`,
  }
})

const cropHighlightStyle = computed(() => {
  const layout = imageLayout.value
  if (!layout) return null
  let rect = cropRect.value
  if (cropDrag.value) {
    const { startX, startY, endX, endY } = cropDrag.value
    rect = {
      x: Math.min(startX, endX),
      y: Math.min(startY, endY),
      width: Math.abs(endX - startX),
      height: Math.abs(endY - startY),
    }
  }
  if (!rect?.width || !rect?.height) return null
  return {
    left: `${layout.offsetX + rect.x * layout.scale}px`,
    top: `${layout.offsetY + rect.y * layout.scale}px`,
    width: `${Math.max(rect.width * layout.scale, 2)}px`,
    height: `${Math.max(rect.height * layout.scale, 2)}px`,
  }
})

function updateImageLayout() {
  const img = screenshotImgRef.value
  const stage = screenshotStageRef.value
  if (!img?.naturalWidth || !stage) {
    imageLayout.value = null
    return
  }
  const stageW = stage.clientWidth
  const stageH = stage.clientHeight
  if (!stageW || !stageH) return
  const naturalW = img.naturalWidth
  const naturalH = img.naturalHeight
  const scale = Math.min(stageW / naturalW, stageH / naturalH)
  const displayW = naturalW * scale
  const displayH = naturalH * scale
  imageLayout.value = {
    offsetX: (stageW - displayW) / 2,
    offsetY: (stageH - displayH) / 2,
    scale,
    displayW,
    displayH,
  }
}

function collectNodesAtPoint(nodes, x, y, out = []) {
  for (const n of nodes || []) {
    const r = n.rect
    if (r && r.width > 0 && r.height > 0) {
      if (x >= r.x && x <= r.x + r.width && y >= r.y && y <= r.y + r.height) {
        out.push(n)
      }
    }
    if (n.children?.length) {
      collectNodesAtPoint(n.children, x, y, out)
    }
  }
  return out
}

function rankHits(hits) {
  const withIdentity = hits.filter(
    (n) => (n.resource_id || '').trim() || (n.text || '').trim() || (n.content_desc || '').trim()
  )
  const pool = withIdentity.length ? withIdentity : hits
  const score = (n) =>
    ((n.resource_id || '').trim() ? 4 : 0) +
    ((n.text || '').trim() ? 2 : 0) +
    ((n.content_desc || '').trim() ? 1 : 0)
  return [...pool].sort((a, b) => {
    const areaA = a.rect.width * a.rect.height
    const areaB = b.rect.width * b.rect.height
    if (areaA !== areaB) return areaA - areaB
    if (a.clickable !== b.clickable) return a.clickable ? -1 : 1
    return score(b) - score(a)
  })
}

function findNodesAtPoint(x, y) {
  const hits = collectNodesAtPoint(treeData.value, x, y)
  return rankHits(hits).slice(0, 8)
}

function formatCandidateLabel(n) {
  const text = (n.text || '').trim()
  if (text) return text.slice(0, 24)
  const rid = (n.resource_id || '').trim()
  if (rid) {
    const short = rid.includes('/') ? rid.split('/').pop() : rid
    return short.slice(0, 28)
  }
  const desc = (n.content_desc || '').trim()
  if (desc) return desc.slice(0, 24)
  return (n.class || '(node)').split('.').pop()
}

function rebuildNodeIndexMap() {
  const map = {}
  const walk = (list) => {
    for (const n of list || []) {
      if (n.index !== undefined) map[n.index] = n
      walk(n.children)
    }
  }
  walk(treeData.value)
  nodeIndexMap.value = map
}

function onScreenshotModeChange() {
  cropDrag.value = null
  cropRect.value = null
  cropDidDrag = false
}

function clearCropRect() {
  cropRect.value = null
  cropDrag.value = null
}

function mapEventToDevice(event) {
  const layout = imageLayout.value
  const stage = screenshotStageRef.value
  if (!layout || !stage) return null
  const stageRect = stage.getBoundingClientRect()
  const localX = event.clientX - stageRect.left
  const localY = event.clientY - stageRect.top
  const imgX = localX - layout.offsetX
  const imgY = localY - layout.offsetY
  if (imgX < 0 || imgY < 0 || imgX > layout.displayW || imgY > layout.displayH) return null
  return {
    x: Math.round(imgX / layout.scale),
    y: Math.round(imgY / layout.scale),
  }
}

function onCropMouseMove(event) {
  if (!cropDrag.value) return
  const pt = mapEventToDevice(event)
  if (!pt) return
  cropDrag.value.endX = pt.x
  cropDrag.value.endY = pt.y
  if (
    Math.abs(cropDrag.value.endX - cropDrag.value.startX) > 3 ||
    Math.abs(cropDrag.value.endY - cropDrag.value.startY) > 3
  ) {
    cropDidDrag = true
  }
}

function onCropMouseUp(event) {
  document.removeEventListener('mousemove', onCropMouseMove)
  document.removeEventListener('mouseup', onCropMouseUp)
  if (!cropDrag.value) return
  const { startX, startY, endX = startX, endY = startY } = cropDrag.value
  cropDrag.value = null
  const width = Math.abs(endX - startX)
  const height = Math.abs(endY - startY)
  if (width >= 8 && height >= 8) {
    cropRect.value = {
      x: Math.min(startX, endX),
      y: Math.min(startY, endY),
      width,
      height,
    }
    selectedNode.value = null
    selectedWebNode.value = null
    if (!saveForm.name.trim()) {
      saveForm.name = `crop_${Date.now()}`.slice(-12)
    }
  }
}

function onScreenshotMouseDown(event) {
  if (screenshotMode.value !== 'crop' || !screenshotUrl.value) return
  event.preventDefault()
  updateImageLayout()
  const pt = mapEventToDevice(event)
  if (!pt) return
  cropDidDrag = false
  cropDrag.value = { startX: pt.x, startY: pt.y, endX: pt.x, endY: pt.y }
  document.addEventListener('mousemove', onCropMouseMove)
  document.addEventListener('mouseup', onCropMouseUp)
}

function mapClickToDevice(event) {
  return mapEventToDevice(event)
}

async function cropScreenshotBlob() {
  const img = screenshotImgRef.value
  const rect = cropRect.value
  if (!img?.naturalWidth || !rect) return null
  const canvas = document.createElement('canvas')
  canvas.width = rect.width
  canvas.height = rect.height
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  ctx.drawImage(img, rect.x, rect.y, rect.width, rect.height, 0, 0, rect.width, rect.height)
  return new Promise((resolve, reject) => {
    try {
      canvas.toBlob((blob) => {
        if (!blob || blob.size <= 0) {
          reject(new Error('裁剪失败，请刷新控件树后重试'))
          return
        }
        resolve(blob)
      }, 'image/png')
    } catch (err) {
      reject(err)
    }
  })
}

function revokeScreenshotObjectUrl() {
  if (screenshotObjectUrl) {
    URL.revokeObjectURL(screenshotObjectUrl)
    screenshotObjectUrl = ''
  }
}

async function loadSessionScreenshot() {
  revokeScreenshotObjectUrl()
  if (!sessionId.value) {
    screenshotUrl.value = ''
    return
  }
  try {
    const res = await appInspectorApi.getScreenshot(sessionId.value)
    const blob = res.data
    if (!(blob instanceof Blob) || blob.size <= 0) {
      screenshotUrl.value = ''
      return
    }
    screenshotObjectUrl = URL.createObjectURL(blob)
    screenshotUrl.value = screenshotObjectUrl
  } catch (e) {
    screenshotUrl.value = ''
    ElMessage.warning(getApiErrorMessage(e, '截图加载失败，识别图裁剪可能不可用'))
  }
}

function buildCropLocator(objectKey) {
  const img = screenshotImgRef.value
  const rect = cropRect.value
  const nw = img?.naturalWidth || 0
  const nh = img?.naturalHeight || 0
  const locator = {
    by: 'image',
    value: objectKey,
    threshold: 0.8,
    rgb: false,
  }
  if (rect && nw && nh) {
    const cx = rect.x + rect.width / 2
    const cy = rect.y + rect.height / 2
    locator.record_pos = [cx / nw - 0.5, cy / nh - 0.5]
    locator.resolution = [nw, nh]
  }
  return locator
}

async function saveCropToLibrary() {
  if (!canSaveCrop.value) return
  saving.value = true
  try {
    const blob = await cropScreenshotBlob()
    if (!blob) {
      ElMessage.warning('裁剪失败，请重试')
      return
    }
    const file = new File([blob], `${saveForm.name.trim()}.png`, { type: 'image/png' })
    const res = await appElementApi.uploadTemplate(proStore.projectInfo.id, file)
    const data = res.data?.data || res.data
    const objectKey = data?.object_key || ''
    if (!objectKey) {
      ElMessage.error('上传失败：未返回 object_key')
      return
    }
    await appElementApi.create({
      name: saveForm.name.trim(),
      project_id: proStore.projectInfo.id,
      element_type: 'image',
      locator: buildCropLocator(objectKey),
      remark: '元素探查截图裁剪',
      username: uStore.userInfo?.username,
    })
    ElMessage.success('识别图已保存到元素库')
    clearCropRect()
  } catch (e) {
    const msg =
      e?.name === 'SecurityError' || /裁剪失败/.test(String(e?.message || ''))
        ? String(e?.message || '截图跨域无法裁剪，请刷新控件树后重试')
        : getApiErrorMessage(e, '保存失败')
    if (isDuplicateElementNameError(e)) {
      ElMessage.warning(msg)
    } else {
      ElMessage.error(msg)
    }
  } finally {
    saving.value = false
  }
}

function selectNode(node) {
  if (!node) return
  clearCropRect()
  selectedNode.value = node
  selectedWebNode.value = null
  if (isWebViewNativeNode(node)) {
    treeTab.value = 'native'
  }
  const base = node.text || node.resource_id || node.content_desc || 'element'
  saveForm.name = base.slice(0, 50).replace(/[^\w\u4e00-\u9fa5_-]/g, '_')
  nextTick(() => {
    treeRef.value?.setCurrentKey?.(node.index)
  })
}

function selectWebNode(node) {
  if (!node) return
  selectedWebNode.value = node
  selectedNode.value = null
  treeTab.value = 'h5'
  const base = node.text || node.data_testid || node.id || node.tag || 'h5_element'
  saveForm.name = base.slice(0, 50).replace(/[^\w\u4e00-\u9fa5_-]/g, '_')
  nextTick(() => {
    webTreeRef.value?.setCurrentKey?.(node.index)
  })
}

function onWebNodeClick(node) {
  selectWebNode(node)
}

function applySessionWebviewFields(data) {
  webviewNodes.value = data.webview_nodes || []
  webviewContexts.value = data.webview_contexts || []
  webviewHint.value = data.webview_hint || ''
  chromeContexts.value = data.chrome_contexts || []
  chromeHint.value = data.chrome_hint || ''
  if (data.devtools_source) {
    devtoolsSource.value = data.devtools_source
  }
  if (data.webview_dom) {
    webviewDom.value = data.webview_dom
  }
  if (data.webview_error) {
    webviewError.value = data.webview_error
  } else if (data.webview_status === 'ready') {
    webviewError.value = ''
  }
  if (typeof data.webview_page_index === 'number') {
    webviewPageIndex.value = data.webview_page_index
  }
}

function selectParentNode() {
  const idx = selectedNode.value?.index
  if (!idx || !String(idx).includes('/')) return
  const parentIndex = String(idx).slice(0, String(idx).lastIndexOf('/'))
  const parent = nodeIndexMap.value[parentIndex]
  if (parent) {
    nodeCandidates.value = []
    selectNode(parent)
  }
}

function decorateNodes(nodes) {
  return (nodes || []).map((n) => ({
    ...n,
    label: n.text || n.resource_id || n.content_desc || n.class || '(node)',
    children: decorateNodes(n.children),
  }))
}

watch(devtoolsSource, () => {
  webviewPageIndex.value = 0
})

async function loadDevices() {
  try {
    const res = await deviceApi.getList({ page: 1, size: 200, status: '在线' })
    devices.value = res.data?.data || res.data || []
  } catch {
    devices.value = []
  }
}

async function connectSession() {
  if (!deviceId.value) {
    ElMessage.warning('请选择执行设备')
    return
  }
  connecting.value = true
  try {
    const res = await appInspectorApi.createSession({
      project_id: proStore.projectInfo.id,
      device_id: deviceId.value,
      app_udid: appUdid.value,
    })
    const data = res.data?.data || res.data
    sessionId.value = data.session_id
    ElMessage.success('已连接元素探查会话')
    await refreshDump()
  } finally {
    connecting.value = false
  }
}

async function disconnectSession() {
  if (sessionId.value) {
    try {
      await appInspectorApi.close(sessionId.value)
    } catch {
      /* ignore */
    }
  }
  stopPoll()
  stopLiveMirror()
  liveMirror.value = false
  sessionId.value = ''
  revokeScreenshotObjectUrl()
  treeData.value = []
  screenshotUrl.value = ''
  selectedNode.value = null
  selectedWebNode.value = null
  nodeCandidates.value = []
  webviewNodes.value = []
  webviewContexts.value = []
  webviewHint.value = ''
  chromeContexts.value = []
  chromeHint.value = ''
  devtoolsSource.value = 'webview'
  webviewDom.value = null
  webviewError.value = ''
  webviewProbing.value = false
  treeTab.value = 'native'
  sessionMeta.package = ''
  sessionMeta.activity = ''
}

function stopWebviewPoll() {
  if (webviewPollTimer) {
    clearInterval(webviewPollTimer)
    webviewPollTimer = null
  }
  webviewPollAttempts = 0
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  pollAttempts = 0
  stopWebviewPoll()
  stopExplorePoll()
}

function stopExplorePoll() {
  if (explorePollTimer) {
    clearInterval(explorePollTimer)
    explorePollTimer = null
  }
  explorePollAttempts = 0
}

function stopLiveMirror() {
  if (mirrorTimer) {
    clearInterval(mirrorTimer)
    mirrorTimer = null
  }
  mirrorBusy.value = false
}

function onLiveMirrorChange(enabled) {
  stopLiveMirror()
  if (enabled && sessionId.value) {
    mirrorTimer = setInterval(tickLiveMirror, MIRROR_INTERVAL_MS)
    tickLiveMirror()
  }
}

async function tickLiveMirror() {
  if (!sessionId.value || !liveMirror.value || mirrorBusy.value) return
  if (dumping.value || exploring.value) return
  mirrorBusy.value = true
  try {
    await appInspectorApi.refreshScreenshot(sessionId.value)
    await pollScreenshotOnce()
  } catch {
    /* 静默失败，下一轮重试 */
  } finally {
    mirrorBusy.value = false
  }
}

async function pollScreenshotOnce() {
  for (let i = 0; i < 15; i += 1) {
    await new Promise((r) => setTimeout(r, 400))
    const res = await appInspectorApi.getSession(sessionId.value)
    const data = res.data?.data || res.data
    if (data?.screenshot_status === 'ready') {
      sessionMeta.package = data.package || sessionMeta.package
      sessionMeta.activity = data.activity || sessionMeta.activity
      await loadSessionScreenshot()
      return
    }
    if (data?.screenshot_status === 'failed') return
  }
}

async function runExplore(payload) {
  if (!sessionId.value || !canEdit.value) return
  exploring.value = true
  stopExplorePoll()
  try {
    await appInspectorApi.explore(sessionId.value, {
      refresh_tree: exploreRefreshTree.value,
      ...payload,
    })
    explorePollAttempts = 0
    explorePollTimer = setInterval(pollExploreSession, POLL_INTERVAL_MS)
    await pollExploreSession()
  } catch (e) {
    exploring.value = false
    ElMessage.error(getApiErrorMessage(e, '探索操作失败'))
  }
}

async function pollExploreSession() {
  if (!sessionId.value) return
  explorePollAttempts += 1
  if (explorePollAttempts > POLL_MAX_ATTEMPTS) {
    exploring.value = false
    stopExplorePoll()
    ElMessage.error('探索操作超时，请重试')
    return
  }
  try {
    const res = await appInspectorApi.getSession(sessionId.value)
    const data = res.data?.data || res.data
    if (!data) return
    sessionMeta.package = data.package || ''
    sessionMeta.activity = data.activity || ''
    if (data.explore_status === 'ready') {
      if (data.hierarchy?.nodes?.length) {
        treeData.value = decorateNodes(data.hierarchy.nodes)
        rebuildNodeIndexMap()
      }
      applySessionWebviewFields(data)
      await loadSessionScreenshot()
      exploring.value = false
      stopExplorePoll()
      nextTick(updateImageLayout)
    } else if (data.explore_status === 'failed') {
      exploring.value = false
      stopExplorePoll()
      ElMessage.error(data.error || '探索操作失败')
    }
  } catch (e) {
    exploring.value = false
    stopExplorePoll()
    ElMessage.error(getApiErrorMessage(e, '获取探索结果失败'))
  }
}

async function exploreBack() {
  await runExplore({ action: 'back' })
}

async function exploreHome() {
  await runExplore({ action: 'home' })
}

async function exploreInput() {
  try {
    const { value } = await ElMessageBox.prompt('输入要发送到当前焦点控件的文本', '探索输入', {
      confirmButtonText: '发送',
      cancelButtonText: '取消',
      inputPlaceholder: '文本内容',
    })
    if (value != null && String(value).trim()) {
      await runExplore({ action: 'input', text: String(value) })
    }
  } catch {
    /* cancelled */
  }
}

async function pollSession() {
  if (!sessionId.value) return
  try {
    pollAttempts += 1
    if (pollAttempts > POLL_MAX_ATTEMPTS) {
      dumping.value = false
      stopPoll()
      ElMessage.error('原生控件探测超时，请重试')
      return
    }
    const res = await appInspectorApi.getSession(sessionId.value)
    const data = res.data?.data || res.data
    if (!data) return
    sessionMeta.package = data.package || ''
    sessionMeta.activity = data.activity || ''
    if (data.status === 'ready' && data.hierarchy) {
      treeData.value = decorateNodes(data.hierarchy.nodes || [])
      rebuildNodeIndexMap()
      await loadSessionScreenshot()
      applySessionWebviewFields(data)
      dumping.value = false
      stopPoll()
      nextTick(updateImageLayout)
    } else if (data.status === 'failed') {
      dumping.value = false
      stopPoll()
      ElMessage.error(data.error || '探测失败')
    }
  } catch (e) {
    dumping.value = false
    stopPoll()
    ElMessage.error(getApiErrorMessage(e, '获取探测结果失败'))
  }
}

async function pollWebviewSession() {
  if (!sessionId.value) return
  try {
    webviewPollAttempts += 1
    if (webviewPollAttempts > POLL_MAX_ATTEMPTS) {
      webviewProbing.value = false
      stopWebviewPoll()
      ElMessage.error('H5 DOM 探测超时，请重试')
      return
    }
    const res = await appInspectorApi.getSession(sessionId.value)
    const data = res.data?.data || res.data
    if (!data) return
    applySessionWebviewFields(data)
    if (data.webview_status === 'ready' && data.webview_dom) {
      webviewProbing.value = false
      stopWebviewPoll()
      treeTab.value = 'h5'
      ElMessage.success('H5 DOM 抓取完成')
    } else if (data.webview_status === 'failed') {
      webviewProbing.value = false
      stopWebviewPoll()
      ElMessage.error(data.webview_error || 'H5 DOM 探测失败')
    }
  } catch (e) {
    webviewProbing.value = false
    stopWebviewPoll()
    ElMessage.error(getApiErrorMessage(e, '获取 H5 探测结果失败'))
  }
}

async function probeWebviewDom() {
  if (!sessionId.value) return
  webviewProbing.value = true
  webviewError.value = ''
  selectedWebNode.value = null
  try {
    await appInspectorApi.webviewProbe(sessionId.value, {
      page_index: webviewPageIndex.value,
      package: devtoolsSource.value === 'webview' ? (sessionMeta.package || '') : '',
      devtools_source: devtoolsSource.value,
    })
    stopWebviewPoll()
    webviewPollAttempts = 0
    webviewPollTimer = setInterval(pollWebviewSession, POLL_INTERVAL_MS)
    await pollWebviewSession()
  } catch (e) {
    webviewProbing.value = false
    ElMessage.error(getApiErrorMessage(e, '下发 H5 探测失败'))
  }
}

async function manualRefreshScreenshot() {
  if (!sessionId.value || mirrorBusy.value) return
  mirrorBusy.value = true
  try {
    await appInspectorApi.refreshScreenshot(sessionId.value)
    await pollScreenshotOnce()
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e, '刷新截图失败'))
  } finally {
    mirrorBusy.value = false
  }
}

async function manualRefreshTree() {
  if (!sessionId.value || dumping.value) return
  stopExplorePoll()
  exploring.value = false
  await refreshDump()
}

async function refreshDump() {
  if (!sessionId.value) return
  stopExplorePoll()
  exploring.value = false
  dumping.value = true
  treeData.value = []
  selectedNode.value = null
  selectedWebNode.value = null
  nodeCandidates.value = []
  webviewDom.value = null
  webviewError.value = ''
  try {
    await appInspectorApi.dump(sessionId.value)
    stopPoll()
    pollAttempts = 0
    pollTimer = setInterval(pollSession, POLL_INTERVAL_MS)
    await pollSession()
  } catch (e) {
    dumping.value = false
  }
}

function onScreenshotError() {
  ElMessage.warning('截图加载失败，请确认 MinIO 端口已放行或联系管理员检查存储配置')
}

function onScreenshotClick(event) {
  if (screenshotMode.value === 'crop') {
    if (cropDidDrag) {
      cropDidDrag = false
    }
    return
  }
  if (screenshotMode.value === 'explore') {
    if (!canEdit.value) return
    updateImageLayout()
    const pt = mapClickToDevice(event)
    if (!pt) return
    runExplore({ action: 'tap', x: pt.x, y: pt.y })
    return
  }
  if (!screenshotUrl.value || !treeData.value.length) return
  updateImageLayout()
  const pt = mapClickToDevice(event)
  if (!pt) return
  const hits = findNodesAtPoint(pt.x, pt.y)
  if (!hits.length) {
    nodeCandidates.value = []
    ElMessage.info('该位置未匹配到控件，请换位置或从左侧树选择')
    return
  }
  nodeCandidates.value = hits
  selectNode(hits[0])
}

function onNodeClick(node) {
  nodeCandidates.value = []
  selectNode(node)
}

async function copyText(text, label = '内容') {
  const ok = await copyToClipboard(text)
  if (ok) ElMessage.success(`已复制${label}`)
  else ElMessage.error('复制失败')
}

async function copyLocator() {
  const loc = suggestedLocator.value
  if (!loc) return
  await copyText(formatLocatorJson(loc), '定位器 JSON')
}

async function copyWebLocator() {
  const loc = suggestedWebLocator.value
  if (!loc) return
  await copyText(formatWebLocatorJson(loc), 'H5 定位器 JSON')
}

async function saveToLibrary() {
  if (!canSave.value) return
  saving.value = true
  try {
    await appElementApi.create({
      name: saveForm.name.trim(),
      project_id: proStore.projectInfo.id,
      element_type: 'control',
      locator: { ...suggestedLocator.value },
      remark: '元素探查抓取',
      username: uStore.userInfo?.username,
    })
    ElMessage.success('已保存到元素库')
  } catch (e) {
    const msg = getApiErrorMessage(e, '保存失败')
    if (isDuplicateElementNameError(e)) {
      ElMessage.warning(msg)
    } else {
      ElMessage.error(msg)
    }
  } finally {
    saving.value = false
  }
}

async function saveWebToLibrary() {
  if (!canSaveWeb.value) return
  saving.value = true
  try {
    await appElementApi.create({
      name: saveForm.name.trim(),
      project_id: proStore.projectInfo.id,
      element_type: 'control',
      locator: {
        ...suggestedWebLocator.value,
        page_index: webviewPageIndex.value,
        devtools_source: devtoolsSource.value,
      },
      remark: '元素探查 H5 抓取',
      username: uStore.userInfo?.username,
    })
    ElMessage.success('H5 元素已保存到元素库（用例驱动模式请选 hybrid_web / mobile_chrome）')
  } catch (e) {
    const msg = getApiErrorMessage(e, '保存失败')
    if (isDuplicateElementNameError(e)) {
      ElMessage.warning(msg)
    } else {
      ElMessage.error(msg)
    }
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  inspectorContext.value = getAppInspectorContext()
  loadColWidths()
  window.addEventListener('resize', onWindowResize)
  await loadDevices()
  const qDevice = route.query.device_id
  if (qDevice) {
    deviceId.value = String(qDevice)
  }
  const qUdid = route.query.app_udid
  if (qUdid) {
    appUdid.value = String(qUdid)
  }
  nextTick(() => {
    clampColWidths()
    updateImageLayout()
  })
})

function onWindowResize() {
  clampColWidths()
  updateImageLayout()
}

watch(screenshotUrl, () => {
  imageLayout.value = null
  nextTick(() => {
    updateImageLayout()
    bindScreenshotResizeObserver()
  })
})

onBeforeUnmount(() => {
  onSplitterMouseUp()
  document.removeEventListener('mousemove', onCropMouseMove)
  document.removeEventListener('mouseup', onCropMouseUp)
  window.removeEventListener('resize', onWindowResize)
  revokeScreenshotObjectUrl()
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  stopPoll()
  stopLiveMirror()
  if (sessionId.value) {
    appInspectorApi.close(sessionId.value).catch(() => {})
  }
})
</script>

<style scoped>
.toolbar {
  margin-bottom: 8px;
  flex-shrink: 0;
}
.empty-hint {
  color: #909399;
  padding: 24px;
  text-align: center;
}
.app-inspector-page :deep(.main_box) {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.app-inspector-page :deep(.el-alert) {
  flex-shrink: 0;
}
.inspector-layout {
  display: grid;
  gap: 0;
  flex: 1 1 0;
  min-height: 480px;
  height: 0;
}
.col-splitter {
  width: 6px;
  margin: 0 2px;
  cursor: col-resize;
  border-radius: 4px;
  background: transparent;
  transition: background 0.15s;
  flex-shrink: 0;
}
.col-splitter:hover,
.col-splitter:active {
  background: var(--el-color-primary-light-7);
}
.inspector-col {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--el-bg-color);
}
.col-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.tree-col-body {
  flex: 1;
  min-height: 0;
  overflow-x: auto;
  overflow-y: auto;
}
.tree-col-body :deep(.inspector-tree) {
  display: inline-block;
  min-width: max(100%, 480px);
}
.tree-col-body :deep(.el-tree-node__label) {
  white-space: nowrap;
}
.tree-col-body :deep(.el-tree-node__content) {
  height: auto;
  min-height: 26px;
}
.tree-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.tree-tabs :deep(.el-tabs__header) {
  flex-shrink: 0;
  margin-bottom: 8px;
}
.tree-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.tree-tabs :deep(.el-tab-pane) {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.tree-panel {
  min-width: 0;
  overflow: hidden;
}
.webview-hint-body {
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}
.webview-hint-body p {
  margin: 0 0 8px;
}
.webview-context-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.ctx-label {
  font-size: 13px;
  color: #606266;
}
.h5-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 12px;
  color: #909399;
  font-size: 13px;
}
.explore-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  padding: 0 4px;
}
.explore-hint {
  margin: 0 0 8px;
  padding: 0 4px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}
.screenshot-panel {
  min-width: 0;
}
.props-panel {
  min-width: 0;
  overflow-y: auto;
}
.props-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}
.panel-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.row-between {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.overlap-candidates {
  margin-bottom: 10px;
}
.candidate-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.candidate-tag {
  cursor: pointer;
  max-width: 100%;
}
.panel-hint {
  font-weight: normal;
  font-size: 12px;
  color: #909399;
}
.screenshot-wrap {
  flex: 1;
  min-height: 0;
  background: #111;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.screenshot-stage {
  position: relative;
  flex: 1;
  width: 100%;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: crosshair;
}
.screenshot {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  display: block;
  user-select: none;
}
.node-highlight {
  position: absolute;
  border: 2px solid #409eff;
  background: rgba(64, 158, 255, 0.18);
  pointer-events: none;
  box-sizing: border-box;
  border-radius: 2px;
  z-index: 1;
}
.crop-highlight {
  position: absolute;
  border: 2px dashed #e6a23c;
  background: rgba(230, 162, 60, 0.15);
  pointer-events: none;
  box-sizing: border-box;
  border-radius: 2px;
  z-index: 2;
}
.screenshot-stage.is-crop-mode {
  cursor: crosshair;
}
.crop-meta {
  margin: 0 0 12px;
  font-size: 12px;
  color: #909399;
}
.node-detail {
  flex: 1;
  min-height: 0;
}
.locator-code {
  display: block;
  word-break: break-all;
  white-space: pre-wrap;
  font-size: 12px;
  padding: 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  margin: 0;
}
.attr-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-bottom: 10px;
}
.attr-table th,
.attr-table td {
  border: 1px solid var(--el-border-color-lighter);
  padding: 6px 8px;
  vertical-align: top;
}
.attr-table th {
  background: var(--el-fill-color-light);
  font-weight: 600;
  text-align: left;
}
.attr-col-name {
  width: 96px;
}
.attr-col-action {
  width: 44px;
}
.attr-name {
  color: #606266;
  white-space: nowrap;
}
.attr-value {
  word-break: break-all;
  color: #303133;
}
.attr-action {
  text-align: center;
}
.attr-table-compact td {
  padding: 4px 8px;
}
.extra-attrs {
  margin-bottom: 10px;
  border: none;
}
.extra-attrs :deep(.el-collapse-item__header) {
  font-size: 13px;
  font-weight: 600;
  height: 36px;
  line-height: 36px;
}
.extra-attrs :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}
.code-section {
  margin-top: 10px;
}
.code-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.ai-suggest-section {
  margin-top: 12px;
  padding: 10px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
.ai-suggest-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.ai-step-row {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 8px;
}
.ai-step-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
  font-size: 13px;
}
.ai-step-desc {
  color: var(--el-text-color-secondary);
}
.ai-step-params {
  margin: 0;
  font-size: 12px;
  background: var(--el-fill-color-light);
  padding: 8px;
  border-radius: 4px;
  overflow: auto;
}
.save-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
@media (max-width: 1200px) {
  .app-inspector-page :deep(.main_box) {
    overflow-y: auto;
  }
  .inspector-layout {
    grid-template-columns: 1fr !important;
    flex: none;
    height: auto;
    min-height: 0;
  }
  .col-splitter {
    display: none;
  }
  .tree-panel {
    min-height: 220px;
    max-height: 320px;
  }
  .screenshot-panel {
    min-height: 480px;
  }
  .props-panel {
    max-height: 360px;
  }
}
</style>

<style>
body.inspector-col-resizing {
  cursor: col-resize !important;
  user-select: none;
}
body.inspector-col-resizing * {
  cursor: col-resize !important;
}
.suggest-title {
  color: #606266;
  font-size: 13px;
  font-weight: 600;
}
.usage-steps {
  margin: 4px 0 0 18px;
  padding: 0;
  font-size: 13px;
  line-height: 1.8;
  color: #606266;
}
</style>
