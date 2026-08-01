<template>
  <div v-if="visible" class="platform-assistant">
    <el-tooltip :content="`${ASSISTANT_NAME} · 平台助手`" placement="left">
      <button
        class="assistant-fab"
        type="button"
        :class="{ 'fab-hidden': panelOpen }"
        @click="togglePanel"
      >
        <AssistantMascot size="large" />
      </button>
    </el-tooltip>

    <Teleport to="body">
      <div
        v-show="panelOpen"
        ref="panelRef"
        class="assistant-panel"
        :class="{ maximized: isMaximized }"
        :style="panelStyle"
      >
        <div class="panel-header" @mousedown="onDragStart">
          <div class="header-left">
            <AssistantMascot size="small" />
            <span class="panel-title">{{ ASSISTANT_NAME }} · 平台助手</span>
            <el-tag size="small" type="success">Phase 4</el-tag>
          </div>
          <div class="header-actions" @mousedown.stop>
            <el-tooltip :content="isMaximized ? '还原窗口' : '放大窗口'" placement="bottom">
              <button type="button" class="icon-btn" @click="toggleMaximize">
                <el-icon><FullScreen v-if="!isMaximized" /><CopyDocument v-else /></el-icon>
              </button>
            </el-tooltip>
            <el-tooltip content="关闭" placement="bottom">
              <button type="button" class="icon-btn close-btn" @click="panelOpen = false">
                <el-icon><Close /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>

        <div class="panel-body">
          <div class="session-bar">
            <el-select
              v-model="sessionId"
              placeholder="选择会话"
              size="small"
              :disabled="loading || !projectId"
              class="session-select"
              @change="switchSession"
            >
              <el-option v-for="s in sessions" :key="s.id" :label="s.title" :value="s.id" />
            </el-select>
            <el-button size="small" :disabled="!projectId || loading" @click="handleNewSession">新建</el-button>
            <el-dropdown trigger="click" @command="handleSessionCommand">
              <el-button size="small" :disabled="!sessionId">更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename">重命名</el-dropdown-item>
                  <el-dropdown-item command="clear">清空消息</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除会话</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <el-input
            v-model="sessionKeyword"
            size="small"
            clearable
            placeholder="搜索会话标题、预览或消息内容"
            class="session-search"
            :disabled="!projectId"
          />

          <div class="assistant-meta">
            <span v-if="projectLabel">当前项目：{{ projectLabel }}</span>
            <span v-else class="meta-warn">请先在顶部切换项目</span>
            <el-tag v-if="pageContextLabel" size="small" type="info" class="page-ctx-tag">
              {{ pageContextLabel }}
            </el-tag>
          </div>

          <div class="quick-chips">
            <el-button
              v-for="item in quickPrompts"
              :key="item.key"
              size="small"
              round
              :disabled="loading"
              @click="sendQuick(item.message)"
            >
              {{ item.label }}
            </el-button>
          </div>

          <div ref="messageBoxRef" class="message-box">
            <div v-if="messages.length === 0" class="empty-hint">
              可询问项目概览、需求、接口、UI 用例、最近失败等；执行/生成类操作需点击确认卡片。
            </div>
            <div
              v-for="(msg, idx) in messages"
              :key="idx"
              class="message-item"
              :class="[msg.role, msg.streaming ? 'streaming' : '']"
            >
              <div class="message-role">{{ msg.role === 'user' ? '我' : ASSISTANT_NAME }}</div>
              <div v-if="msg.role === 'assistant'" class="message-content assistant-md">
                <MarkdownReport compact :content="linkifyAssistantContent(msg.content)" />
                <span v-if="msg.streaming" class="cursor">▍</span>
              </div>
              <div v-else class="message-content user-text">{{ msg.content }}</div>
              <div v-if="msg.tools?.length" class="message-tools">
                <el-tag v-for="t in msg.tools" :key="t" size="small" type="success">{{ t }}</el-tag>
              </div>
              <div v-if="msg.pending_confirm && !msg.confirm_done" class="confirm-card">
                <div class="confirm-title">待确认操作</div>
                <div class="confirm-impact assistant-md">
                  <MarkdownReport compact :content="linkifyAssistantContent(formatImpact(msg.pending_confirm))" />
                </div>
                <div class="confirm-actions">
                  <el-button
                    type="primary"
                    size="small"
                    :loading="confirmLoading === idx"
                    @click="handleConfirm(msg, idx)"
                  >
                    确认执行
                  </el-button>
                  <el-button size="small" :disabled="confirmLoading === idx" @click="cancelConfirm(msg)">
                    取消
                  </el-button>
                </div>
              </div>
            </div>
            <div v-if="loading" class="message-item assistant loading-item">
              <div class="message-role">{{ ASSISTANT_NAME }}</div>
              <div class="tool-status">{{ statusText || '正在查询并生成回答…' }}</div>
            </div>
          </div>

          <div class="input-area">
            <el-input
              v-model="inputText"
              type="textarea"
              :rows="3"
              placeholder="例如：总结当前项目情况；或：执行接口用例 12；或：预览执行接口套件 3"
              :disabled="loading"
              @keydown.enter.exact.prevent="sendMessage"
            />
            <div class="input-actions">
              <el-button size="small" :disabled="loading || !sessionId" @click="clearChat">清空</el-button>
              <el-button type="primary" size="small" :loading="loading" @click="sendMessage">发送</el-button>
            </div>
          </div>
        </div>

        <div v-if="!isMaximized" class="resize-handle" @mousedown="onResizeStart" />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, CopyDocument, FullScreen } from '@element-plus/icons-vue'
