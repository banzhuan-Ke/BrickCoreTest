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
          </div>
          <div class="header-actions" @mousedown.stop>
            <el-tooltip content="项目记忆" placement="bottom">
              <button
                type="button"
                class="icon-btn"
                :disabled="!projectId"
                @click="openMemoryDrawer"
              >
                <el-icon><Notebook /></el-icon>
              </button>
            </el-tooltip>
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
                  <el-dropdown-item command="clear">清空会话（含摘要与钉住）</el-dropdown-item>
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

          <AssistantPinBar
            :items="pinnedItems"
            :pin-candidate="pinCandidate"
            :disabled="loading || !projectId"
            @unpin="handleUnpin"
            @pin-page="handlePinPage"
          />

          <div v-if="sessionJobs.length" class="session-jobs">
            <div class="session-jobs-title">进行中的任务</div>
            <AssistantJobProgressCard
              v-for="job in sessionJobs"
              :key="job.link_id || job.id"
              :card="job.card || job"
              :cancelling="cancellingLinkId === (job.link_id || job.id)"
              @cancel="handleJobCancel"
            />
          </div>

          <div class="quick-chips">
            <span v-if="skillChips.length" class="quick-chips-label">技能快捷入口</span>
            <el-button
              v-for="item in skillChips"
              :key="item.key"
              size="small"
              round
              type="warning"
              plain
              :disabled="loading"
              @click="sendSkillChip(item)"
            >
              {{ item.label }}
            </el-button>
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
              <div v-if="msg.role === 'assistant'" class="message-path" v-show="msg.mode || msg.skills?.length">
                <el-tag v-if="msg.mode" size="small" type="info">Agent · {{ msg.mode }}</el-tag>
                <el-tag v-for="s in (msg.skills || [])" :key="s" size="small" type="warning">{{ s }}</el-tag>
              </div>
              <div v-if="msg.role === 'assistant'" class="message-content assistant-md">
                <details v-if="msg.thinking" class="assistant-thinking">
                  <summary>思考过程</summary>
                  <pre class="thinking-body">{{ msg.thinking }}</pre>
                </details>
                <MarkdownReport compact :content="linkifyAssistantContent(msg.content)" />
                <span v-if="msg.streaming" class="cursor">▍</span>
              </div>
              <div v-else class="message-content user-text">{{ msg.content }}</div>
              <div v-if="msg.tools?.length" class="message-tools">
                <el-tag v-for="t in msg.tools" :key="t" size="small" type="success">{{ t }}</el-tag>
              </div>
              <div
                v-if="msg.role === 'assistant' && msg.message_id && !msg.streaming"
                class="message-feedback"
              >
                <el-button
                  size="small"
                  text
                  :type="msg.feedbackScore === 1 ? 'success' : 'default'"
                  :disabled="!!msg.feedbackScore || feedbackLoadingId === msg.message_id"
                  @click="handleFeedback(msg, 1)"
                >
                  有用
                </el-button>
                <el-button
                  size="small"
                  text
                  :type="msg.feedbackScore === -1 ? 'danger' : 'default'"
                  :disabled="!!msg.feedbackScore || feedbackLoadingId === msg.message_id"
                  @click="handleFeedback(msg, -1)"
                >
                  不准
                </el-button>
              </div>
              <div
                v-if="effectivePendingConfirm(msg) && !msg.confirm_done && !hasOpenAsk(msg)"
                class="confirm-card"
              >
                <div class="confirm-title">待确认操作</div>
                <div class="confirm-impact assistant-md">
                  <MarkdownReport
                    compact
                    :content="linkifyAssistantContent(formatImpact(effectivePendingConfirm(msg)))"
                  />
                </div>
                <div class="confirm-actions">
                  <el-button
                    type="primary"
                    size="small"
                    :loading="confirmLoading === idx || loading"
                    :disabled="loading"
                    @click="handleConfirm(msg, idx)"
                  >
                    确认执行
                  </el-button>
                  <el-button
                    size="small"
                    :disabled="confirmLoading === idx || loading"
                    @click="cancelConfirm(msg)"
                  >
                    取消
                  </el-button>
                </div>
              </div>
              <AssistantCardList
                v-if="msg.role === 'assistant' && visibleCards(msg).length"
                :cards="visibleCards(msg)"
                :ask-done="!!msg.ask_user_done"
                :ask-loading="askLoading === idx"
                :skill-labels="SKILL_LABELS"
                :cancelling-link-id="cancellingLinkId"
                @ask-submit="(card, answers) => handleAskSubmit(msg, idx, card, answers)"
                @ask-cancel="() => cancelAskUser(msg)"
                @job-cancel="handleJobCancel"
              />
              <AssistantAskUserCard
                v-else-if="msg.pending_ask_user && !msg.ask_user_done"
                :card="msg.pending_ask_user"
                :loading="askLoading === idx"
                @submit="(answers) => handleAskSubmit(msg, idx, msg.pending_ask_user, answers)"
                @cancel="() => cancelAskUser(msg)"
              />
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

      <el-drawer
        v-model="memoryDrawerOpen"
        title="项目记忆"
        size="360px"
        append-to-body
        :close-on-click-modal="true"
      >
        <p class="memory-hint">
          仅对当前账号 + 当前项目生效，会注入标准模式对话上下文。不要写入密码、Token 等敏感信息。
        </p>
        <div class="memory-form">
          <el-input v-model="memoryForm.key" size="small" maxlength="64" placeholder="键，如：默认环境" />
          <el-input
            v-model="memoryForm.value"
            type="textarea"
            :rows="2"
            size="small"
            maxlength="2000"
            show-word-limit
            placeholder="值，如：测试环境 A"
          />
          <div class="memory-form-actions">
            <el-button size="small" type="primary" :loading="memorySaving" @click="saveMemoryItem">
              保存
            </el-button>
            <el-button
              size="small"
              type="danger"
              plain
              :disabled="!memoryItems.length || memoryLoading"
              @click="clearAllMemory"
            >
              全部清空
            </el-button>
          </div>
        </div>
        <div v-loading="memoryLoading" class="memory-list">
          <el-empty v-if="!memoryItems.length" description="暂无记忆" :image-size="64" />
          <div v-for="item in memoryItems" :key="item.key" class="memory-item" @click="editMemoryItem(item)">
            <div class="memory-item-head">
              <span class="memory-key">{{ item.key }}</span>
              <el-button size="small" text type="danger" @click.stop="removeMemoryItem(item.key)">删除</el-button>
            </div>
            <div class="memory-value">{{ item.value }}</div>
          </div>
        </div>
      </el-drawer>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, CopyDocument, FullScreen, Notebook } from '@element-plus/icons-vue'
