<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">
        {{ isEdit ? '✏️ 编辑性能测试场景' : '➕ 新建性能测试场景' }}
      </div>
    </template>
    <template #main>
      <el-form :model="form" :rules="rules" ref="formRef" label-width="120px">
        <!-- 基本信息 -->
        <el-divider content-position="left">基本信息</el-divider>
        <el-form-item label="场景名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入场景名称" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="场景描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="请输入场景描述" />
        </el-form-item>

        <!-- 压测模式 -->
        <el-divider content-position="left">压测模式</el-divider>
        <el-form-item label="模式选择" prop="config.mode">
                  <div class="mode-wrap">
            <el-radio-group v-model="form.config.mode" @change="onModeChange">
              <el-radio-button label="fixed">固定模式</el-radio-button>
              <el-radio-button label="loop">循环模式</el-radio-button>
              <el-radio-button label="stepping">梯度模式</el-radio-button>
            </el-radio-group>
            <div class="mode-hint">
              <el-tag v-if="form.config.mode === 'fixed'" size="small" type="info">固定并发数，持续指定时间</el-tag>
              <el-tag v-if="form.config.mode === 'loop'" size="small" type="info">固定并发数，每个用户循环指定次数</el-tag>
              <el-tag v-if="form.config.mode === 'stepping'" size="small" type="info">分阶段递增并发，每阶段持续指定时间</el-tag>
            </div>
          </div>
        </el-form-item>

        <!-- 分配模式 -->
        <el-form-item label="分配模式">
          <div class="mode-wrap">
            <el-radio-group v-model="form.config.distribution_mode">
              <el-radio-button label="random_weight">随机权重</el-radio-button>
              <el-radio-button label="fixed_ratio">固定比例</el-radio-button>
            </el-radio-group>
            <el-tooltip placement="top" :content="distModeTip">
              <el-icon class="tip-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
          <div class="field-tip">{{ distModeTip }}</div>
        </el-form-item>

        <!-- 通用配置 -->
        <el-form-item label="并发用户数" prop="config.concurrent_users" v-if="form.config.mode !== 'stepping'">
          <el-slider v-model="form.config.concurrent_users" :min="1" :max="1000" show-stops show-input />
          <div class="field-tip">同时发起请求的虚拟用户数，建议不超过 500；超过 500 请确保服务器有足够 CPU 和网络带宽</div>
        </el-form-item>
        <el-form-item label="Ramp-up时间">
          <el-input-number v-model="form.config.ramp_up_seconds" :min="0" :max="600" />
          <span class="unit">秒（0表示立即加压）</span>
          <el-tooltip placement="top" content="从0用户逐渐增加到目标并发数所需的时间，可避免瞬间高压导致服务器拒绝连接">
            <el-icon class="tip-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>
        <el-form-item label="目标Host">
          <el-input v-model="form.config.target_host" placeholder="可选，覆盖环境配置的Host" />
          <el-tooltip placement="top" content="不填则使用环境配置中的Host地址，填写后将覆盖环境配置">
            <el-icon class="tip-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>

        <!-- 错误率阈值自动停止 -->
        <el-form-item label="错误率阈值">
          <div style="display:flex;align-items:center;gap:12px;width:100%">
            <el-switch v-model="enableErrorThreshold" active-text="启用" inactive-text="关闭" />
            <el-slider
              v-if="enableErrorThreshold"
              v-model="form.config.error_rate_threshold"
              :min="1"
              :max="100"
              show-stops
              show-input
              style="flex:1"
            />
          </div>
          <div class="field-tip">启用后，当错误率连续 3 秒超过该阈值时，压测将自动停止（0 表示不启用）</div>
        </el-form-item>

        <!-- 固定模式配置 -->
        <template v-if="form.config.mode === 'fixed'">
          <el-form-item label="持续时间" prop="config.duration_seconds">
            <el-input-number v-model="form.config.duration_seconds" :min="1" :max="3600" />
            <span class="unit">秒（最大3600秒）</span>
            <el-tooltip placement="top" content="压测持续的总时长，期间保持目标并发数持续施压">
              <el-icon class="tip-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-form-item>
        </template>

        <!-- 循环模式配置 -->
        <template v-if="form.config.mode === 'loop'">
          <el-form-item label="循环次数" prop="config.loop_count">
            <el-input-number v-model="form.config.loop_count" :min="1" :max="100000" />
            <span class="unit">次（每个并发用户执行次数）</span>
            <el-tooltip placement="top" content="每个虚拟用户重复执行请求的总次数，总请求数 = 并发数 × 循环次数">
              <el-icon class="tip-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-form-item>
        </template>

        <!-- 梯度模式配置 -->
        <template v-if="form.config.mode === 'stepping'">
          <el-form-item label="梯度阶段" prop="config.steps">
            <div class="steps-list">
              <div v-for="(step, index) in form.config.steps" :key="index" class="step-item">
                <span class="step-label">第 {{ index + 1 }} 阶段</span>
                <el-input-number v-model="step.users" :min="1" :max="1000" placeholder="并发数" />
                <span class="step-sep">用户，持续</span>
                <el-input-number v-model="step.duration" :min="1" :max="3600" placeholder="秒" />
                <span class="step-sep">秒</span>
                <el-button type="danger" size="small" circle :icon="Delete" @click="removeStep(index)" />
              </div>
              <el-button type="primary" size="small" :icon="Plus" @click="addStep">添加阶段</el-button>
            </div>
            <div class="field-tip">分阶段逐步增加并发用户数，每阶段持续指定时间，用于探测系统性能拐点</div>
          </el-form-item>
        </template>

        <!-- 用例选择 -->
        <el-divider content-position="left">场景用例</el-divider>
        <el-form-item label="选择用例" prop="scene_items">
          <div class="case-selector">
            <el-transfer
              v-model="selectedCaseIds"
              :data="caseOptions"
              :titles="['可用用例', '已选用例']"
              filterable
              :filter-method="filterCase"
              filter-placeholder="搜索用例名称"
              style="width: 100%"
            />
          </div>
        </el-form-item>

        <!-- 已选用例配置 -->
        <el-form-item label="用例配置" v-if="selectedCases.length > 0">
          <div class="field-tip" style="margin-bottom: 8px;">
            <el-tag v-if="form.config.distribution_mode === 'fixed_ratio'" size="small" type="warning">固定比例</el-tag>
            <el-tag v-else size="small" type="info">随机权重</el-tag>
            {{ form.config.distribution_mode === 'fixed_ratio'
              ? '请求按下方「比例」严格循环分配，确保各接口请求数精确匹配比例'
              : '请求按下方「权重」概率随机分配，相同权重下请求数会有随机波动' }}
          </div>
          <el-table :data="selectedCases" size="small" border style="width: 100%">
            <el-table-column prop="case_name" label="用例名称" min-width="180" show-overflow-tooltip />
            <el-table-column prop="api_method" label="方法" width="70" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="getMethodType(row.api_method)">{{ row.api_method }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column width="120" align="center">
              <template #header>
                <span>{{ form.config.distribution_mode === 'fixed_ratio' ? '比例' : '权重' }}</span>
                <el-tooltip placement="top">
                  <template #content>
                    <div v-if="form.config.distribution_mode === 'fixed_ratio'">
                      固定比例模式下，比例决定严格循环的分配规律<br/>如比例 1:2 则按 A-B-B-A-B-B 循环分配
                    </div>
                    <div v-else>
                      权重越大，该接口被选中的概率越高<br/>相同权重时各接口概率均等
                    </div>
                  </template>
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <el-input-number v-model="row.weight" :min="1" :max="100" size="small" style="width: 90px" />
              </template>
            </el-table-column>
            <el-table-column width="120" align="center">
              <template #header>
                <span>间隔(ms)</span>
                <el-tooltip placement="top" content="每次请求执行后的等待间隔（毫秒），0表示不等待">
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <el-input-number v-model="row.delay_ms" :min="0" :max="60000" size="small" style="width: 90px" />
              </template>
            </el-table-column>
          </el-table>
        </el-form-item>

        <!-- CSV 参数化数据 -->
        <el-divider content-position="left">📄 参数化数据 (CSV)</el-divider>
        <el-form-item>
          <div style="width: 100%;">
            <el-alert
              type="info"
              :closable="false"
              style="margin-bottom: 12px;"
            >
              <template #title>
                <div style="font-weight: 600; margin-bottom: 6px;">CSV 参数化使用说明</div>
              </template>
              <div style="font-size: 13px; line-height: 1.8;">
                <div><b>Step 1 — 准备 CSV 文件</b></div>
                <div>　• 第一行必须是<b>英文列名</b>（如 username,password），不要包含中文表头</div>
                <div>　• 从第二行开始，每行为一组参数值，格式：普通 CSV（逗号分隔）</div>
                <div>　• 编码建议 UTF-8，行数上限 10000 行</div>
                <div style="margin-top: 4px;"><b>Step 2 — 上传 CSV</b></div>
                <div>　• 点击下方「上传 CSV 文件」按钮，上传成功后预览表格会显示前 5 行数据</div>
                <div>　• 记下你需要的<b>列名</b>（如 username、password）</div>
                <div style="margin-top: 4px;"><b>Step 3 — 在 API 用例中引用变量</b></div>
                <div>　• 写法固定格式：<code v-pre style="background:#f5f7fa;padding:2px 6px;border-radius:4px;">${{csv.列名}}</code></div>
                <div>　• <b>可使用的位置</b>：请求 Body、Query 参数值、Header 值、URL Path 段</div>
                <div>　• <b>Body 示例</b>（JSON）：<code v-pre style="background:#f5f7fa;padding:2px 6px;border-radius:4px;">{"user":"${{csv.username}}","pwd":"${{csv.password}}"}</code></div>
                <div>　• <b>URL 示例</b>：<code v-pre style="background:#f5f7fa;padding:2px 6px;border-radius:4px;">/api/users/${{csv.user_id}}/profile</code></div>
                <div style="margin-top: 4px;"><b>Step 4 — 选择分配策略（重要）</b></div>
                <div>　• <b>轮询</b>：所有并发用户按顺序循环取 CSV 行，适合数据可重复使用的场景</div>
                <div>　• <b>唯一</b>：将 CSV 行按并发数均分，每个用户独占一段，适合账号不可重复登录的场景</div>
                <div>　• <b>随机</b>：每次请求随机取一行，适合数据量大、不要求覆盖全部数据的场景</div>
                <div style="margin-top: 4px; color: #e6a23c;">⚠️ <b>注意</b>：如果并发用户数 > CSV 行数且选择「唯一」策略，会导致部分用户无数据可用，请确保 CSV 数据量充足。</div>
              </div>
            </el-alert>
            <div v-if="!csvInfo.hasCSV" style="display: flex; align-items: center; gap: 12px;">
              <el-upload
                accept=".csv"
                :show-file-list="false"
                :auto-upload="false"
                :on-change="handleCSVUpload"
              >
                <el-button type="primary" :icon="Upload">上传 CSV 文件</el-button>
              </el-upload>
              <span style="color: #909399; font-size: 13px;">支持 UTF-8 / GBK 编码，最多 10000 行</span>
            </div>
            <div v-else>
              <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                <el-tag size="small" type="success">{{ csvInfo.fileName }}</el-tag>
                <span style="color: #606266; font-size: 13px;">共 {{ csvInfo.rowCount }} 行</span>
                <el-button link type="danger" size="small" @click="handleCSVDelete">删除</el-button>
              </div>
              <el-table :data="csvInfo.preview" size="small" border style="width: 100%; max-width: 600px; margin-bottom: 12px;">
                <el-table-column
                  v-for="col in csvInfo.columns"
                  :key="col"
                  :prop="col"
                  :label="col"
                  min-width="100"
                />
              </el-table>
              <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 13px;">分配策略:</span>
                <el-radio-group v-model="csvInfo.strategy" size="small" @change="handleCSVStrategyChange">
                  <el-radio-button label="round_robin">轮询</el-radio-button>
                  <el-radio-button label="unique">唯一</el-radio-button>
                  <el-radio-button label="random">随机</el-radio-button>
                </el-radio-group>
                <el-tooltip placement="top">
                  <template #content>
                    <div>轮询: 每个请求按顺序取下一行，循环使用</div>
                    <div style="margin-top:4px;">唯一: 每个并发用户独占一段行号范围</div>
                    <div style="margin-top:4px;">随机: 每次请求随机取一行</div>
                  </template>
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="field-tip" style="margin-top: 8px;">
                💡 在 API 用例中使用 <code v-pre>${{csv.column_name}}</code> 即可引用 CSV 列数据
              </div>
            </div>
          </div>
        </el-form-item>

        <!-- 操作按钮 -->
        <el-form-item>
          <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
          <el-button @click="handleCancel">取消</el-button>
        </el-form-item>
      </el-form>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Delete, QuestionFilled, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { perfSceneApi, httpCaseApi } from '@/api'
import { perfSceneApi as perfSceneApiCSV } from '@/api/modules/perf'
import { ProjectStore } from '@/stores/module/ProjectStore'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()

const isEdit = computed(() => !!route.params.id)
const sceneId = computed(() => route.params.id)

const formRef = ref(null)
const saving = ref(false)
const allCases = ref([])
const selectedCaseIds = ref([])
const enableErrorThreshold = ref(false)

// CSV 参数化数据
const csvInfo = reactive({
  hasCSV: false,
  fileName: '',
  rowCount: 0,
  columns: [],
  preview: [],
  strategy: 'round_robin'
})

const form = reactive({
  name: '',
  description: '',
  config: {
    mode: 'fixed',
    distribution_mode: 'random_weight',
    concurrent_users: 10,
    ramp_up_seconds: 5,
    duration_seconds: 60,
    loop_count: 100,
    steps: [{ users: 10, duration: 30 }],
    target_host: '',
    error_rate_threshold: 50
  },
  scene_items: []
})

const rules = {
  name: [{ required: true, message: '请输入场景名称', trigger: 'blur' }],
  'config.mode': [{ required: true, message: '请选择压测模式', trigger: 'change' }],
  'config.concurrent_users': [{ required: true, message: '请设置并发用户数', trigger: 'change' }],
  'config.duration_seconds': [{ required: true, message: '请设置持续时间', trigger: 'change', validator: (rule, value, callback) => {
    if (form.config.mode === 'fixed' && !value) return callback(new Error('固定模式必须设置持续时间'))
    callback()
  }}],
  'config.loop_count': [{ required: true, message: '请设置循环次数', trigger: 'change', validator: (rule, value, callback) => {
    if (form.config.mode === 'loop' && !value) return callback(new Error('循环模式必须设置循环次数'))
    callback()
  }}],
  'config.steps': [{ required: true, message: '请设置梯度阶段', trigger: 'change', validator: (rule, value, callback) => {
    if (form.config.mode === 'stepping' && (!value || value.length === 0)) return callback(new Error('梯度模式必须至少设置一个阶段'))
    callback()
  }}]
}

const caseOptions = computed(() => {
  return allCases.value.map(c => ({
    key: c.id,
    label: `${c.name} [${c.api_method || ''}]`,
    disabled: false
  }))
})

const selectedCases = computed(() => {
  return selectedCaseIds.value.map(id => {
    const caseInfo = allCases.value.find(c => c.id === id)
    const existing = form.scene_items.find(item => item.case_id === id)
    return {
      case_id: id,
      case_name: caseInfo?.name || '未知',
      api_method: caseInfo?.api?.method || caseInfo?.api_method || '',
      weight: existing?.weight || 1,
      delay_ms: existing?.delay_ms || 0
    }
  })
})

const distModeTip = computed(() => {
  return form.config.distribution_mode === 'fixed_ratio'
    ? '按权重比例严格分配请求次数，确保各接口请求数精确匹配权重比（如权重1:1则各50%）'
    : '按权重概率随机选择接口，相同权重下请求数会有随机波动'
})

const filterCase = (query, item) => {
  return item.label.toLowerCase().includes(query.toLowerCase())
}

const getMethodType = (method) => {
  const map = { GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger', PATCH: 'info' }
  return map[method?.toUpperCase()] || ''
}

const onModeChange = (mode) => {
  // 清空不相关的字段验证
  if (mode === 'fixed') {
    form.config.loop_count = undefined
    form.config.steps = undefined
  } else if (mode === 'loop') {
    form.config.duration_seconds = undefined
    form.config.steps = undefined
  } else if (mode === 'stepping') {
    form.config.duration_seconds = undefined
    form.config.loop_count = undefined
    if (!form.config.steps || form.config.steps.length === 0) {
      form.config.steps = [{ users: 10, duration: 30 }]
    }
  }
}

const addStep = () => {
  if (!form.config.steps) form.config.steps = []
  form.config.steps.push({ users: 10, duration: 30 })
}

const removeStep = (index) => {
  form.config.steps.splice(index, 1)
}

const loadCases = async () => {
  if (!proStore.projectInfo?.id) return
  try {
    const res = await httpCaseApi.getList({ project_id: proStore.projectInfo.id, page: 1, size: 5000 })
    const body = res?.data ?? res
    allCases.value = Array.isArray(body) ? body : (body?.data ?? [])
  } catch (err) {
    console.error(err)
    ElMessage.error('加载用例列表失败')
  }
}

const loadScene = async () => {
  if (!isEdit.value) return
  try {
    const res = await perfSceneApi.getDetail(sceneId.value)
    const data = res.data || res
    form.name = data.name || ''
    form.description = data.description || ''
    if (data.config) {
      Object.assign(form.config, data.config)
      if (!form.config.mode) form.config.mode = 'fixed'
      if (!form.config.steps) form.config.steps = [{ users: 10, duration: 30 }]
      enableErrorThreshold.value = !!(data.config.error_rate_threshold && data.config.error_rate_threshold > 0)
    }
    if (data.scene_items) {
      form.scene_items = data.scene_items.map(item => ({
        case_id: item.case_id,
        weight: item.weight || 1,
        delay_ms: item.delay_ms || 0
      }))
      selectedCaseIds.value = form.scene_items.map(item => item.case_id)
    }
  } catch (err) {
    console.error(err)
    ElMessage.error('加载场景详情失败')
  }
}

const handleSave = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  if (selectedCaseIds.value.length === 0) {
    ElMessage.warning('请至少选择一个用例')
    return
  }

  saving.value = true
  try {
    const payload = {
      name: form.name,
      description: form.description,
      project_id: proStore.projectInfo.id,
      config: { ...form.config },
      scene_items: selectedCases.value.map(c => ({
        case_id: c.case_id,
        weight: c.weight,
        delay_ms: c.delay_ms
      }))
    }

    // 错误率阈值：未启用时设为 0
    if (!enableErrorThreshold.value) {
      payload.config.error_rate_threshold = 0
    }
    // 清理不需要的字段
    if (payload.config.mode === 'fixed') {
      delete payload.config.loop_count
      delete payload.config.steps
    } else if (payload.config.mode === 'loop') {
      delete payload.config.duration_seconds
      delete payload.config.steps
    } else if (payload.config.mode === 'stepping') {
      delete payload.config.duration_seconds
      delete payload.config.loop_count
      // 梯度模式保留 concurrent_users（后端 schema 要求），虽然执行时不使用
    }

    if (isEdit.value) {
      await perfSceneApi.update(sceneId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await perfSceneApi.create(payload)
      ElMessage.success('创建成功')
    }
    router.push('/perf-scenes')
  } catch (err) {
    console.error(err)
    ElMessage.error(isEdit.value ? '更新失败' : '创建失败')
  } finally {
    saving.value = false
  }
}

const handleCancel = () => {
  router.push('/perf-scenes')
}

// CSV 上传
const handleCSVUpload = async (file) => {
  const raw = file.raw
  if (!raw || !raw.name.endsWith('.csv')) {
    ElMessage.error('请选择 CSV 文件')
    return
  }
  try {
    const formData = new FormData()
    formData.append('file', raw)
    const res = await perfSceneApiCSV.uploadCSV(sceneId.value, formData)
    const data = res.data || res
    csvInfo.hasCSV = true
    csvInfo.fileName = data.file_name
    csvInfo.rowCount = data.row_count
    csvInfo.columns = data.columns || []
    csvInfo.preview = data.preview || []
    ElMessage.success('CSV 上传成功')
  } catch (err) {
    console.error(err)
    ElMessage.error('CSV 上传失败')
  }
}

// CSV 删除
const handleCSVDelete = async () => {
  try {
    await perfSceneApiCSV.deleteCSV(sceneId.value)
    csvInfo.hasCSV = false
    csvInfo.fileName = ''
    csvInfo.rowCount = 0
    csvInfo.columns = []
    csvInfo.preview = []
    csvInfo.strategy = 'round_robin'
    ElMessage.success('CSV 已删除')
  } catch (err) {
    console.error(err)
    ElMessage.error('删除失败')
  }
}

// CSV 策略变更
const handleCSVStrategyChange = async (val) => {
  try {
    await perfSceneApiCSV.updateCSVConfig(sceneId.value, { strategy: val, enabled: true })
    ElMessage.success('策略已更新')
  } catch (err) {
    console.error(err)
    ElMessage.error('策略更新失败')
  }
}

// 加载 CSV 预览
const loadCSVPreview = async () => {
  if (!isEdit.value || !sceneId.value) return
  try {
    const res = await perfSceneApiCSV.previewCSV(sceneId.value)
    const data = res.data || res
    if (data.row_count > 0) {
      csvInfo.hasCSV = true
      csvInfo.fileName = data.file_name
      csvInfo.rowCount = data.row_count
      csvInfo.columns = data.columns || []
      csvInfo.preview = data.preview || []
      csvInfo.strategy = data.strategy || 'round_robin'
    }
  } catch (err) {
    // 忽略错误，可能没有 CSV
  }
}

onMounted(() => {
  loadCases()
  loadScene()
  loadCSVPreview()
})
</script>

<style scoped>
.unit {
  margin-left: 8px;
  color: #999;
  font-size: 13px;
}
.mode-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.mode-hint {
  margin-top: 0;
}
.field-tip {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}
.tip-icon {
  margin-left: 6px;
  color: #909399;
  cursor: pointer;
  font-size: 14px;
  vertical-align: middle;
}
.tip-icon:hover {
  color: #409eff;
}
.case-selector {
  display: flex;
  justify-content: center;
}
.case-selector :deep(.el-transfer) {
  display: flex;
  align-items: center;
  gap: 20px;
}
.case-selector :deep(.el-transfer-panel) {
  width: 320px;
}
.steps-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.step-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #f5f7fa;
  padding: 10px 14px;
  border-radius: 6px;
}
.step-label {
  font-weight: 600;
  color: #606266;
  min-width: 70px;
}
.step-sep {
  color: #999;
  font-size: 13px;
}
</style>