import { aiAssistantApi } from '@/api/modules/ai_assistant.js'
import { UserStore } from '@/stores/module/UserStore.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import AssistantMascot from '@/components/AssistantMascot.vue'
import MarkdownReport from '@/components/MarkdownReport.vue'
import { buildAssistantPageContext, formatPageContextLabel } from '@/utils/assistantPageContext.js'
import { linkifyAssistantContent } from '@/utils/assistantLinkify.js'

const ASSISTANT_NAME = '小测'

const uStore = UserStore()
const proStore = ProjectStore()
const route = useRoute()

const panelOpen = ref(false)
const isMaximized = ref(false)
const panelRef = ref(null)
const panelPos = ref({ x: 0, y: 0 })
const panelSize = ref({ w: 500, h: 620 })
const posInitialized = ref(false)

const inputText = ref('')
const messages = ref([])
const loading = ref(false)
const confirmLoading = ref(-1)
const statusText = ref('')
const quickPrompts = ref([])
const messageBoxRef = ref(null)
const sessionId = ref(null)
const sessions = ref([])
const sessionKeyword = ref('')
let sessionSearchTimer = null

let dragState = null
let resizeState = null

const visible = computed(() => !!uStore.token && uStore.hasPermission('ai_test:view'))
const projectId = computed(() => proStore.projectInfo?.id || null)
const projectLabel = computed(() => {
  if (!projectId.value) return ''
  return proStore.projectInfo?.name ? `${proStore.projectInfo.name} (id=${projectId.value})` : `id=${projectId.value}`
})

const pageContext = computed(() => buildAssistantPageContext(route))
const pageContextLabel = computed(() => formatPageContextLabel(pageContext.value))

const panelStyle = computed(() => {
  if (isMaximized.value) {
    return {
      top: '24px',
      left: '24px',
      width: 'calc(100vw - 48px)',
      height: 'calc(100vh - 48px)'
    }
  }
  return {
    top: `${panelPos.value.y}px`,
    left: `${panelPos.value.x}px`,
    width: `${panelSize.value.w}px`,
    height: `${panelSize.value.h}px`
  }
})

const initPanelPosition = () => {
  const w = panelSize.value.w
  const h = panelSize.value.h
  panelPos.value = {
    x: Math.max(16, window.innerWidth - w - 24),
    y: Math.max(16, window.innerHeight - h - 96)
  }
  posInitialized.value = true
}

const togglePanel = () => {
  panelOpen.value = !panelOpen.value
  if (panelOpen.value && !posInitialized.value) {
    initPanelPosition()
  }
}

const toggleMaximize = () => {
  isMaximized.value = !isMaximized.value
}

const clampPanel = () => {
  if (isMaximized.value) return
  const maxX = window.innerWidth - 120
  const maxY = window.innerHeight - 80
  panelPos.value.x = Math.min(Math.max(0, panelPos.value.x), maxX)
  panelPos.value.y = Math.min(Math.max(0, panelPos.value.y), maxY)
  panelSize.value.w = Math.min(Math.max(380, panelSize.value.w), window.innerWidth - 32)
  panelSize.value.h = Math.min(Math.max(420, panelSize.value.h), window.innerHeight - 48)
}

