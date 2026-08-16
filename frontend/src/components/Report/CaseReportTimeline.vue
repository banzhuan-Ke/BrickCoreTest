<template>
  <div class="case-timeline-report" v-if="hasData" :class="{ 'is-app-profile': isAppProfile }">
    <!-- 用例基本信息 -->
    <div class="case-header">
      <el-descriptions :column="4" border>
        <el-descriptions-item label="用例名称" :span="2">{{ runInfo.case_name || runInfo.name || '未知用例' }}</el-descriptions-item>
        <el-descriptions-item label="执行状态">
          <el-tag :type="getStatusType(runInfo.status)">{{ getStatusText(runInfo.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="执行耗时">{{ formatDuration(processedRunInfo.duration) }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- App 步骤分布摘要 -->
    <div v-if="isAppProfile && steps.length" class="app-step-summary">
      <span class="app-step-summary-label">步骤分布</span>
      <el-tag size="small" type="info" effect="plain">共 {{ steps.length }} 步</el-tag>
      <el-tag v-if="appStepStats.native" size="small" type="info" effect="plain">原生 {{ appStepStats.native }}</el-tag>
      <el-tag v-if="appStepStats.webview" size="small" type="warning" effect="plain">H5 {{ appStepStats.webview }}</el-tag>
      <el-tag v-if="appStepStats.vision" size="small" type="success" effect="plain">图像 {{ appStepStats.vision }}</el-tag>
      <el-tag v-if="appStepStats.context" size="small" type="primary" effect="plain">上下文 {{ appStepStats.context }}</el-tag>
      <el-tag v-if="appStepStats.failed" size="small" type="danger" effect="plain">失败 {{ appStepStats.failed }}</el-tag>
    </div>

    <!-- 变量快照 -->
    <div class="variables-section" v-if="hasVariables">
      <div class="section-title">
        <el-icon><Collection /></el-icon>
        变量快照
        <el-tag size="small" type="info">{{ variablesTotalCount }} 个</el-tag>
      </div>
      <div class="variables-container">
        <!-- 用例变量 -->
        <div class="var-group" v-if="Object.keys(variablesSnapshot.case_vars || {}).length > 0">
          <div class="var-group-title">
            <el-tag size="small" type="warning">用例变量</el-tag>
            <span class="var-group-desc">通过"提取元素"步骤设置，当前用例内有效</span>
          </div>
          <el-table :data="formatVars(variablesSnapshot.case_vars, variablesSnapshot.usage)" size="small" border class="var-table">
            <el-table-column prop="name" label="变量名" width="160" />
            <el-table-column prop="value" label="值" show-overflow-tooltip min-width="120" />
            <el-table-column prop="writeStep" label="提取步骤" width="100" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.writeStep" size="small" type="warning">步骤 {{ row.writeStep }}</el-tag>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="readSteps" label="引用步骤" width="140" align="center">
              <template #default="{ row }">
                <el-tooltip v-if="row.readSteps && row.readSteps.length" :content="'步骤 ' + row.readSteps.join('、')" placement="top">
                  <el-tag size="small" type="success" class="read-steps-tag">
                    步骤 {{ row.readSteps.join('、') }}
                  </el-tag>
                </el-tooltip>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <!-- 动态变量 -->
        <div class="var-group" v-if="Object.keys(variablesSnapshot.dynamic_vars || {}).length > 0">
          <div class="var-group-title">
            <el-tag size="small" type="success">动态变量</el-tag>
            <span class="var-group-desc">random_int / today / now_time 等运行时生成的值</span>
          </div>
          <el-table :data="formatVars(variablesSnapshot.dynamic_vars, variablesSnapshot.usage)" size="small" border class="var-table">
            <el-table-column prop="name" label="变量名" width="160" />
            <el-table-column prop="value" label="值" show-overflow-tooltip min-width="120" />
            <el-table-column prop="writeStep" label="提取步骤" width="100" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.writeStep" size="small" type="warning">步骤 {{ row.writeStep }}</el-tag>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="readSteps" label="引用步骤" width="140" align="center">
              <template #default="{ row }">
                <el-tooltip v-if="row.readSteps && row.readSteps.length" :content="'步骤 ' + row.readSteps.join('、')" placement="top">
                  <el-tag size="small" type="success" class="read-steps-tag">
                    步骤 {{ row.readSteps.join('、') }}
                  </el-tag>
                </el-tooltip>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <!-- 全局变量 -->
        <div class="var-group" v-if="Object.keys(variablesSnapshot.global_vars || {}).length > 0">
          <div class="var-group-title">
            <el-tag size="small" type="primary">全局变量</el-tag>
            <span class="var-group-desc">来自环境配置，跨用例长期有效</span>
          </div>
          <el-table :data="formatVars(variablesSnapshot.global_vars, variablesSnapshot.usage)" size="small" border class="var-table">
            <el-table-column prop="name" label="变量名" width="160" />
            <el-table-column prop="value" label="值" show-overflow-tooltip min-width="120" />
            <el-table-column prop="writeStep" label="提取步骤" width="100" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.writeStep" size="small" type="warning">步骤 {{ row.writeStep }}</el-tag>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="readSteps" label="引用步骤" width="140" align="center">
              <template #default="{ row }">
                <el-tooltip v-if="row.readSteps && row.readSteps.length" :content="'步骤 ' + row.readSteps.join('、')" placement="top">
                  <el-tag size="small" type="success" class="read-steps-tag">
                    步骤 {{ row.readSteps.join('、') }}
                  </el-tag>
                </el-tooltip>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>

    <!-- 步骤时间轴 -->
    <div class="timeline-section" v-if="steps.length > 0">
      <div class="section-title">
        执行步骤时间轴
        <el-tag size="small" type="info">{{ steps.length }} 个步骤</el-tag>
        <el-button
          v-if="caseIdForWriteback && healedSteps.length"
          size="small"
          type="warning"
          link
          @click="applyAllHealedToCase"
        >写回全部自愈 ({{ healedSteps.length }})</el-button>
        <el-button
          v-if="caseIdForWriteback && aiActSteps.length"
          size="small"
          type="success"
          link
          @click="applyAllAiActToCase"
        >写回全部 AI Act ({{ aiActSteps.length }})</el-button>
      </div>
      <div class="timeline-container">
        <el-timeline>
          <el-timeline-item
            v-for="(step, index) in steps"
            :key="index"
            :type="getStepStatusType(step.status)"
            :icon="getStepIcon(step.status)"
            :timestamp="formatTime(step.time || step.timestamp)"
            placement="top"
          >
            <el-card :class="['step-card', step.status || 'info']" shadow="hover">
              <template #header>
                <div class="step-header">
                  <span class="step-index">步骤 {{ index + 1 }}</span>
                  <span class="step-keyword">{{ step.keyword || step.name || '执行步骤' }}</span>
                  <el-tag v-if="step._from_fragment?.name" size="small" type="success" effect="plain">
                    片段：{{ step._from_fragment.name }}
                  </el-tag>
                  <el-tag size="small" :type="getStepStatusType(step.status)">
                    {{ getStepStatusText(step.status) }}
                  </el-tag>
                  <el-tag
                    v-if="step.failure_code"
                    size="small"
                    :type="failureCodeTagType(step.failure_code)"
                    effect="plain"
                    class="failure-code-tag"
                  >
                    {{ formatFailureCode(step.failure_code) }}
                  </el-tag>
                  <el-tag v-if="isAppProfile && step.locator_type" size="small" :type="locatorTypeTag(step.locator_type)" effect="plain">
                    {{ locatorTypeLabel(step.locator_type) }}
                  </el-tag>
                  <el-tag v-if="isAppProfile && step.execution_context === 'webview'" size="small" type="warning" effect="plain">
                    H5 WebView
                  </el-tag>
                  <el-tag v-if="isAppProfile && step.execution_context === 'chrome'" size="small" type="success" effect="plain">
                    Chrome H5
                  </el-tag>
                </div>
              </template>
              <div class="step-content">
                <div class="step-desc">{{ step.message || step.desc || step.content || '无描述' }}</div>
                <div v-if="isAppProfile && step.webview_page_url" class="step-webview-meta">
                  H5 页面：{{ step.webview_page_url }}
                </div>
                <div v-if="isAppProfile && step.match_score != null" class="step-webview-meta">
                  图像匹配相似度：{{ (step.match_score * 100).toFixed(1) }}%
                  <span v-if="step.status === 'fail' || step.status === 'error'" class="match-score-hint">（未达阈值时可适当降低 threshold）</span>
                </div>
                <div
                  v-if="isAppProfile && (step.template_image || step.template_image_key || hasClickMarker(step))"
                  class="step-vision-compare"
                >
                  <div v-if="step.template_image || step.template_image_key" class="vision-compare-item">
                    <div class="vision-compare-label">识别模板</div>
                    <el-image
                      :src="resolveTemplateImage(step)"
                      :preview-src-list="[resolveTemplateImage(step)]"
                      fit="contain"
                      class="vision-compare-img"
                      :preview-teleported="true"
                    />
                  </div>
                  <div v-if="step.screenshot || step.image" class="vision-compare-item">
                    <div class="vision-compare-label">
                      实际截图
                      <span v-if="hasClickMarker(step)" class="click-marker-hint">（红框标注操作元素）</span>
                    </div>
                    <el-image
                      :src="step.screenshot || step.image"
                      :preview-src-list="[step.screenshot || step.image]"
                      fit="contain"
                      class="vision-compare-img"
                      :preview-teleported="true"
                    />
                  </div>
                </div>
                <div v-if="step.locator_healed" class="step-heal-info">
                  <el-tag size="small" type="warning">AI 自愈</el-tag>
                  <code class="heal-locator">{{ step.locator_healed.original || '—' }}</code>
                  <span class="heal-arrow">→</span>
                  <code class="heal-locator">{{ step.locator_healed.new || step.locator_healed }}</code>
                  <el-tag
                    v-if="step.heal_retry_status === 'fail'"
                    size="small"
                    type="danger"
                    effect="plain"
                  >重试仍失败</el-tag>
                  <el-tag
                    v-else-if="step.heal_retry_status === 'skipped'"
                    size="small"
                    type="info"
                    effect="plain"
                  >校验未通过</el-tag>
                  <span
                    v-if="step.locator_healed.validate_reason"
                    class="heal-act-desc"
                  >{{ step.locator_healed.validate_reason }}</span>
                  <el-button
                    v-if="caseIdForWriteback && step.heal_retry_status !== 'skipped'"
                    size="small"
                    type="primary"
                    link
                    :loading="applyingStepIndex === index"
                    @click="applyHealedToCase(step, index)"
                  >写回用例</el-button>
                </div>
                <div v-if="step.smart_action || step.smart_action_used" class="step-smart-info">
                  <div class="step-smart-head">
                    <el-tag size="small" type="primary">智能消歧</el-tag>
                    <span v-if="step.smart_action?.selected_locator" class="smart-selected">
                      选中
                      <code class="heal-locator">{{ step.smart_action.selected_locator }}</code>
                      <template v-if="step.smart_action.selected_score != null">
                        （{{ step.smart_action.selected_score }} 分
                        <template v-if="step.smart_action.score_margin != null">
                          · 分差 {{ step.smart_action.score_margin }}
                        </template>）
                      </template>
                    </span>
                    <el-tag
                      v-if="step.smart_action?.error_code"
                      size="small"
                      type="danger"
                      effect="plain"
                    >{{ step.smart_action.error_code }}</el-tag>
                    <el-tag
                      v-if="step.smart_action?.postcondition?.status"
                      size="small"
                      :type="step.smart_action.postcondition.status === 'passed' ? 'success' : (step.smart_action.postcondition.status === 'skipped' ? 'info' : 'danger')"
                      effect="plain"
                    >后置 {{ step.smart_action.postcondition.status }}</el-tag>
                  </div>
                  <ul
                    v-if="Array.isArray(step.smart_action?.candidates) && step.smart_action.candidates.length"
                    class="smart-cand-list"
                  >
                    <li
                      v-for="(c, ci) in step.smart_action.candidates.slice(0, 5)"
                      :key="`${index}-cand-${ci}`"
                    >
                      <span class="smart-cand-score">{{ c.score ?? '—' }}</span>
                      <code class="heal-locator">{{ c.locator }}</code>
                      <span v-if="c.source" class="smart-cand-src">{{ c.source }}</span>
                    </li>
                  </ul>
                </div>
                <div
                  v-if="isFailedStep(step) && getFailureContextScreenshots(index).length"
                  class="failure-context-shots"
                >
                  <div class="vision-compare-label">失败上下文截图（含前序步骤）</div>
                  <div class="failure-context-row">
                    <div
                      v-for="shot in getFailureContextScreenshots(index)"
                      :key="`${index}-${shot.stepNo}`"
                      class="vision-compare-item"
                    >
                      <div class="vision-compare-label">
                        第 {{ shot.stepNo }} 步
                        <el-tag v-if="shot.isFail" size="small" type="danger" effect="plain">失败</el-tag>
                      </div>
                      <el-image
                        :src="shot.url"
                        :preview-src-list="getFailureContextScreenshots(index).map(s => s.url)"
                        fit="contain"
                        class="vision-compare-img"
                        :preview-teleported="true"
                      />
                    </div>
                  </div>
                </div>
                <div v-if="step.ai_act_used && step.ai_act" class="step-heal-info">
                  <el-tag
                    size="small"
                    :type="step.ai_act.retry_status === 'fail' ? 'danger' : 'success'"
                  >AI Act 兜底</el-tag>
                  <span class="heal-act-desc">{{
                    step.ai_act.retry_status === 'fail'
                      ? (step.ai_act.error || step.ai_act.reason || '兜底执行失败')
                      : (step.ai_act.act_desc || step.ai_act.reason || '已重新规划并执行')
                  }}</span>
                  <el-tag
                    v-if="step.ai_act.retry_status === 'fail'"
                    size="small"
                    type="danger"
                    effect="plain"
                  >失败</el-tag>
                  <el-button
                    v-if="caseIdForWriteback && step.ai_act.retry_status !== 'fail' && step.ai_act.act_params && Object.keys(step.ai_act.act_params).length"
                    size="small"
                    type="primary"
                    link
                    :loading="applyingAiActIndex === index"
                    @click="applyAiActToCase(step, index)"
                  >写回用例</el-button>
                </div>
                <!-- 步骤截图缩略图（无模板对比时显示） -->
                <div
                  class="step-screenshot-preview"
                  v-if="(step.screenshot || step.image) && !(isAppProfile && (step.template_image || step.template_image_key))"
                  @click.stop
                >
                  <div v-if="hasClickMarker(step)" class="step-screenshot-marker-hint">红框标注操作元素</div>
                  <el-image 
                    :src="step.screenshot || step.image" 
                    :preview-src-list="[step.screenshot || step.image]"
                    :fit="isAppProfile ? 'contain' : 'cover'"
                    class="screenshot-thumb"
                    :class="{ 'is-app-thumb': isAppProfile }"
                    :preview-teleported="true"
                  >
                    <template #error>
                      <div class="image-error-small">
                        <el-icon><Picture /></el-icon>
                      </div>
                    </template>
                  </el-image>
                </div>
              </div>
            </el-card>
          </el-timeline-item>
        </el-timeline>
      </div>
    </div>

    <!-- 截图轮播 -->
    <div class="screenshot-section" v-if="screenshots.length > 0">
      <div class="section-title">
        执行截图
        <span class="screenshot-count">({{ currentScreenshot + 1 }} / {{ screenshots.length }})</span>
      </div>
      <div class="screenshot-carousel">
        <el-carousel 
          :interval="5000" 
          arrow="always" 
          :type="isAppProfile ? '' : 'card'"
          :height="isAppProfile ? '520px' : '400px'"
          @change="handleScreenshotChange"
        >
          <el-carousel-item v-for="(screenshot, index) in screenshots" :key="index">
            <div class="screenshot-item">
              <el-image 
                :src="screenshot.url" 
                :preview-src-list="screenshotPreviewList"
                :initial-index="index"
                fit="contain"
                class="screenshot-image"
                :preview-teleported="true"
              >
                <template #error>
                  <div class="image-error">
                    <el-icon><Picture /></el-icon>
                    <span>截图加载失败</span>
                  </div>
                </template>
              </el-image>
              <div class="screenshot-info">
                <span class="screenshot-step">步骤 {{ screenshot.stepIndex + 1 }}</span>
                <span class="screenshot-desc">{{ screenshot.desc }}</span>
                <span v-if="screenshot.hasMarker" class="screenshot-marker-hint">红框标注操作元素</span>
              </div>
            </div>
          </el-carousel-item>
        </el-carousel>
      </div>
    </div>

    <!-- 视频回放（App 优先展示录屏） -->
    <div class="video-section" v-if="processedRunInfo.video_url">
      <div class="section-title">{{ isAppProfile ? '执行录屏' : '执行视频回放' }}</div>
      <div class="video-wrapper" :class="{ 'mobile-media-box': isAppProfile }">
        <video
          v-if="videoLoaded"
          ref="videoPlayer"
          :key="processedRunInfo.video_url"
          controls
          class="video-player"
          preload="metadata"
          playsinline
          @error="handleVideoError"
        >
          <source :src="processedRunInfo.video_url" type="video/mp4" />
        </video>
        <div v-else class="video-placeholder" :class="{ 'mobile-media-box': isAppProfile }" @click.stop="loadAndPlayVideo">
          <el-icon class="play-icon"><VideoPlay /></el-icon>
          <div class="play-text">点击加载视频</div>
        </div>
      </div>
    </div>

    <el-alert
      v-else-if="showVideoMissingHint"
      type="warning"
      :closable="false"
      show-icon
      class="video-missing-hint"
      title="未生成录屏"
      description="本次执行已开启录屏，但 Runner 未上传视频。请确认 Runner 本机 adb 可用、设备允许 screenrecord，且用例时长未过短。"
    />

    <!-- 结果截图：有录屏时 App 报告不再重复展示 -->
    <div class="result-screenshot-section" v-if="showFinalScreenshot">
      <div class="section-title">
        {{ isAppProfile ? '用例结束截图' : '最终截图' }}
      </div>
      <div class="result-screenshot" :class="{ 'mobile-media-box': isAppProfile }">
        <el-image 
          :src="processedRunInfo.img_url" 
          :preview-src-list="[processedRunInfo.img_url]"
          fit="contain"
          class="final-screenshot"
          :preview-teleported="true"
        />
      </div>
    </div>

    <!-- 错误信息 -->
    <div class="error-section" v-if="processedRunInfo.error_msg">
      <div class="section-title" style="color: var(--el-color-danger)">
        <el-icon><Warning /></el-icon>
        错误信息
      </div>
      <div class="error-content">
        <pre>{{ processedRunInfo.error_msg }}</pre>
      </div>
    </div>

    <!-- 日志虚拟滚动 -->
    <ExecutionLogScroller
      :logs="logData"
      container-height="400px"
      show-time
      show-level
    />
  </div>

  <!-- 无数据状态 -->
  <el-empty v-else description="用例暂无运行详细记录信息" />
</template>

<script setup>
import { computed, ref, watch, onMounted, nextTick } from 'vue'
import { 
  UploadFilled, 
  CircleCheck, 
  CircleClose, 
  Warning, 
  InfoFilled,
  Timer,
  Picture,
  VideoPlay,
  Collection
} from '@element-plus/icons-vue'
import ExecutionLogScroller from '@/components/Report/ExecutionLogScroller.vue'
import { fileApi } from '@/api/modules/sys'
import { aiGenerateApi } from '@/api/modules/ai.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatFailureCode, failureCodeTagType } from '@/utils/uiFailureCode'

const props = defineProps({
  runInfo: {
    type: Object,
    required: true
  },
  profile: {
    type: String,
    default: 'web',
    validator: (v) => ['web', 'app'].includes(v),
  },
})

// 预签名 URL 映射表
const presignedUrlMap = ref({})

const normalizeRunInfo = (info) => {
  if (!info) return null
  if (typeof info === 'string') {
    try {
      return JSON.parse(info)
    } catch (e) {
      console.error('Invalid runInfo JSON:', e)
      return null
    }
  }
  return info
}

const isStorageObjectUrl = (url) => {
  if (!url || typeof url !== 'string' || isPresignedUrl(url)) return false
  const cleanUrl = url.split('?')[0]
  if (/\.(png|jpe?g|gif|webm|mp4)$/i.test(cleanUrl)) return true
  return cleanUrl.includes('aliyuncs.com') || cleanUrl.includes('/minio/')
}

// 处理 runInfo，将 MinIO URL 替换为预签名 URL
const processedRunInfo = computed(() => {
  const rawInfo = normalizeRunInfo(props.runInfo)
  if (!rawInfo) return {}
  
  const info = { ...rawInfo }
  if (!info.img_url && info.img) {
    info.img_url = info.img
  }
  
  // 替换主截图 URL（仅当尚未预签名时）
  if (info.img && !isPresignedUrl(info.img)) {
    const filename = extractFilename(info.img)
    if (filename && presignedUrlMap.value[filename]) {
      info.img = presignedUrlMap.value[filename]
      info.img_url = info.img
    }
  }
  
  // 替换视频 URL（优先使用最新的预签名 URL，支持过期后刷新）
  if (info.video_url) {
    const filename = extractFilename(info.video_url)
    if (filename && presignedUrlMap.value[filename]) {
      info.video_url = presignedUrlMap.value[filename]
    }
  }

  if (info.steps && info.steps.length > 0) {
    info.steps = info.steps.map(step => {
      const next = { ...step }
      const tplKey = step.template_image_key
      if (tplKey && presignedUrlMap.value[tplKey]) {
        next.template_image = presignedUrlMap.value[tplKey]
      }
      const shot = step.screenshot || step.image
      if (shot && !isPresignedUrl(shot)) {
        const filename = extractFilename(shot)
        if (filename && presignedUrlMap.value[filename]) {
          const signed = presignedUrlMap.value[filename]
          next.screenshot = signed
          next.image = signed
        }
      }
      return next
    })
  }
  
  return info
})

const isAppProfile = computed(() => props.profile === 'app')

const showFinalScreenshot = computed(() => {
  const info = processedRunInfo.value
  if (!info?.img_url) return false
  if (isAppProfile.value && info.video_url) return false
  return true
})

const showVideoMissingHint = computed(() => {
  if (!isAppProfile.value) return false
  const info = processedRunInfo.value
  if (info?.video_url) return false
  return info.record_video !== false
})

// 从 URL 中提取文件名
const extractFilename = (url) => {
  if (!url) return ''
  // 去掉查询参数后再匹配
  const cleanUrl = url.split('?')[0]
  // 处理 http://192.168.x.x:9200/bucket/filename 格式
  // 或者 http://localhost:9200/test-results/filename
  const match = cleanUrl.match(/\/([^\/]+\.(?:png|jpg|jpeg|gif|webm|mp4))$/)
  if (match) return match[1]
  // 如果上面没匹配到，尝试从URL解码后的路径提取
  try {
    const decoded = decodeURIComponent(cleanUrl)
    const match2 = decoded.match(/\/([^\/]+\.(?:png|jpg|jpeg|gif|webm|mp4))$/)
    if (match2) return match2[1]
  } catch (e) {}
  return ''
}

// 判断 URL 是否已经是预签名 URL
const isPresignedUrl = (url) => {
  return url && typeof url === 'string' && url.includes('X-Amz-Signature=')
}

// 收集所有需要处理的 URL（过滤掉已经是预签名的）
const collectUrlsToProcess = (info) => {
  const normalized = normalizeRunInfo(info)
  if (!normalized) return []

  const urls = new Set()
  
  // 主截图
  if (normalized.img && isStorageObjectUrl(normalized.img)) {
    urls.add(extractFilename(normalized.img))
  }
  
  // 视频
  if (normalized.video_url && isStorageObjectUrl(normalized.video_url)) {
    urls.add(extractFilename(normalized.video_url))
  }
  
  // 步骤截图 / 图像模板
  if (normalized.steps && normalized.steps.length > 0) {
    normalized.steps.forEach(step => {
      const shot = step.screenshot || step.image
      if (shot && isStorageObjectUrl(shot)) {
        urls.add(extractFilename(shot))
      }
      const tplKey = step.template_image_key
      if (tplKey && typeof tplKey === 'string') {
        urls.add(tplKey)
      }
    })
  }
  
  return Array.from(urls).filter(Boolean)
}

// video DOM ref
const videoPlayer = ref(null)
const videoLoaded = ref(false)

// 点击播放按钮后加载视频
const loadAndPlayVideo = async () => {
  videoLoaded.value = true
  await nextTick()
  // 如果 video_url 还不是预签名 URL，先刷新
  const src = processedRunInfo.value.video_url
  if (src && !isPresignedUrl(src)) {
    const filename = extractFilename(src)
    if (filename) {
      try {
        const urlMap = await fileApi.getBatchPresignedUrls([filename])
        if (urlMap[filename]) {
          presignedUrlMap.value[filename] = urlMap[filename]
        }
      } catch (e) {
        console.error('[CaseReportTimeline] 预加载视频 URL 失败:', e)
      }
    }
  }
  reloadVideo()
  // 尝试自动播放（浏览器策略可能阻止，但不影响手动点击播放）
  setTimeout(() => {
    if (videoPlayer.value) {
      videoPlayer.value.play().catch(() => {})
    }
  }, 300)
}

// 强制 video 元素重新加载
const reloadVideo = () => {
  nextTick(() => {
    if (videoPlayer.value) {
      videoPlayer.value.load()
    }
  })
}

// 监听 runInfo 变化时重置懒加载状态
watch(() => props.runInfo, () => {
  videoLoaded.value = false
}, { deep: true })

// 处理视频加载失败（通常是预签名 URL 过期），自动刷新 URL
const handleVideoError = async () => {
  const src = processedRunInfo.value.video_url
  if (!src) return
  const filename = extractFilename(src)
  if (!filename) return
  try {
    const urlMap = await fileApi.getBatchPresignedUrls([filename])
    const newUrl = urlMap[filename]
    if (newUrl && newUrl !== src) {
      presignedUrlMap.value[filename] = newUrl
      reloadVideo()
    }
  } catch (e) {
    console.error('[CaseReportTimeline] 视频 URL 刷新失败:', e)
  }
}

// 获取预签名 URL
const loadPresignedUrls = async () => {
  const urls = collectUrlsToProcess(props.runInfo)
  
  if (urls.length === 0) {
    const info = normalizeRunInfo(props.runInfo)
    if (info?.video_url) {
      reloadVideo()
    }
    return
  }
  
  try {
    const urlMap = await fileApi.getBatchPresignedUrls(urls)
    presignedUrlMap.value = urlMap
    console.log('[CaseReportTimeline] Loaded presigned URLs:', Object.keys(urlMap))
    reloadVideo()
  } catch (error) {
    console.error('[CaseReportTimeline] 获取预签名 URL 失败:', error)
  }
}

// 组件挂载时加载
onMounted(() => {
  loadPresignedUrls()
})

// 监听 runInfo 变化
watch(() => props.runInfo, () => {
  presignedUrlMap.value = {}
  loadPresignedUrls()
}, { deep: true })

const currentScreenshot = ref(0)
const applyingStepIndex = ref(-1)
const applyingAiActIndex = ref(-1)

const caseIdForWriteback = computed(() => {
  const info = processedRunInfo.value
  return info?.case_id || info?.id || null
})

const healedSteps = computed(() =>
  steps.value
    .map((step, index) => ({ step, index }))
    .filter(({ step }) => step?.locator_healed?.new)
)

const aiActSteps = computed(() =>
  steps.value
    .map((step, index) => ({ step, index }))
    .filter(({ step }) => step?.ai_act_used && step?.ai_act?.act_params && Object.keys(step.ai_act.act_params).length)
)

function formatAiActWritebackPreview(aiAct) {
  const params = aiAct?.act_params || {}
  const keys = ['locator', 'selector', 'start_selector', 'end_selector', 'first_locator', 'second_locator']
  const parts = keys
    .filter((k) => params[k])
    .map((k) => `${k}=${params[k]}`)
  return parts.length ? parts.join('\n') : JSON.stringify(params, null, 2)
}

async function applyAiActToCase(step, index, skipConfirm = false) {
  const caseId = caseIdForWriteback.value
  const aiAct = step.ai_act
  if (!caseId || !aiAct?.act_params) return
  if (!skipConfirm) {
    try {
      await ElMessageBox.confirm(
        `将步骤 ${index + 1} 的 AI Act 定位参数写回用例 #${caseId}？\n${formatAiActWritebackPreview(aiAct)}`,
        '写回 AI Act 结果',
        { type: 'warning' }
      )
    } catch {
      return
    }
  }
  applyingAiActIndex.value = index
  try {
    const res = await aiGenerateApi.applyAiActToCase({
      case_id: caseId,
      step_index: step.step_index ?? index,
      act_params: aiAct.act_params,
      act_method: aiAct.act_method,
    })
    if (res.data?.code === 200) {
      if (!skipConfirm) ElMessage.success('已写回用例')
      return true
    }
    ElMessage.error(res.data?.message || '写回失败')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '写回失败')
  } finally {
    applyingAiActIndex.value = -1
  }
  return false
}

async function applyAllAiActToCase() {
  const caseId = caseIdForWriteback.value
  if (!caseId || !aiActSteps.value.length) return
  try {
    await ElMessageBox.confirm(
      `将 ${aiActSteps.value.length} 处 AI Act 定位参数全部写回用例 #${caseId}？`,
      '批量写回 AI Act',
      { type: 'warning' }
    )
  } catch {
    return
  }
  let ok = 0
  for (const { step, index } of aiActSteps.value) {
    if (await applyAiActToCase(step, index, true)) ok += 1
  }
  if (ok) ElMessage.success(`已写回 ${ok} 处 AI Act 定位参数`)
}

async function applyHealedToCase(step, index, skipConfirm = false) {
  const caseId = caseIdForWriteback.value
  const healed = step.locator_healed
  if (!caseId || !healed?.new) return
  if (!skipConfirm) {
    try {
      await ElMessageBox.confirm(
        `将步骤 ${index + 1} 的定位器写回用例 #${caseId}？\n${healed.original || '—'} → ${healed.new}`,
        '写回自愈定位器',
        { type: 'warning' }
      )
    } catch {
      return
    }
  }
  applyingStepIndex.value = index
  try {
    const res = await aiGenerateApi.applyHealedLocatorToCase({
      case_id: caseId,
      step_index: step.step_index ?? index,
      new_locator: healed.new,
      original_locator: healed.original
    })
    if (res.data?.code === 200) {
      if (!skipConfirm) ElMessage.success('已写回用例')
      return true
    }
    ElMessage.error(res.data?.message || '写回失败')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '写回失败')
  } finally {
    applyingStepIndex.value = -1
  }
  return false
}

async function applyAllHealedToCase() {
  const caseId = caseIdForWriteback.value
  if (!caseId || !healedSteps.value.length) return
  try {
    await ElMessageBox.confirm(
      `将 ${healedSteps.value.length} 处自愈定位器全部写回用例 #${caseId}？`,
      '批量写回',
      { type: 'warning' }
    )
  } catch {
    return
  }
  let ok = 0
  for (const { step, index } of healedSteps.value) {
    if (await applyHealedToCase(step, index, true)) ok += 1
  }
  if (ok) ElMessage.success(`已写回 ${ok} 处定位器`)
}

function isFailedStep(step) {
  return ['fail', 'failed', 'error'].includes(String(step?.status || '').toLowerCase())
}

function getFailureContextScreenshots(failIndex) {
  const list = steps.value || []
  const shots = []
  const start = Math.max(0, failIndex - 2)
  const end = Math.min(list.length - 1, failIndex + 2)
  for (let i = start; i <= end; i++) {
    const s = list[i]
    const url = s?.screenshot || s?.image
    if (url) {
      shots.push({ stepNo: i + 1, url, isFail: i === failIndex })
    }
  }
  return shots
}

// 判断是否有数据（含仅有错误说明的超时收尾结果）
const hasData = computed(() => {
  const info = processedRunInfo.value
  return info && (info.id || info.case_id || info.case_name || info.name ||
         (info.steps && info.steps.length > 0) ||
         (info.log_data && info.log_data.length > 0) ||
         info.error_msg || info.error || info.message)
})

// 步骤数据（使用处理后的数据）
const steps = computed(() => {
  return processedRunInfo.value.steps || []
})

const appStepStats = computed(() => {
  if (!isAppProfile.value || !steps.value.length) {
    return { native: 0, webview: 0, vision: 0, context: 0, failed: 0 }
  }
  const stats = { native: 0, webview: 0, vision: 0, context: 0, failed: 0 }
  steps.value.forEach((step) => {
    const type = step.locator_type || (step.by === 'image' ? 'vision' : '')
    if (type && Object.prototype.hasOwnProperty.call(stats, type)) {
      stats[type] += 1
    }
    if (['fail', 'failed', 'error'].includes(String(step.status || '').toLowerCase())) {
      stats.failed += 1
    }
  })
  return stats
})

// 变量快照
const variablesSnapshot = computed(() => {
  return processedRunInfo.value.variables_snapshot || {}
})

const hasVariables = computed(() => {
  const snap = variablesSnapshot.value
  return snap && (
    Object.keys(snap.global_vars || {}).length > 0 ||
    Object.keys(snap.case_vars || {}).length > 0 ||
    Object.keys(snap.dynamic_vars || {}).length > 0
  )
})

const variablesTotalCount = computed(() => {
  const snap = variablesSnapshot.value
  return (
    Object.keys(snap.global_vars || {}).length +
    Object.keys(snap.case_vars || {}).length +
    Object.keys(snap.dynamic_vars || {}).length
  )
})

const formatVars = (varsObj, usage) => {
  if (!varsObj) return []
  return Object.entries(varsObj).map(([name, value]) => {
    const varUsage = usage && usage[name] ? usage[name] : {}
    return {
      name,
      value: String(value),
      writeStep: varUsage.write_step || null,
      readSteps: varUsage.read_steps || []
    }
  })
}

// 日志数据
const logData = computed(() => {
  return processedRunInfo.value.log_data || []
})

// 状态映射
const statusMap = {
  no_run: { text: '未运行', type: 'info' },
  running: { text: '运行中', type: 'primary' },
  success: { text: '成功', type: 'success' },
  fail: { text: '失败', type: 'danger' },
  failed: { text: '失败', type: 'danger' },
  error: { text: '错误', type: 'warning' },
  skip: { text: '跳过', type: 'info' },
  pending: { text: '等待', type: 'info' }
}

const stepStatusMap = {
  pass: { text: '通过', type: 'success', icon: CircleCheck },
  success: { text: '成功', type: 'success', icon: CircleCheck },
  fail: { text: '失败', type: 'danger', icon: CircleClose },
  failed: { text: '失败', type: 'danger', icon: CircleClose },
  error: { text: '错误', type: 'danger', icon: Warning },
  skip: { text: '跳过', type: 'info', icon: InfoFilled },
  skipped: { text: '跳过', type: 'info', icon: InfoFilled },
  running: { text: '执行中', type: 'primary', icon: UploadFilled },
  pending: { text: '等待', type: 'info', icon: InfoFilled },
  info: { text: '信息', type: 'info', icon: InfoFilled }
}

// 获取状态类型
const getStatusType = (status) => statusMap[status]?.type || 'info'
const getStatusText = (status) => statusMap[status]?.text || status
const getStepStatusType = (status) => stepStatusMap[status]?.type || 'info'
const getStepStatusText = (status) => stepStatusMap[status]?.text || status

const locatorTypeLabel = (type) => {
  const map = { native: '原生', webview: 'H5', vision: '图像', context: '上下文' }
  return map[type] || type
}

const locatorTypeTag = (type) => {
  const map = { native: 'info', webview: 'warning', vision: 'success', context: 'primary' }
  return map[type] || 'info'
}
const getStepIcon = (status) => stepStatusMap[status]?.icon || InfoFilled

// 格式化时间
const formatTime = (timestamp) => {
  if (!timestamp) return ''
  if (typeof timestamp === 'string') return timestamp
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { 
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// 格式化耗时
const formatDuration = (duration) => {
  if (duration == null || duration === undefined || duration === '') return '-'
  if (duration < 0.001) return '< 1ms'
  if (duration < 1) return `${(duration * 1000).toFixed(0)}ms`
  if (duration < 60) return `${duration.toFixed(2)}s`
  const mins = Math.floor(duration / 60)
  const secs = (duration % 60).toFixed(2)
  return `${mins}m ${secs}s`
}

// 截图列表（从步骤中提取）
const hasClickMarker = (step) =>
  step?.screenshot_has_marker === true

const resolveTemplateImage = (step) => {
  if (step?.template_image) return step.template_image
  const key = step?.template_image_key
  if (key && presignedUrlMap.value[key]) return presignedUrlMap.value[key]
  return key || ''
}

const screenshots = computed(() => {
  const list = []
  steps.value.forEach((step, index) => {
    const screenshot = step.screenshot || step.image
    if (screenshot) {
      list.push({
        url: screenshot,
        stepIndex: index,
        desc: step.keyword || step.name || `步骤 ${index + 1}`,
        hasMarker: hasClickMarker(step),
      })
    }
  })
  return list
})

// 截图预览列表
const screenshotPreviewList = computed(() => screenshots.value.map(s => s.url))

// 处理截图切换
const handleScreenshotChange = (index) => {
  currentScreenshot.value = index
}
</script>

<style scoped lang="scss">
.case-timeline-report {
  padding: 16px;
  
  .case-header {
    margin-bottom: 20px;
  }
  
  .section-title {
    font-size: 16px;
    font-weight: bold;
    margin: 20px 0 12px;
    padding-left: 12px;
    border-left: 4px solid var(--el-color-primary);
    display: flex;
    align-items: center;
    gap: 8px;
    
    .screenshot-count {
      font-size: 14px;
      color: var(--el-text-color-secondary);
      font-weight: normal;
    }
  }
  
  .timeline-container {
    max-height: 600px;
    overflow-y: auto;
    padding: 16px;
    background: var(--el-fill-color-light);
    border-radius: 8px;
    
    .step-card {
      margin-bottom: 8px;
      
      &.pass, &.success {
        border-left: 3px solid var(--el-color-success);
      }
      &.fail, &.failed, &.error {
        border-left: 3px solid var(--el-color-danger);
      }
      &.skip, &.skipped {
        border-left: 3px solid var(--el-color-info);
      }
      &.running {
        border-left: 3px solid var(--el-color-primary);
      }
      
      .step-header {
        display: flex;
        align-items: center;
        gap: 12px;
        
        .step-index {
          font-weight: bold;
          color: var(--el-text-color-primary);
        }
        
        .step-keyword {
          flex: 1;
          font-family: monospace;
          color: var(--el-color-primary);
        }
      }
      
      .step-content {
        .step-desc {
          color: var(--el-text-color-regular);
          margin-bottom: 8px;
          font-size: 13px;
          line-height: 1.5;
        }

        .step-webview-meta {
          margin-bottom: 8px;
          font-size: 12px;
          color: var(--el-text-color-secondary);
          word-break: break-all;
        }

        .step-heal-info {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
          padding: 8px 10px;
          background: var(--el-color-warning-light-9);
          border-radius: 6px;
          font-size: 12px;

          .heal-locator {
            font-family: monospace;
            word-break: break-all;
            &.new { color: var(--el-color-success); }
          }
          .heal-arrow { color: var(--el-text-color-secondary); }
        }

        .step-smart-info {
          margin-bottom: 8px;
          padding: 8px 10px;
          background: var(--el-color-primary-light-9);
          border-radius: 6px;
          font-size: 12px;

          .step-smart-head {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
          }
          .smart-selected {
            color: var(--el-text-color-regular);
          }
          .smart-cand-list {
            margin: 0;
            padding-left: 18px;
            color: var(--el-text-color-secondary);
            li {
              margin: 2px 0;
              line-height: 1.45;
            }
          }
          .smart-cand-score {
            display: inline-block;
            min-width: 28px;
            font-weight: 600;
            color: var(--el-color-primary);
          }
          .smart-cand-src {
            margin-left: 6px;
            opacity: 0.75;
          }
          .heal-locator {
            font-family: monospace;
            word-break: break-all;
          }
        }
        
        .step-webview-meta {
          margin-top: 6px;
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }

        .failure-context-shots {
          margin-top: 10px;

          .failure-context-row {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
          }

          .vision-compare-item {
            flex: 1;
            min-width: 140px;
            max-width: 220px;
          }

          .vision-compare-label {
            font-size: 12px;
            color: var(--el-text-color-secondary);
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 6px;
          }

          .vision-compare-img {
            width: 100%;
            max-height: 220px;
            border-radius: 6px;
            border: 1px solid var(--el-border-color-lighter);
            background: #111;
          }
        }

        .step-vision-compare {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          margin-top: 10px;

          .vision-compare-item {
            flex: 1;
            min-width: 140px;
            max-width: 220px;
          }

          .vision-compare-label {
            font-size: 12px;
            color: var(--el-text-color-secondary);
            margin-bottom: 6px;

            .click-marker-hint {
              color: var(--el-color-danger);
            }
          }

          .vision-compare-img {
            width: 100%;
            max-height: 280px;
            border-radius: 6px;
            border: 1px solid var(--el-border-color-lighter);
            background: #111;

            :deep(.el-image__inner) {
              max-height: 280px;
              object-fit: contain;
            }
          }
        }

        .step-screenshot-preview {
          margin-top: 8px;

          .step-screenshot-marker-hint {
            font-size: 12px;
            color: var(--el-color-danger);
            margin-bottom: 4px;
          }
          
          .screenshot-thumb {
            width: 120px;
            height: 80px;
            border-radius: 4px;
            border: 1px solid var(--el-border-color);
            
            :deep(.el-image__inner) {
              width: 100%;
              height: 100%;
              object-fit: cover;
            }
          }
          
          .image-error-small {
            width: 120px;
            height: 80px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--el-fill-color);
            color: var(--el-text-color-secondary);
            border-radius: 4px;
          }
        }
      }
    }
  }
  
  .screenshot-carousel {
    padding: 16px;
    background: var(--el-fill-color-light);
    border-radius: 8px;
    
    .screenshot-item {
      height: 100%;
      display: flex;
      flex-direction: column;
      background: var(--el-bg-color);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
      
      .screenshot-image {
        flex: 1;
        min-height: 0;
        background: #f5f5f5;
        
        :deep(.el-image__inner) {
          width: 100%;
          height: 100%;
          object-fit: contain;
        }
      }
      
      .screenshot-info {
        padding: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: var(--el-bg-color);
        border-top: 1px solid var(--el-border-color-light);
        
        .screenshot-step {
          font-weight: bold;
          color: var(--el-color-primary);
        }
        
        .screenshot-desc {
          flex: 1;
          margin: 0 12px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          color: var(--el-text-color-regular);
          font-size: 13px;
        }

        .screenshot-marker-hint {
          flex-shrink: 0;
          font-size: 12px;
          color: var(--el-color-danger);
        }
      }
    }
    
    .image-error {
      height: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: var(--el-text-color-secondary);
      gap: 8px;
      font-size: 14px;
    }
  }
  
  .video-missing-hint {
    margin-bottom: 16px;
  }

  &.is-app-profile {
    .app-step-summary {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin-bottom: 16px;
      padding: 10px 12px;
      border-radius: 8px;
      background: var(--el-fill-color-light);
      border: 1px solid var(--el-border-color-lighter);

      .app-step-summary-label {
        font-size: 13px;
        font-weight: 600;
        color: var(--el-text-color-regular);
        margin-right: 4px;
      }
    }

    .screenshot-carousel {
      background: var(--el-fill-color-light);

      .screenshot-item {
        align-items: center;
        padding: 12px;

        .screenshot-image {
          width: min(320px, 100%);
          max-height: 460px;
          flex: none;
          border-radius: 12px;
          box-shadow: 0 6px 24px rgba(15, 23, 42, 0.12);

          :deep(.el-image__inner) {
            object-fit: contain;
          }
        }

        .screenshot-info {
          width: min(320px, 100%);
        }
      }
    }

    .step-screenshot-preview .screenshot-thumb.is-app-thumb {
      width: 72px;
      height: 128px;

      :deep(.el-image__inner) {
        object-fit: contain;
      }
    }

    .mobile-media-box {
      display: flex;
      justify-content: center;
      padding: 16px;
      background: var(--el-fill-color-light);
      border-radius: 8px;
    }

    .result-screenshot.mobile-media-box .final-screenshot {
      width: min(320px, 100%);
      max-height: 640px;
      border-radius: 12px;
      box-shadow: 0 6px 24px rgba(15, 23, 42, 0.12);
      overflow: hidden;

      :deep(.el-image__inner) {
        width: 100%;
        height: auto;
        max-height: 640px;
        object-fit: contain;
      }
    }

    .video-wrapper.mobile-media-box,
    .video-placeholder.mobile-media-box {
      width: min(320px, 100%);
      margin: 0 auto;
    }

    .video-player {
      width: 100%;
      max-height: none;
      aspect-ratio: 9 / 19.5;
      object-fit: contain;
      background: #000;
    }

    .video-placeholder.mobile-media-box {
      aspect-ratio: 9 / 19.5;
    }
  }
  
  .result-screenshot-section {
    .result-screenshot {
      padding: 16px;
      background: var(--el-fill-color-light);
      border-radius: 8px;
      
      .final-screenshot {
        width: 100%;
        max-height: 500px;
        border-radius: 8px;
      }
    }
  }
  
  .video-player {
    width: 100%;
    max-height: 500px;
    border-radius: 8px;
    background: #000;
  }
  
  .video-wrapper {
    position: relative;
    width: 100%;
    max-height: 500px;
    border-radius: 8px;
    overflow: hidden;
    background: #000;
  }
  
  .video-placeholder {
    width: 100%;
    aspect-ratio: 16 / 9;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: #1a1a1a;
    cursor: pointer;
    transition: background 0.2s;
    
    &:hover {
      background: #2a2a2a;
    }
    
    .play-icon {
      font-size: 64px;
      color: var(--el-color-primary);
      margin-bottom: 12px;
    }
    
    .play-text {
      font-size: 14px;
      color: var(--el-text-color-secondary);
    }
  }
  
  .error-section {
    .error-content {
      padding: 16px;
      background: var(--el-color-danger-light-9);
      border: 1px solid var(--el-color-danger-light-5);
      border-radius: 8px;
      
      pre {
        margin: 0;
        color: var(--el-color-danger);
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 13px;
        white-space: pre-wrap;
        word-break: break-all;
        max-height: 300px;
        overflow-y: auto;
      }
    }
  }
}

.variables-container {
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  
  .var-group {
    .var-group-title {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
      
      .var-group-desc {
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }
    }
    
    .var-table {
      background: var(--el-bg-color);
      border-radius: 6px;
      overflow: hidden;
    }
  }
}

:deep(.el-timeline-item__node) {
  background-color: var(--el-color-primary);
}

:deep(.el-timeline-item__tail) {
  border-left-color: var(--el-border-color);
}

.text-muted {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.read-steps-tag {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-flex;
}
</style>