import { aiAssistantApi } from '@/api/modules/ai_assistant.js'
import { UserStore } from '@/stores/module/UserStore.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import AssistantMascot from '@/components/AssistantMascot.vue'
import MarkdownReport from '@/components/MarkdownReport.vue'
import AssistantPinBar from '@/components/assistant/AssistantPinBar.vue'
import AssistantCardList from '@/components/assistant/AssistantCardList.vue'
import AssistantAskUserCard from '@/components/assistant/AssistantAskUserCard.vue'
import AssistantJobProgressCard from '@/components/assistant/AssistantJobProgressCard.vue'
import {
  buildAssistantPageContext,
  formatPageContextLabel,
  pinCandidateFromPageContext
} from '@/utils/assistantPageContext.js'
import { linkifyAssistantContent } from '@/utils/assistantLinkify.js'
import { ASSISTANT_OPEN_SKILL_EVENT } from '@/utils/assistantBridge.js'

const ASSISTANT_NAME = '小测'

const uStore = UserStore()
const proStore = ProjectStore()
const route = useRoute()
const router = useRouter()

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
const feedbackLoadingId = ref('')
const memoryDrawerOpen = ref(false)
const memoryLoading = ref(false)
const memorySaving = ref(false)
const memoryItems = ref([])
const memoryForm = ref({ key: '', value: '' })
const askLoading = ref(-1)
const statusText = ref('')
const quickPrompts = ref([])
const skillChips = ref([])
const pinnedItems = ref([])
const sessionJobs = ref([])
const cancellingLinkId = ref(null)
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
const pinCandidate = computed(() => pinCandidateFromPageContext(pageContext.value))

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

const splitThinkingFromContent = (text) => {
  const raw = String(text || '')
  const parts = []
  const open = '<' + 'think>'
  const close = '</' + 'think>'
  const openAlt = '<' + 'redacted_reasoning>'
  const closeAlt = '</' + 'redacted_reasoning>'
  const closedRe = new RegExp(
    `${open}([\\s\\S]*?)${close}|${openAlt}([\\s\\S]*?)${closeAlt}`,
    'gi'
  )
  let m
  while ((m = closedRe.exec(raw)) !== null) {
    const inner = (m[1] || m[2] || '').trim()
    if (inner) parts.push(inner)
  }
  let answer = raw
    .replace(closedRe, '')
    .replace(/<\/?result>/gi, '')
    .trim()
  // 未闭合思考（输出截断）：从 open 到文末整段归思考，勿进正文
  const trailRe = new RegExp(`(${open}|${openAlt})([\\s\\S]*)$`, 'i')
  const trail = trailRe.exec(answer)
  if (trail) {
    const inner = (trail[2] || '').trim()
    if (inner) parts.push(inner)
    answer = answer.slice(0, trail.index).trim()
  }
  return { thinking: parts.join('\n\n'), answer }
}

const SKILL_LABELS = {
  ui_failure_analysis: '失败分析',
  knowledge_qa: '资料库问答',
  project_health_digest: '项目健康摘要',
  requirement_to_test_points: '需求→测试点',
  api_definition_to_cases: '接口→用例',
  test_points_to_functional_cases: '测试点→用例',
  mock_response_generate: '生成 Mock',
  nl_to_sql_template: 'NL→SQL模板',
  perf_scene_from_nl: '一句话压测',
  browser_lab_to_ui_case: '浏览器→用例',
  ui_steps_from_nl: '自然语言 UI',
  report_narrative: '报告叙事',
  qa_eval_assist: '问答评测',
  curl_to_cases: 'curl→用例',
  ui_locator_suggest: '元素→定位'
}