const onDragStart = (e) => {
  if (isMaximized.value || e.button !== 0) return
  dragState = {
    startX: e.clientX,
    startY: e.clientY,
    originX: panelPos.value.x,
    originY: panelPos.value.y
  }
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', onDragEnd)
}

const onDragMove = (e) => {
  if (!dragState) return
  panelPos.value.x = dragState.originX + (e.clientX - dragState.startX)
  panelPos.value.y = dragState.originY + (e.clientY - dragState.startY)
}

const onDragEnd = () => {
  dragState = null
  clampPanel()
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
}

const onResizeStart = (e) => {
  if (isMaximized.value || e.button !== 0) return
  e.preventDefault()
  resizeState = {
    startX: e.clientX,
    startY: e.clientY,
    originW: panelSize.value.w,
    originH: panelSize.value.h
  }
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', onResizeEnd)
}

const onResizeMove = (e) => {
  if (!resizeState) return
  panelSize.value.w = resizeState.originW + (e.clientX - resizeState.startX)
  panelSize.value.h = resizeState.originH + (e.clientY - resizeState.startY)
}

const onResizeEnd = () => {
  resizeState = null
  clampPanel()
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
}

const onWindowResize = () => {
  if (!posInitialized.value) return
  clampPanel()
}

const scrollToBottom = async () => {
  await nextTick()
  const el = messageBoxRef.value
  if (el) el.scrollTop = el.scrollHeight
}

const normalizeMessages = (items) => {
  if (!Array.isArray(items)) return []
  return items.map((m) => ({
    role: m.role || 'assistant',
    content: m.content || '',
    tools: m.tools || [],
    pending_confirm: m.pending_confirm || null,
    confirm_done: m.confirm_done || false,
    execution_follow_up: m.execution_follow_up || false,
    streaming: false
  }))
}

let executionWatchTimer = null

const stopExecutionWatch = () => {
  if (executionWatchTimer) {
    clearInterval(executionWatchTimer)
    executionWatchTimer = null
  }
}

const startExecutionWatch = (baselineCount) => {
  stopExecutionWatch()
  statusText.value = '任务执行中，完成后将自动更新结果…'
  let attempts = 0
  executionWatchTimer = setInterval(async () => {
    attempts += 1
    if (attempts > 120 || !sessionId.value || !projectId.value) {
      stopExecutionWatch()
      statusText.value = ''
      return
    }
    try {
      const res = await aiAssistantApi.getSession(projectId.value, sessionId.value)
      if (res.data?.code !== 200) return
      const serverMsgs = normalizeMessages(res.data.data?.messages || [])
      const follow = serverMsgs.find((m) => m.execution_follow_up)
      if (follow && serverMsgs.length > baselineCount) {
        messages.value = serverMsgs
        stopExecutionWatch()
        statusText.value = ''
        const idx = serverMsgs.indexOf(follow)
        await revealStreaming(idx, follow.content)
        ElMessage.success('执行结果已更新')
      }
    } catch {
      /* ignore poll errors */
    }
  }, 3000)
}

const loadSessions = async (pickSessionId = null) => {
  if (!projectId.value) {
    sessions.value = []
    sessionId.value = null
    messages.value = []
    return
  }
  try {
    const res = await aiAssistantApi.listSessions(projectId.value, sessionKeyword.value)
    if (res.data?.code === 200) {
      sessions.value = res.data.data?.items || []
      if (pickSessionId && sessions.value.some((s) => s.id === pickSessionId)) {
        sessionId.value = pickSessionId
      } else if (!sessionId.value && sessions.value.length) {
        sessionId.value = sessions.value[0].id
      } else if (sessionId.value && !sessions.value.some((s) => s.id === sessionId.value)) {
        sessionId.value = sessions.value[0]?.id || null
      }
    }
  } catch {
    sessions.value = []
  }
}

const loadSessionFromServer = async () => {
  if (!projectId.value) {
    messages.value = []
    sessionId.value = null
    sessions.value = []
    return
  }
  await loadSessions(sessionId.value)
  if (!sessionId.value) {
    messages.value = []
    return
  }
  try {
    const res = await aiAssistantApi.getSession(projectId.value, sessionId.value)
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      sessionId.value = d.session_id || sessionId.value
      messages.value = normalizeMessages(d.messages)
    }
  } catch {
    messages.value = []
  }
}

const switchSession = async () => {
  await loadSessionFromServer()
  scrollToBottom()
}

const handleNewSession = async () => {
  if (!projectId.value) return
  try {
    const res = await aiAssistantApi.createSession(projectId.value)
    if (res.data?.code === 200) {
      const item = res.data.data
      await loadSessions(item?.id)
      sessionId.value = item?.id || sessionId.value
      messages.value = []
      ElMessage.success('已创建新会话')
    }
  } catch {
    ElMessage.error('创建会话失败')
  }
}

const handleSessionCommand = async (cmd) => {
  if (!sessionId.value) return
  if (cmd === 'rename') {
    const current = sessions.value.find((s) => s.id === sessionId.value)
    try {
      const { value } = await ElMessageBox.prompt('请输入会话标题', '重命名会话', {
        inputValue: current?.title || '',
        confirmButtonText: '保存',
        cancelButtonText: '取消'
      })
      if (!value?.trim()) return
      const res = await aiAssistantApi.renameSession(sessionId.value, value.trim())
      if (res.data?.code === 200) {
        await loadSessions(sessionId.value)
        ElMessage.success('已重命名')
      }
    } catch {
      /* cancelled */
    }
    return
  }
  if (cmd === 'clear') {
    await clearChat()
    return
  }
  if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm('确定删除该会话？此操作不可恢复。', '删除会话', { type: 'warning' })
      const deletedId = sessionId.value
      await aiAssistantApi.deleteSession(deletedId)
      sessionId.value = null
      messages.value = []
      await loadSessions()
      if (!sessionId.value && projectId.value) {
        await handleNewSession()
      } else {
        await loadSessionFromServer()
      }
      ElMessage.success('会话已删除')
    } catch {
      /* cancelled */
    }
  }
}

const loadQuickPrompts = async () => {
  try {
    const res = await aiAssistantApi.getQuickPrompts()
    if (res.data?.code === 200) {
      quickPrompts.value = res.data.data?.items || []
    }
  } catch {
    quickPrompts.value = [
      { key: 'overview', label: '项目概览', message: '请总结当前项目的完整情况，包括环境、模块、需求和用例库规模。' },
      {
        key: 'loop_analyze',
        label: '失败闭环',
        message:
          '请做「失败分析闭环」：1）列出当前项目最近失败用例；2）查看最近接口套件/计划执行记录；3）在回复中写明可用于分析的 target_type 与 target_id（接口失败记录 ID）；4）若我已在本句给出 target，再发起 AI 失败分析预览（需我确认）；否则先出清单等我指定。若当前无失败，直接说明即可。'
      },
      {
        key: 'loop_run',
        label: '执行闭环',
        message:
          '请做「接口执行闭环」：1）列出当前项目的接口测试计划与测试环境；2）若页面上下文或本句已有计划 ID 与环境 ID，则预览执行该计划（需我确认）；否则先推荐一个可执行计划并说明还需哪项 ID。3）执行完成后我会收到回传；若有失败，我再点快捷「失败闭环」做分析。不要跳过确认直接执行。'
      },
      { key: 'failures', label: '最近失败', message: '列出当前项目最近的失败用例，并简要说明。' },
      { key: 'requirements', label: '需求列表', message: '当前项目有哪些需求文档？各有多少条已生成用例？' },
      { key: 'api_overview', label: '接口概览', message: '请汇总当前项目的接口分类、接口定义、接口测试用例和套件情况。' },
      { key: 'api_cases', label: '接口用例', message: '列出当前项目的接口测试用例，说明各用例关联的接口、方法与路径。' },
      { key: 'api_runs', label: '接口执行', message: '列出当前项目最近的接口套件与测试计划执行记录，并简要说明成功/失败情况。' },
      { key: 'ui_runs', label: 'UI 执行', message: '列出当前项目最近的 UI 测试计划执行记录，说明通过率与失败数。' },
      { key: 'perf', label: '压测概览', message: '当前项目有哪些压测场景？最近一次压测的 QPS 和响应时间如何？' },
      { key: 'ui', label: 'UI 计划', message: '当前项目有哪些 UI 测试计划和 Web 用例？' }
    ]
  }
}