const skillLabelsFromMsg = (m) => {
  const used = m.skills_used || m.skills || []
  const codes = []
  if (Array.isArray(used)) {
    used.forEach((item) => {
      if (typeof item === 'string' && item) codes.push(item)
      else if (item && typeof item === 'object' && (item.skill_code || item.code)) {
        codes.push(item.skill_code || item.code)
      }
    })
  }
  return [...new Set(codes)].map((c) => SKILL_LABELS[c] || c)
}

const normalizeAssistantPayload = (content, thinking) => {
  const split = splitThinkingFromContent(content)
  let answer = split.answer
  if (!answer) {
    answer = split.thinking
      ? '（回答未完成：模型输出在思考阶段被截断。请重试或换更短的问题。）'
      : (content || '')
    // 仍含 think 开标签时绝不回落原文
    if (/<(?:think|redacted_reasoning)>/i.test(answer)) {
      answer = '（模型未返回正文）'
    }
  }
  return {
    content: answer,
    thinking: (thinking || '').trim() || split.thinking
  }
}

const normalizeMessages = (items) => {
  if (!Array.isArray(items)) return []
  const mapped = items.map((m) => {
    const payload = normalizeAssistantPayload(m.content || '', m.thinking || '')
    return {
      role: m.role || 'assistant',
      content: payload.content,
      thinking: payload.thinking,
      tools: m.tools || [],
      skills: skillLabelsFromMsg(m),
      mode: m.mode || '',
      cards: Array.isArray(m.cards) ? m.cards : [],
      pending_confirm: m.pending_confirm || null,
      confirm_done: m.confirm_done || false,
      confirm_result: m.confirm_result || null,
      pending_ask_user: m.pending_ask_user || null,
      ask_user_done: m.ask_user_done || false,
      page_context: m.page_context || null,
      execution_follow_up: m.execution_follow_up || false,
      message_id: m.message_id || '',
      feedbackScore: m.feedbackScore || m.feedback_score || 0,
      streaming: false
    }
  })
  // 若后续消息带 confirm_result.confirm_token，反推同 token 的卡已完成（兼容旧会话）
  const doneTokens = new Set()
  for (const m of mapped) {
    const cr = m.confirm_result
    if (cr?.confirm_token) doneTokens.add(String(cr.confirm_token))
  }
  for (const m of mapped) {
    if (m.confirm_done || !m.pending_confirm?.confirm_token) continue
    if (doneTokens.has(String(m.pending_confirm.confirm_token))) {
      m.confirm_done = true
    }
  }
  return mapped
}

const hasOpenAsk = (msg) =>
  !!(msg?.pending_ask_user && !msg.ask_user_done) ||
  (!msg?.ask_user_done && (msg?.cards || []).some((c) => c?.type === 'ask_user'))

/** 兼容仅 cards 含 confirm、无 pending_confirm 的历史 */
const effectivePendingConfirm = (msg) => {
  if (msg?.pending_confirm) return msg.pending_confirm
  const card = (msg?.cards || []).find((c) => c?.type === 'confirm')
  return card || null
}

/** 组装展示用 cards：缺 ask 时用 pending_ask_user 补上；有未完成 ask 时隐藏 confirm 卡避免双交互 */
const visibleCards = (msg) => {
  const cards = Array.isArray(msg?.cards) ? [...msg.cards] : []
  if (
    msg?.pending_ask_user &&
    !msg.ask_user_done &&
    !cards.some((c) => c?.type === 'ask_user')
  ) {
    // 复用同一对象引用，避免每次渲染 spread 新对象触发 AskUser 表单重建
    const ask = msg.pending_ask_user
    if (ask.type !== 'ask_user') ask.type = 'ask_user'
    cards.unshift(ask)
  }
  if (hasOpenAsk(msg)) {
    return cards.filter((c) => c?.type !== 'confirm')
  }
  return cards
}

const applyPinnedFromPayload = (data) => {
  const pinned = data?.pinned_context
  if (pinned && Array.isArray(pinned.items)) {
    pinnedItems.value = pinned.items
  }
}

const sameGeneration = (reqSessionId, reqProjectId) =>
  sessionId.value === reqSessionId && projectId.value === reqProjectId

let executionWatchTimer = null
let executionWatchBound = null

const stopExecutionWatch = () => {
  if (executionWatchTimer) {
    clearInterval(executionWatchTimer)
    executionWatchTimer = null
  }
  executionWatchBound = null
}

let jobPollTimer = null
let jobPollBound = null

const JOB_ACTIVE = new Set(['pending', 'running'])

const stopJobPoll = () => {
  if (jobPollTimer) {
    clearInterval(jobPollTimer)
    jobPollTimer = null
  }
  jobPollBound = null
}