const formatImpact = (pending) => {
  const impact = pending?.impact || {}
  const lines = []
  if (impact.warning) lines.push(impact.warning)
  if (impact.plan_name || impact.plan_id != null) {
    const isApp = impact.driver_mode != null && !impact.scene_id
    const prefix = isApp ? 'App 计划' : '接口测试计划'
    const idKey = isApp ? 'app_plan_id' : 'plan_id'
    lines.push(`${prefix}：${impact.plan_name || '未命名'} (${idKey}=${impact.plan_id})`)
  }
  if (impact.scene_name || impact.scene_id != null) {
    lines.push(`压测场景：${impact.scene_name || '未命名'} (scene_id=${impact.scene_id})`)
  }
  if (impact.suite_name || impact.suite_id != null) {
    const prefix = impact.driver_mode != null
      ? 'App 套件'
      : impact.device_id != null
        ? 'Web UI 套件'
        : '接口套件'
    const idKey = impact.driver_mode != null ? 'app_suite_id' : 'suite_id'
    lines.push(`${prefix}：${impact.suite_name || '未命名'} (${idKey}=${impact.suite_id})`)
  }
  if (impact.task_name || impact.task_id != null) {
    lines.push(`UI 计划：${impact.task_name || '未命名'} (task_id=${impact.task_id})`)
  }
  if (impact.requirement_name || impact.requirement_id != null) {
    lines.push(`需求：${impact.requirement_name || '未命名'} (requirement_id=${impact.requirement_id})`)
  }
  if (impact.env_name) lines.push(`环境：${impact.env_name}`)
  if (impact.device_id) lines.push(`Runner 设备：${impact.device_id}`)
  if (impact.case_count != null) lines.push(`用例数：${impact.case_count}`)
  if (impact.case_name || impact.case_id != null) {
    let prefix = '接口用例'
    let idKey = 'case_id'
    if (impact.driver_mode != null) {
      prefix = 'App 用例'
      idKey = 'app_case_id'
    } else if (impact.device_id != null && impact.step_count != null) {
      prefix = 'Web UI 用例'
      idKey = 'ui_case_id'
    }
    lines.push(`${prefix}：${impact.case_name || '未命名'} (${idKey}=${impact.case_id})`)
  }
  if (impact.step_count != null) lines.push(`步骤数：${impact.step_count}`)
  if (impact.data_driven != null) lines.push(`数据驱动：${impact.data_driven ? '是' : '否'}`)
  if (impact.set_name || impact.set_id != null) {
    lines.push(`问答评测集：${impact.set_name || '未命名'} (set_id=${impact.set_id})`)
  }
  if (impact.run_mode_label) lines.push(`评测模式：${impact.run_mode_label}`)
  if (impact.case_scope_label) lines.push(`用例范围：${impact.case_scope_label}`)
  if (impact.target_name || impact.target_id != null) {
    lines.push(`被测 API：${impact.target_name || '未命名'} (target_id=${impact.target_id})`)
  }
  if (impact.item_count != null) lines.push(`计划项/场景项：${impact.item_count}`)
  if (impact.requires_worker != null) {
    lines.push(`需在线压测 Worker：${impact.requires_worker ? '是' : '否'}`)
  }
  if (impact.online_workers != null) lines.push(`当前在线 Worker：${impact.online_workers}`)
  if (impact.use_workers != null) lines.push(`（已废弃）use_workers=${impact.use_workers}`)
  if (impact.target_type && impact.target_id != null) {
    lines.push(`分析目标：${impact.target_type} (target_id=${impact.target_id})`)
  }
  if (impact.existing_cases != null) lines.push(`已有用例：${impact.existing_cases}`)
  if (impact.planned_batch_count != null) lines.push(`计划生成：${impact.planned_batch_count} 条`)
  if (pending?.expires_in_seconds) lines.push(`确认有效期：${pending.expires_in_seconds} 秒`)
  return lines.length ? lines.join('\n') : '请确认是否执行该操作'
}

const revealStreaming = async (msgIndex, fullContent) => {
  const step = 12
  messages.value[msgIndex].streaming = true
  messages.value[msgIndex].content = ''
  for (let i = 0; i <= fullContent.length; i += step) {
    messages.value[msgIndex].content = fullContent.slice(0, i)
    await scrollToBottom()
    await new Promise((r) => setTimeout(r, 18))
  }
  messages.value[msgIndex].streaming = false
  messages.value[msgIndex].content = fullContent
}

const sendQuick = (text) => {
  inputText.value = text
  sendMessage()
}

const clearChat = async () => {
  messages.value = []
  statusText.value = ''
  try {
    await aiAssistantApi.clearSession(projectId.value, sessionId.value)
  } catch {
    /* ignore */
  }
}

const ensureSession = async () => {
  if (sessionId.value || !projectId.value) return
  const res = await aiAssistantApi.createSession(projectId.value)
  if (res.data?.code === 200) {
    sessionId.value = res.data.data?.id || null
    await loadSessions(sessionId.value)
  }
}

const sendMessage = async () => {
  const text = inputText.value.trim()
  if (!text || loading.value) return
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }

  try {
    await ensureSession()
  } catch {
    ElMessage.error('无法创建会话')
    return
  }

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  loading.value = true
  statusText.value = '正在查询平台数据并生成回答（最多约 5 分钟）…'
  scrollToBottom()

  try {
    const res = await aiAssistantApi.chat(text, {
      projectId: projectId.value,
      sessionId: sessionId.value,
      useServerHistory: true,
      pageContext: pageContext.value
    })
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      sessionId.value = d.session_id || sessionId.value
      const msg = {
        role: 'assistant',
        content: d.content || '（无内容）',
        tools: d.tools_used || [],
        pending_confirm: d.pending_confirm || null,
        confirm_done: false,
        streaming: false
      }
      messages.value.push(msg)
      const idx = messages.value.length - 1
      if (d.content && !d.pending_confirm) {
        await revealStreaming(idx, d.content)
      }
      await loadSessions(sessionId.value)
    } else {
      throw new Error(res.data?.message || '请求失败')
    }
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.data?.detail || e?.message || '助手请求失败'
    ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    messages.value.push({ role: 'assistant', content: `请求失败：${msg}` })
  } finally {
    loading.value = false
    statusText.value = ''
    scrollToBottom()
  }
}

const handleConfirm = async (msg, idx) => {
  const pending = msg.pending_confirm
  if (!pending?.confirm_token) return
  confirmLoading.value = idx
  try {
    const res = await aiAssistantApi.confirm({
      action: pending.action,
      confirmToken: pending.confirm_token,
      confirmArgs: pending.confirm_args || {},
      projectId: projectId.value,
      sessionId: sessionId.value
    })
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      sessionId.value = d.session_id || sessionId.value
      msg.confirm_done = true
      msg.pending_confirm = null
      const baselineCount = messages.value.length + 1
      messages.value.push({
        role: 'assistant',
        content: d.content || '操作已完成',
        tools: [`confirm:${pending.action}`],
        streaming: false
      })
      if (d.execution_watch) {
        startExecutionWatch(baselineCount)
      }
      ElMessage.success('操作已执行')
      await scrollToBottom()
    } else {
      throw new Error(res.data?.message || '确认失败')
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.message || '确认执行失败'
    ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  } finally {
    confirmLoading.value = -1
  }
}

const cancelConfirm = (msg) => {
  msg.confirm_done = true
  msg.pending_confirm = null
  messages.value.push({
    role: 'assistant',
    content: '已取消该操作。',
    streaming: false
  })
  scrollToBottom()
}

watch(panelOpen, (open) => {
  if (open) {
    if (!posInitialized.value) initPanelPosition()
    scrollToBottom()
  }
})

watch(projectId, () => {
  sessionId.value = null
  sessionKeyword.value = ''
  loadSessionFromServer()
  scrollToBottom()
})

watch(sessionKeyword, () => {
  if (sessionSearchTimer) clearTimeout(sessionSearchTimer)
  sessionSearchTimer = setTimeout(() => {
    loadSessions(sessionId.value)
  }, 300)
})

onMounted(() => {
  window.addEventListener('resize', onWindowResize)
  if (visible.value) {
    loadQuickPrompts()
    loadSessionFromServer()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onWindowResize)
  onDragEnd()
  onResizeEnd()
  stopExecutionWatch()
})
</script>

<style scoped lang="scss">
.platform-assistant {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2000;
  pointer-events: none;

  .assistant-fab {
    pointer-events: auto;
  }
}