const refreshSessionJobs = async (boundSessionId, boundProjectId, { reloadMessages = false } = {}) => {
  if (!boundSessionId) {
    sessionJobs.value = []
    return []
  }
  try {
    const res = await aiAssistantApi.listJobs(boundSessionId, boundProjectId, true)
    if (!sameGeneration(boundSessionId, boundProjectId)) return []
    if (res.data?.code !== 200) return []
    const items = res.data.data?.items || []
    const canCancel = uStore.hasPermission('ai_test:execute')
    sessionJobs.value = items
      .filter((j) => JOB_ACTIVE.has(String(j.status || '').toLowerCase()))
      .map((j) => {
        const card = { ...(j.card || j) }
        card.can_cancel = Boolean(card.can_cancel) && canCancel
        return { ...j, card }
      })
    if (reloadMessages) {
      await loadSessionFromServer()
    }
    return items
  } catch {
    return []
  }
}

const startJobPoll = (boundSessionId, boundProjectId) => {
  stopJobPoll()
  if (!boundSessionId) return
  jobPollBound = { sessionId: boundSessionId, projectId: boundProjectId }
  let attempts = 0
  const tick = async () => {
    attempts += 1
    const bound = jobPollBound
    if (
      attempts > 200 ||
      !bound ||
      !sameGeneration(bound.sessionId, bound.projectId)
    ) {
      stopJobPoll()
      return
    }
    const baseline = messages.value.length
    const items = await refreshSessionJobs(bound.sessionId, bound.projectId)
    if (!sameGeneration(bound.sessionId, bound.projectId)) {
      stopJobPoll()
      return
    }
    const active = (items || []).some((j) => JOB_ACTIVE.has(String(j.status || '').toLowerCase()))
    if (!active) {
      // 终态可能已写入 follow-up，刷新消息
      if (items?.length) {
        await loadSessionFromServer()
        if (messages.value.length > baseline) {
          statusText.value = ''
          ElMessage.success('任务结果已更新')
          scrollToBottom()
        }
      }
      stopJobPoll()
      return
    }
    statusText.value = statusText.value || '智能浏览器任务执行中…'
  }
  tick()
  jobPollTimer = setInterval(tick, 3000)
}

const startExecutionWatch = (baselineCount, boundSessionId, boundProjectId) => {
  stopExecutionWatch()
  executionWatchBound = { sessionId: boundSessionId, projectId: boundProjectId }
  statusText.value = '任务执行中，完成后将自动更新结果…'
  let attempts = 0
  executionWatchTimer = setInterval(async () => {
    attempts += 1
    const bound = executionWatchBound
    if (
      attempts > 120 ||
      !bound ||
      !sameGeneration(bound.sessionId, bound.projectId)
    ) {
      stopExecutionWatch()
      if (bound && sameGeneration(bound.sessionId, bound.projectId)) {
        statusText.value = ''
      }
      return
    }
    try {
      const res = await aiAssistantApi.getSession(bound.projectId, bound.sessionId)
      if (!sameGeneration(bound.sessionId, bound.projectId)) {
        stopExecutionWatch()
        return
      }
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
    pinnedItems.value = []
    sessionJobs.value = []
    return
  }
  await loadSessions(sessionId.value)
  if (!sessionId.value) {
    messages.value = []
    pinnedItems.value = []
    sessionJobs.value = []
    return
  }
  try {
    const res = await aiAssistantApi.getSession(projectId.value, sessionId.value)
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      sessionId.value = d.session_id || sessionId.value
      messages.value = normalizeMessages(d.messages)
      applyPinnedFromPayload(d)
    } else {
      messages.value = []
      pinnedItems.value = []
    }
  } catch {
    messages.value = []
    pinnedItems.value = []
  }
}

const switchSession = async () => {
  stopExecutionWatch()
  stopJobPoll()
  statusText.value = ''
  loading.value = false
  askLoading.value = -1
  confirmLoading.value = -1
  sessionJobs.value = []
  await loadSessionFromServer()
  if (sessionId.value) {
    startJobPoll(sessionId.value, projectId.value)
  }
  scrollToBottom()
}

const handleJobCancel = async (card) => {
  const linkId = card?.link_id || card?.id
  if (!linkId) return
  cancellingLinkId.value = linkId
  try {
    const res = await aiAssistantApi.cancelJob(linkId)
    if (res.data?.code === 200) {
      ElMessage.success('已请求停止')
      await refreshSessionJobs(sessionId.value, projectId.value, { reloadMessages: true })
    } else {
      throw new Error(res.data?.message || '停止失败')
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.message || '停止失败'
    ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  } finally {
    cancellingLinkId.value = null
  }
}

const handleFeedback = async (msg, score) => {
  const mid = msg?.message_id
  if (!mid || !sessionId.value || msg.feedbackScore) return
  feedbackLoadingId.value = mid
  try {
    const res = await aiAssistantApi.postFeedback({
      sessionId: sessionId.value,
      messageId: mid,
      score,
      projectId: projectId.value
    })
    if (res.data?.code === 200) {
      const i = messages.value.findIndex((m) => m.message_id === mid)
      if (i >= 0) {
        messages.value[i] = { ...messages.value[i], feedbackScore: score }
      }
      ElMessage.success(score === 1 ? '已标记有用' : '已记录反馈')
    } else {
      throw new Error(res.data?.message || '反馈失败')
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.data?.message || e?.message || '反馈失败'
    ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  } finally {
    feedbackLoadingId.value = ''
  }
}

const openMemoryDrawer = async () => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  memoryDrawerOpen.value = true
  await loadMemoryItems()
}

const editMemoryItem = (item) => {
  if (!item) return
  memoryForm.value = {
    key: item.key || '',
    value: item.value || ''
  }
}

const loadMemoryItems = async () => {
  if (!projectId.value) {
    memoryItems.value = []
    return
  }
  memoryLoading.value = true
  try {
    const res = await aiAssistantApi.listMemory(projectId.value)
    if (res.data?.code === 200) {
      memoryItems.value = res.data.data?.items || []
    } else {
      memoryItems.value = []
    }
  } catch {
    memoryItems.value = []
    ElMessage.error('加载记忆失败')
  } finally {
    memoryLoading.value = false
  }
}

const saveMemoryItem = async () => {
  const key = (memoryForm.value.key || '').trim()
  const value = (memoryForm.value.value || '').trim()
  if (!key || !value) {
    ElMessage.warning('请填写键和值')
    return
  }
  if (!projectId.value) return
  memorySaving.value = true
  try {
    const res = await aiAssistantApi.putMemory({
      projectId: projectId.value,
      key,
      value
    })
    if (res.data?.code === 200) {
      ElMessage.success('已保存')
      memoryForm.value = { key: '', value: '' }
      await loadMemoryItems()
    } else {
      throw new Error(res.data?.message || '保存失败')
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.message || '保存失败'
    ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  } finally {
    memorySaving.value = false
  }
}

const removeMemoryItem = async (key) => {
  if (!projectId.value || !key) return
  try {
    await ElMessageBox.confirm(`删除记忆「${key}」？`, '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    const res = await aiAssistantApi.deleteMemory(projectId.value, key)
    if (res.data?.code === 200) {
      ElMessage.success('已删除')
      await loadMemoryItems()
    } else {
      throw new Error(res.data?.message || '删除失败')
    }
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    const detail = e?.response?.data?.detail || e?.message || '删除失败'
    ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
}

const clearAllMemory = async () => {
  if (!projectId.value) return
  try {
    await ElMessageBox.confirm('清空当前项目下全部记忆？此操作不可恢复。', '确认清空', {
      type: 'warning',
      confirmButtonText: '清空'
    })
  } catch {
    return
  }
  try {
    const res = await aiAssistantApi.clearMemory(projectId.value)
    if (res.data?.code === 200) {
      ElMessage.success('已清空')
      memoryItems.value = []
    } else {
      throw new Error(res.data?.message || '清空失败')
    }
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    const detail = e?.response?.data?.detail || e?.message || '清空失败'
    ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
}

const handleNewSession = async () => {
  if (!projectId.value) return
  stopExecutionWatch()
  stopJobPoll()
  sessionJobs.value = []
  try {
    const res = await aiAssistantApi.createSession(projectId.value)
    if (res.data?.code === 200) {
      const item = res.data.data
      await loadSessions(item?.id)
      sessionId.value = item?.id || sessionId.value
      messages.value = []
      pinnedItems.value = []
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
    try {
      await ElMessageBox.confirm(
        '将清空本会话的消息、摘要与钉住实体，下次对话不再带入旧上下文。',
        '清空会话',
        { type: 'warning', confirmButtonText: '清空' }
      )
    } catch {
      return
    }
    await clearChat()
    ElMessage.success('已清空会话')
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
      skillChips.value = res.data.data?.skill_chips || []
    }
  } catch {
    skillChips.value = []
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
  if (
    impact.api_name ||
    impact.api_definition_id != null ||
    impact.reuse_api_definition_id != null ||
    (impact.method && impact.path)
  ) {
    const methodPath = [impact.method, impact.path].filter(Boolean).join(' ')
    const reuseId = impact.reuse_api_definition_id
    const apiId = impact.api_definition_id ?? reuseId
    let idPart = ''
    if (reuseId != null && reuseId !== '') {
      idPart = ` (api_definition_id=${reuseId}，复用已有)`
    } else if (apiId != null && apiId !== '') {
      idPart = ` (api_definition_id=${apiId})`
    } else {
      idPart = ' （确认后新建接口定义）'
    }
    lines.push(
      `接口：${impact.api_name || '未命名'}${methodPath ? ` ${methodPath}` : ''}${idPart}`
    )
  }
  if (impact.preview_count != null) lines.push(`预览条数：${impact.preview_count}`)
  if (Array.isArray(impact.sample_titles) && impact.sample_titles.length) {
    lines.push(`测试点示例：${impact.sample_titles.slice(0, 5).join('；')}`)
  }
  if (Array.isArray(impact.sample_names) && impact.sample_names.length) {
    lines.push(`用例示例：${impact.sample_names.slice(0, 5).join('；')}`)
  }
  if (impact.navigate) lines.push(`确认后将打开：${impact.navigate}`)
  if (impact.env_name) lines.push(`环境：${impact.env_name}`)
  if (impact.task_text) lines.push(`探索任务：${impact.task_text}`)
  if (impact.start_url) lines.push(`起始 URL：${impact.start_url}`)
  if (impact.device_name || impact.device_id) {
    lines.push(
      `Runner 设备：${impact.device_name || impact.device_id}${
        impact.device_online === false ? '（当前不在线）' : ''
      }`
    )
  }
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

const sendSkillChip = async (item) => {
  if (!item?.key && !item?.message) return
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (item.direct_form) {
    if (item.hint) ElMessage.info(item.hint)
    loading.value = true
    statusText.value = '正在打开补充信息…'
    let prepared = false
    try {
      await ensureSession()
      const reqSessionId = sessionId.value
      const reqProjectId = projectId.value
      const res = await aiAssistantApi.prepareSkillChipForm({
        chipKey: item.key,
        projectId: reqProjectId,
        sessionId: reqSessionId,
        chipLabel: item.label || '',
        chipMessage: item.message || '',
        pageContext: pageContext.value || null
      })
      if (!sameGeneration(reqSessionId, reqProjectId)) return
      if (res.data?.code !== 200) {
        throw new Error(res.data?.message || '打开表单失败')
      }
      prepared = true
      const d = res.data.data || {}
      if (d.session_id) sessionId.value = d.session_id
      try {
        await loadSessionFromServer()
      } catch (loadErr) {
        // prepare 已落库：用返回体补齐，避免再走快捷消息造成双份意图
        if (d.user_message || d.assistant_message) {
          const extras = []
          if (d.user_message) extras.push(d.user_message)
          if (d.assistant_message) extras.push(d.assistant_message)
          messages.value = normalizeMessages([...(messages.value || []), ...extras])
        } else {
          throw loadErr
        }
      }
      await loadSessions(sessionId.value)
      await scrollToBottom()
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || '打开表单失败'
      ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
      // 仅 prepare 未成功时降级原快捷消息，避免已落库后再空转一轮
      if (!prepared && item.message) sendQuick(item.message)
    } finally {
      loading.value = false
      statusText.value = ''
    }
    return
  }
  if (!item?.message) return
  if (item.hint) ElMessage.info(item.hint)
  sendQuick(item.message)
}

/** skill_code → Chip；无 Chip 时降级话术（清单「快速使用」） */
const SKILL_CODE_FALLBACK_MESSAGE = {
  knowledge_qa: '',
  platform_how_to: '',
  project_health_digest:
    '请调用 run_skill(skill_code=project_health_digest) 生成当前项目健康摘要（环境、需求/用例规模、近期失败与定时任务）。'
}

const openPanel = () => {
  panelOpen.value = true
  if (!posInitialized.value) initPanelPosition()
}

const handleAssistantOpenSkill = async (ev) => {
  if (!visible.value) return
  const skillCode = String(ev?.detail?.skillCode || '').trim()
  if (!skillCode) return
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (loading.value) {
    ElMessage.warning('小测正在处理中，请稍后再试')
    return
  }
  openPanel()
  if (!skillChips.value.length) {
    await loadQuickPrompts()
  }
  const chip = (skillChips.value || []).find((c) => c.skill_code === skillCode)
  if (chip) {
    await sendSkillChip(chip)
    return
  }
  if (skillCode === 'knowledge_qa') {
    inputText.value = ''
    ElMessage.info('请输入要向资料库提问的内容后发送；小测将优先走资料库问答。')
    await nextTick()
    return
  }
  if (skillCode === 'platform_how_to') {
    inputText.value = ''
    ElMessage.info('请输入想了解的平台功能或技能（例如：失败分析怎么用），发送后将优先走「平台怎么用」。')
    await nextTick()
    return
  }
  const fallback = SKILL_CODE_FALLBACK_MESSAGE[skillCode]
  if (fallback) {
    sendQuick(fallback)
    return
  }
  const name = ev?.detail?.skillName || skillCode
  sendQuick(`请使用技能「${name}」（skill_code=${skillCode}）继续，缺参数时用选择卡让我补充。`)
}

const handlePinPage = async (candidate) => {
  if (!candidate || !projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  try {
    await ensureSession()
    if (!sessionId.value) {
      ElMessage.error('无法创建会话')
      return
    }
    const reqSessionId = sessionId.value
    const reqProjectId = projectId.value
    const res = await aiAssistantApi.pinContext({
      sessionId: reqSessionId,
      projectId: reqProjectId,
      entityType: candidate.type,
      entityId: candidate.id,
      label: candidate.label
    })
    if (!sameGeneration(reqSessionId, reqProjectId)) return
    if (res.data?.code === 200) {
      applyPinnedFromPayload(res.data.data)
      ElMessage.success('已钉住当前页实体')
    } else {
      throw new Error(res.data?.message || '钉住失败')
    }
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '钉住失败'
    ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
}

const handleUnpin = async (item) => {
  if (!item || !sessionId.value) return
  const reqSessionId = sessionId.value
  const reqProjectId = projectId.value
  try {
    const res = await aiAssistantApi.unpinContext({
      sessionId: reqSessionId,
      projectId: reqProjectId,
      entityType: item.type,
      entityId: item.id
    })
    if (!sameGeneration(reqSessionId, reqProjectId)) return
    if (res.data?.code === 200) {
      applyPinnedFromPayload(res.data.data)
    }
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '取消钉住失败'
    ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
}

const clearChat = async () => {
  stopJobPoll()
  sessionJobs.value = []
  messages.value = []
  pinnedItems.value = []
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

  const reqSessionId = sessionId.value
  const reqProjectId = projectId.value

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  loading.value = true
  statusText.value = '正在查询平台数据并生成回答（最多约 5 分钟）…'
  scrollToBottom()

  try {
    const res = await aiAssistantApi.chat(text, {
      projectId: reqProjectId,
      sessionId: reqSessionId,
      useServerHistory: true,
      pageContext: pageContext.value
    })
    if (sessionId.value !== reqSessionId || projectId.value !== reqProjectId) {
      return
    }
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      sessionId.value = d.session_id || sessionId.value
      const payload = normalizeAssistantPayload(d.content || '（无内容）', d.thinking || '')
      const msg = {
        role: 'assistant',
        content: payload.content || '（无内容）',
        thinking: payload.thinking,
        tools: d.tools_used || [],
        skills: skillLabelsFromMsg(d),
        mode: d.mode || '',
        cards: Array.isArray(d.cards) ? d.cards : [],
        pending_confirm: d.pending_confirm || null,
        confirm_done: false,
        pending_ask_user: d.pending_ask_user || null,
        ask_user_done: false,
        page_context: d.page_context || pageContext.value || null,
        message_id: d.message_id || '',
        feedbackScore: 0,
        streaming: false
      }
      messages.value.push(msg)
      applyPinnedFromPayload(d)
      const idx = messages.value.length - 1
      if (payload.content && !d.pending_confirm && !d.pending_ask_user) {
        await revealStreaming(idx, payload.content)
      }
      await loadSessions(sessionId.value)
    } else {
      throw new Error(res.data?.message || '请求失败')
    }
  } catch (e) {
    if (sessionId.value !== reqSessionId || projectId.value !== reqProjectId) {
      return
    }
    const msg = e?.response?.data?.detail || e?.data?.detail || e?.message || '助手请求失败'
    ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    messages.value.push({ role: 'assistant', content: `请求失败：${msg}` })
  } finally {
    // 世代不匹配时也必须清 loading，否则切会话后永久卡死
    loading.value = false
    if (sameGeneration(reqSessionId, reqProjectId)) {
      statusText.value = ''
      scrollToBottom()
    }
  }
}

const handleConfirm = async (msg, idx) => {
  const pending = effectivePendingConfirm(msg)
  if (!pending?.confirm_token || loading.value) return
  const reqSessionId = sessionId.value
  const reqProjectId = projectId.value
  confirmLoading.value = idx
  try {
    const res = await aiAssistantApi.confirm({
      action: pending.action,
      confirmToken: pending.confirm_token,
      confirmArgs: pending.confirm_args || {},
      projectId: reqProjectId,
      sessionId: reqSessionId
    })
    if (!sameGeneration(reqSessionId, reqProjectId)) return
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      sessionId.value = d.session_id || sessionId.value
      await loadSessionFromServer()
      if (d.execution_watch) {
        startExecutionWatch(
          messages.value.length,
          sessionId.value,
          projectId.value
        )
      }
      if (d.job) {
        startJobPoll(sessionId.value, projectId.value)
      }
      const navActions = new Set([
        'skill_requirement_to_test_points',
        'skill_api_definition_to_cases',
        'skill_test_points_to_functional_cases',
        'skill_mock_response_generate',
        'skill_nl_to_sql_template',
        'skill_perf_scene_from_nl',
        'skill_browser_lab_to_ui_case',
        'skill_ui_steps_from_nl',
        'skill_report_narrative',
        'skill_qa_eval_assist',
        'skill_curl_to_cases',
        'skill_functional_case_to_ui_case',
        'skill_functional_case_to_app_case',
        'skill_perf_journey_from_suite',
        'skill_failure_to_defect_draft'
      ])
      const nav =
        navActions.has(pending?.action) &&
        (d.navigate || d.result?.navigate || pending?.impact?.navigate || '')
      if (typeof nav === 'string' && nav.startsWith('/')) {
        try {
          await router.push(nav)
        } catch (_) {
          /* ignore navigation errors */
        }
      }
      ElMessage.success(d.result?.message || d.result?.summary || '操作已执行')
      await scrollToBottom()
    } else {
      throw new Error(res.data?.message || '确认失败')
    }
  } catch (e) {
    if (!sameGeneration(reqSessionId, reqProjectId)) return
    const detail = e?.response?.data?.detail || e?.message || '确认执行失败'
    ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  } finally {
    confirmLoading.value = -1
  }
}

const cancelConfirm = async (msg) => {
  const pending = effectivePendingConfirm(msg)
  const reqSessionId = sessionId.value
  const reqProjectId = projectId.value
  if (!pending?.confirm_token || !reqSessionId) {
    msg.confirm_done = true
    return
  }
  try {
    const res = await aiAssistantApi.cancelConfirm({
      action: pending.action,
      confirmToken: pending.confirm_token,
      projectId: reqProjectId,
      sessionId: reqSessionId
    })
    if (!sameGeneration(reqSessionId, reqProjectId)) return
    if (res.data?.code === 200) {
      msg.confirm_done = true
      await loadSessionFromServer()
    } else {
      throw new Error(res.data?.message || '取消失败')
    }
  } catch (e) {
    if (!sameGeneration(reqSessionId, reqProjectId)) return
    const detail = e?.response?.data?.detail || e?.message || '取消失败'
    ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
}

const handleAskSubmit = async (msg, idx, card, answers) => {
  const askId = card?.ask_id || msg.pending_ask_user?.ask_id
  if (!askId || !sessionId.value) return
  const reqSessionId = sessionId.value
  const reqProjectId = projectId.value
  askLoading.value = idx
  loading.value = true
  statusText.value = '已提交补充信息，继续处理…'
  try {
    const res = await aiAssistantApi.answerAskUser({
      sessionId: reqSessionId,
      projectId: reqProjectId,
      askId,
      answers,
      continueChat: true,
      pageContext: msg.page_context || pageContext.value || null
    })
    if (!sameGeneration(reqSessionId, reqProjectId)) return
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      sessionId.value = d.session_id || sessionId.value
      await loadSessionFromServer()
      await loadSessions(sessionId.value)
    } else {
      throw new Error(res.data?.message || '提交失败')
    }
  } catch (e) {
    if (!sameGeneration(reqSessionId, reqProjectId)) return
    const detail = e?.response?.data?.detail || e?.message || '提交提问失败'
    ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  } finally {
    askLoading.value = -1
    loading.value = false
    if (sameGeneration(reqSessionId, reqProjectId)) {
      statusText.value = ''
      scrollToBottom()
    }
  }
}

const cancelAskUser = async (msg) => {
  const askId =
    msg?.pending_ask_user?.ask_id ||
    (msg.cards || []).find((c) => c?.type === 'ask_user')?.ask_id
  const reqSessionId = sessionId.value
  const reqProjectId = projectId.value
  if (!askId || !reqSessionId) return
  try {
    await aiAssistantApi.answerAskUser({
      sessionId: reqSessionId,
      projectId: reqProjectId,
      askId,
      answers: { cancelled: '1' },
      continueChat: false
    })
    if (sameGeneration(reqSessionId, reqProjectId)) {
      msg.ask_user_done = true
      await loadSessionFromServer()
    }
  } catch (e) {
    if (sameGeneration(reqSessionId, reqProjectId)) {
      msg.ask_user_done = false
      const detail = e?.response?.data?.detail || e?.message || '取消失败，请重试'
      ElMessage.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    }
  }
}

watch(panelOpen, (open) => {
  if (open) {
    if (!posInitialized.value) initPanelPosition()
    scrollToBottom()
  } else {
    memoryDrawerOpen.value = false
  }
})

watch(projectId, () => {
  memoryDrawerOpen.value = false
  memoryItems.value = []
  memoryForm.value = { key: '', value: '' }
  stopExecutionWatch()
  stopJobPoll()
  loading.value = false
  askLoading.value = -1
  confirmLoading.value = -1
  statusText.value = ''
  sessionId.value = null
  sessionKeyword.value = ''
  pinnedItems.value = []
  sessionJobs.value = []
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
  window.addEventListener(ASSISTANT_OPEN_SKILL_EVENT, handleAssistantOpenSkill)
  if (visible.value) {
    loadQuickPrompts()
    loadSessionFromServer().then(() => {
      if (sessionId.value) {
        startJobPoll(sessionId.value, projectId.value)
      }
    })
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onWindowResize)
  window.removeEventListener(ASSISTANT_OPEN_SKILL_EVENT, handleAssistantOpenSkill)
  onDragEnd()
  onResizeEnd()
  stopExecutionWatch()
  stopJobPoll()
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

    &:hover:not(:disabled) {
      background: var(--el-fill-color);
      color: var(--el-color-primary);
    }

    &:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    &.close-btn:hover:not(:disabled) {
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

.session-jobs {
  margin-bottom: 10px;
  flex-shrink: 0;
  max-height: 160px;
  overflow-y: auto;

  .session-jobs-title {
    font-size: 12px;
    color: #909399;
    margin-bottom: 6px;
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
  align-items: center;
}

.quick-chips-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-right: 2px;
  flex-shrink: 0;
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

.assistant-thinking {
  margin: 4px 6px 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: #eef1f6;
  color: #606266;
  font-size: 12px;

  summary {
    cursor: pointer;
    user-select: none;
    color: #909399;
    list-style: none;

    &::-webkit-details-marker {
      display: none;
    }

    &::before {
      content: '▸ ';
      color: #c0c4cc;
    }
  }

  &[open] summary::before {
    content: '▾ ';
  }

  .thinking-body {
    margin: 6px 0 0;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: inherit;
    font-size: 12px;
    line-height: 1.5;
    color: #606266;
    max-height: 240px;
    overflow: auto;
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

.message-path {
  margin: 0 0 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.message-tools {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.message-feedback {
  margin-top: 2px;
  display: flex;
  gap: 2px;
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

.memory-hint {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.memory-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.memory-form-actions {
  display: flex;
  gap: 8px;
}

.memory-list {
  min-height: 120px;
}

.memory-item {
  padding: 10px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;

  &:hover {
    background: var(--el-fill-color-lighter);
  }
}

.memory-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.memory-key {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-primary);
  word-break: break-all;
}

.memory-value {
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