.assistant-fab {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  background: linear-gradient(145deg, #fff7e6, #ffe7ba);
  box-shadow: 0 4px 16px rgba(245, 166, 35, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s, opacity 0.2s;
  padding: 4px;

  &:hover {
    transform: scale(1.06);
  }

  &.fab-hidden {
    opacity: 0;
    pointer-events: none;
    transform: scale(0.8);
  }
}

.assistant-panel {
  position: fixed;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
  border: 1px solid var(--el-border-color-lighter);
  overflow: hidden;
  pointer-events: auto;

  &.maximized {
    border-radius: 10px;
  }
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-light);
  cursor: move;
  user-select: none;
  flex-shrink: 0;

  .header-left {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .panel-title {
    font-weight: 600;
    font-size: 15px;
    white-space: nowrap;
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 4px;
    cursor: default;
  }

  .icon-btn {
    width: 28px;
    height: 28px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: var(--el-text-color-regular);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;

    &:hover {
      background: var(--el-fill-color);
      color: var(--el-color-primary);
    }

    &.close-btn:hover {
      color: var(--el-color-danger);
    }
  }
}

.panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 14px 14px;
  overflow: hidden;
}

.resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  background: linear-gradient(135deg, transparent 50%, var(--el-border-color) 50%);
  opacity: 0.6;
}

.session-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-shrink: 0;

  .session-select {
    flex: 1;
    min-width: 0;
  }
}

.session-search {
  margin-bottom: 8px;
  flex-shrink: 0;
}

.assistant-meta {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;

  .meta-warn {
    color: #e6a23c;
  }

  .page-ctx-tag {
    max-width: 100%;
  }
}

.quick-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
  flex-shrink: 0;
  max-height: 72px;
  overflow-y: auto;
}

.message-box {
  flex: 1;
  min-height: 100px;
  overflow-y: auto;
  padding: 8px 4px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  margin-bottom: 10px;
}

.empty-hint {
  color: #909399;
  font-size: 13px;
  line-height: 1.5;
  padding: 12px;
}

.message-item {
  margin-bottom: 10px;

  &.user .message-content {
    background: #ecf5ff;
  }

  &.assistant .message-content,
  &.assistant .assistant-md {
    background: #f4f4f5;
    border-radius: 8px;
  }
}

.assistant-md {
  padding: 2px 4px;

  :deep(.markdown-report.compact) {
    padding: 4px 6px;
  }

  :deep(a.md-link) {
    color: #409eff;
    text-decoration: none;
    border-bottom: 1px dashed rgba(64, 158, 255, 0.45);
  }

  :deep(a.md-link:hover) {
    color: #66b1ff;
  }
}

.message-role {
  font-size: 12px;
  color: #909399;
  margin-bottom: 3px;
}

.message-content {
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.55;
  word-break: break-word;

  &.user-text {
    white-space: pre-wrap;
  }
}

.message-tools {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.confirm-card {
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px solid #e6a23c;
  border-radius: 8px;
  background: #fdf6ec;

  .confirm-title {
    font-size: 13px;
    font-weight: 600;
    color: #e6a23c;
    margin-bottom: 6px;
  }

  .confirm-impact {
    margin-bottom: 8px;
    color: #606266;
  }

  .confirm-actions {
    display: flex;
    gap: 8px;
  }
}

.tool-status {
  font-size: 12px;
  color: #e6a23c;
  padding: 8px 10px;
  background: #f4f4f5;
  border-radius: 8px;
}

.streaming .cursor {
  animation: blink 1s step-end infinite;
  color: #409eff;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.input-area {
  flex-shrink: 0;

  .input-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 8px;
  }
}

html.dark {
  .message-item.user .message-content {
    background: #1d3a5f;
  }

  .message-item.assistant .message-content,
  .message-item.assistant .assistant-md,
  .tool-status {
    background: #2b2b2c;
  }

  .assistant-fab {
    background: linear-gradient(145deg, #3d3520, #2b2418);
  }

  .confirm-card {
    background: #3d3520;
    border-color: #e6a23c;
  }

  .assistant-md :deep(.md-table th) {
    background: #1d1d1d;
  }

  .assistant-md :deep(.md-table tr:nth-child(even) td) {
    background: #262626;
  }
}
</style>
