<template>
  <el-drawer
    v-model="visible"
    size="720px"
    direction="rtl"
    destroy-on-close
    class="defect-detail-drawer"
    @closed="onClosed"
  >
    <template #header>
      <div class="drawer-head">
        <div class="title-line">
          <span class="key">{{ isCreate ? '新建缺陷' : (detail.defect_key || '缺陷详情') }}</span>
          <el-tag v-if="!isCreate" size="small" :type="statusTagType(form.status)">
            {{ statusLabel(form.status) }}
          </el-tag>
          <el-tag v-if="!isCreate" size="small" type="danger" effect="plain">
            {{ severityLabel(form.severity) }}
          </el-tag>
        </div>
        <div class="sub" v-if="!isCreate && form.title">{{ form.title }}</div>
      </div>
    </template>

    <div v-loading="loading" class="drawer-body">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="基本信息" name="basic">
          <el-form label-position="top" class="form defect-form">
            <el-form-item label="标题" required>
              <el-input v-model="form.title" :disabled="!canEdit" maxlength="500" show-word-limit />
            </el-form-item>
            <div class="form-grid">
              <el-form-item label="严重度">
                <el-select v-model="form.severity" :disabled="!canEdit" style="width: 100%">
                  <el-option v-for="s in severityOptions" :key="s" :label="severityLabel(s)" :value="s" />
                </el-select>
              </el-form-item>
              <el-form-item label="优先级">
                <el-select v-model="form.priority" :disabled="!canEdit" style="width: 100%">
                  <el-option v-for="p in priorityOptions" :key="p" :label="defectPriorityLabel(p)" :value="p" />
                </el-select>
              </el-form-item>
            </div>
            <el-form-item label="状态" v-if="!isCreate">
              <template v-if="canEdit">
                <el-select v-model="form.status" style="width: 100%">
                  <el-option
                    v-for="s in statusSelectOptions"
                    :key="s"
                    :label="statusLabel(s)"
                    :value="s"
                  />
                </el-select>
                <div class="field-hint">管理员强制改状态；日常流转请用下方「处理」按钮</div>
              </template>
              <el-tag v-else :type="statusTagType(form.status)">{{ statusLabel(form.status) }}</el-tag>
            </el-form-item>
            <el-form-item label="版本">
              <ReleaseSelect
                v-if="projectId"
                v-model="form.release_id"
                :project-id="projectId"
                :exclude-terminal="isCreate"
                :disabled="!canEdit"
                placeholder="关联版本（可选）"
                width="100%"
              />
              <div v-if="isCreate" class="field-hint">选择版本后，关联需求/用例将优先列出该版本范围</div>
            </el-form-item>
            <div class="form-grid">
              <el-form-item label="负责人">
                <ProjectMemberSelect
                  v-if="projectId"
                  v-model="form.assignee_id"
                  :project-id="projectId"
                  :disabled="!canEdit"
                  placeholder="选择负责人"
                  width="100%"
                />
              </el-form-item>
              <el-form-item label="提报人">
                <ProjectMemberSelect
                  v-if="projectId"
                  v-model="form.reporter_id"
                  :project-id="projectId"
                  :disabled="!canEdit"
                  placeholder="选择提报人"
                  width="100%"
                />
              </el-form-item>
            </div>
            <el-form-item v-if="!isCreate" label="当前处理人">
              <ProjectMemberSelect
                v-if="projectId"
                v-model="form.handler_id"
                :project-id="projectId"
                :disabled="!canEdit"
                placeholder="选择当前处理人"
                width="100%"
              />
            </el-form-item>
            <el-form-item v-if="!isCreate" label="缺陷归属人">
              <ProjectMemberSelect
                v-if="projectId"
                v-model="form.attributor_id"
                :project-id="projectId"
                :disabled="!canEdit"
                clearable
                placeholder="引入问题者（可与处理人不同）"
                width="100%"
              />
              <div class="field-hint">处理时可指定；也可在此直接维护</div>
            </el-form-item>
            <div class="form-grid">
              <el-form-item label="发现版本">
                <el-select
                  v-model="form.found_in"
                  :disabled="!canEdit"
                  filterable
                  allow-create
                  clearable
                  default-first-option
                  placeholder="选择或输入，如 v1.6.0"
                  style="width: 100%"
                >
                  <el-option v-for="v in versionHintOptions" :key="`f-${v}`" :label="v" :value="v" />
                </el-select>
              </el-form-item>
              <el-form-item label="修复版本">
                <el-select
                  v-model="form.fixed_in"
                  :disabled="!canEdit"
                  filterable
                  allow-create
                  clearable
                  default-first-option
                  placeholder="选择或输入，如 v1.6.1"
                  style="width: 100%"
                >
                  <el-option v-for="v in versionHintOptions" :key="`x-${v}`" :label="v" :value="v" />
                </el-select>
              </el-form-item>
            </div>
            <el-form-item label="外部系统">
              <el-select
                v-model="form.external_system"
                :disabled="!canEdit"
                filterable
                allow-create
                clearable
                default-first-option
                placeholder="Jira / 禅道 / 其他"
                style="width: 100%"
              >
                <el-option label="Jira" value="Jira" />
                <el-option label="禅道" value="禅道" />
                <el-option label="其他" value="其他" />
              </el-select>
            </el-form-item>
            <div class="form-grid">
              <el-form-item label="外部编号">
                <el-input v-model="form.external_key" :disabled="!canEdit" />
              </el-form-item>
              <el-form-item label="外部链接">
                <el-input v-model="form.external_url" :disabled="!canEdit" placeholder="https://..." />
              </el-form-item>
            </div>
            <template v-if="isCreate">
              <el-form-item label="关联需求">
                <el-select
                  v-model="draftRequirementIds"
                  multiple
                  filterable
                  clearable
                  collapse-tags
                  collapse-tags-tooltip
                  :loading="reqLoading"
                  :placeholder="scopeReleaseId ? '从当前版本选择需求' : '请先选择版本，或按名称搜索'"
                  style="width: 100%"
                  @visible-change="onRequirementDropdown"
                >
                  <el-option
                    v-for="r in requirementOptions"
                    :key="r.id"
                    :label="r.label"
                    :value="r.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="关联用例">
                <el-select
                  v-model="draftCaseIds"
                  multiple
                  filterable
                  clearable
                  collapse-tags
                  collapse-tags-tooltip
                  :loading="caseLoading"
                  :placeholder="scopeReleaseId ? '从当前版本选择用例' : '请先选择版本，或按标题搜索'"
                  style="width: 100%"
                  @visible-change="onCaseDropdown"
                >
                  <el-option
                    v-for="c in caseOptions"
                    :key="c.id"
                    :label="c.label"
                    :value="c.id"
                  />
                </el-select>
              </el-form-item>
            </template>
            <el-form-item v-if="!isCreate" label="元信息">
              <div class="meta">
                <span>创建：{{ detail.create_by || '—' }} · {{ formatTime(detail.create_time) }}</span>
                <span>更新：{{ formatTime(detail.update_time) }}</span>
              </div>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="详情与附件" name="detail">
          <el-form label-width="96px">
            <el-form-item label="描述">
              <el-input
                v-model="form.description"
                type="textarea"
                :rows="12"
                :disabled="!canEdit && !canProcessCurrent"
                placeholder="前置条件 / 操作步骤 / 实际结果 / 预期结果"
              />
            </el-form-item>
            <el-form-item label="图片/附件">
              <DefectAttachments
                v-if="projectId"
                v-model="form.attachments"
                :project-id="projectId"
                :disabled="!canEdit"
              />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane v-if="!isCreate" label="关联" name="links">
          <div class="pane-toolbar" v-if="canEdit">
            <el-button size="small" type="primary" @click="openAddLink">添加关联</el-button>
          </div>
          <el-table :data="detail.links || []" border size="small" empty-text="暂无关联">
            <el-table-column prop="link_type" label="类型" width="120">
              <template #default="{ row }">{{ linkTypeLabel(row.link_type) }}</template>
            </el-table-column>
            <el-table-column label="对象" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">{{ linkSummary(row) }}</template>
            </el-table-column>
            <el-table-column label="跳转" width="140">
              <template #default="{ row }">
                <el-button
                  v-if="row.run_id"
                  link
                  type="primary"
                  @click="goRun(row.run_id)"
                >运行</el-button>
                <el-button
                  v-else-if="row.functional_case_id"
                  link
                  type="primary"
                  @click="goCase(row.functional_case_id)"
                >用例</el-button>
                <el-button
                  v-else-if="row.requirement_id"
                  link
                  type="primary"
                  @click="openReqPreview(row.requirement_id)"
                >预览</el-button>
                <el-button
                  v-if="row.requirement_id"
                  link
                  @click="goRequirement(row.requirement_id)"
                >工作台</el-button>
                <a
                  v-else-if="safeExternalUrl(row.external_url)"
                  :href="safeExternalUrl(row.external_url)"
                  target="_blank"
                  rel="noopener noreferrer"
                >外链</a>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column v-if="canEdit" label="操作" width="80">
              <template #default="{ row }">
                <el-button link type="danger" @click="removeLink(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane v-if="!isCreate" label="处理记录" name="activity">
          <el-form v-if="canEdit" label-width="96px" class="handle-form">
            <el-form-item label="处理方案">
              <el-select v-model="form.resolution_type" clearable placeholder="选择方案类型" style="width: 100%">
                <el-option
                  v-for="opt in resolutionOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="处理说明">
              <el-input v-model="form.resolution_detail" type="textarea" :rows="3" placeholder="如何处理的、验证情况等" />
            </el-form-item>
            <el-form-item label="产生原因">
              <el-input v-model="form.root_cause" type="textarea" :rows="2" placeholder="根因分类或简述" />
            </el-form-item>
            <el-form-item label="缺陷归属人">
              <ProjectMemberSelect
                v-if="projectId"
                v-model="form.attributor_id"
                :project-id="projectId"
                clearable
                placeholder="引入问题者（可与处理人不同）"
                width="100%"
              />
            </el-form-item>
          </el-form>
          <div class="comment-box" v-if="canEdit">
            <el-input
              v-model="commentText"
              type="textarea"
              :rows="3"
              placeholder="添加处理意见"
              maxlength="10000"
              show-word-limit
            />
            <el-button
              type="primary"
              size="small"
              class="comment-btn"
              :loading="commenting"
              @click="submitComment"
            >发表评论</el-button>
          </div>
          <div v-if="(detail.comments || []).length" class="comments">
            <div v-for="c in detail.comments" :key="'c-' + c.id" class="comment-item">
              <div class="c-head">
                <strong>{{ c.create_by || '—' }}</strong>
                <span>{{ formatTime(c.create_time) }}</span>
                <el-button
                  v-if="canEdit"
                  link
                  type="danger"
                  size="small"
                  @click="removeComment(c)"
                >删除</el-button>
              </div>
              <div class="c-body">{{ c.body }}</div>
            </div>
          </div>
          <el-timeline class="timeline">
            <el-timeline-item
              v-for="a in detail.activities || []"
              :key="'a-' + a.id"
              :timestamp="formatTime(a.create_time)"
              placement="top"
            >
              {{ activityLabel(a) }}
            </el-timeline-item>
          </el-timeline>
          <el-empty
            v-if="!(detail.comments || []).length && !(detail.activities || []).length"
            description="暂无处理记录"
          />
        </el-tab-pane>

        <el-tab-pane v-if="!isCreate" label="测试计划" name="plans">
          <el-table :data="detail.related_plans || []" border size="small" empty-text="暂无关联计划">
            <el-table-column prop="plan_name" label="计划" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.plan_name || (row.plan_id ? `#${row.plan_id}` : '—') }}</template>
            </el-table-column>
            <el-table-column prop="run_item_title" label="运行项" min-width="160" show-overflow-tooltip />
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button v-if="row.run_id" link type="primary" @click="goRun(row.run_id)">打开运行</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <div class="drawer-footer">
        <el-button
          v-if="canEdit && !isCreate"
          type="danger"
          plain
          :loading="removing"
          @click="removeDefect"
        >删除</el-button>
        <el-button
          v-if="!isCreate && canProcessCurrent && processAction"
          type="warning"
          @click="openProcess"
        >{{ processAction.label }}</el-button>
        <div class="footer-spacer" />
        <el-button @click="visible = false">关闭</el-button>
        <el-button v-if="canEdit" type="primary" :loading="saving" @click="save">保存</el-button>
      </div>
    </template>

    <el-dialog
      v-model="processVisible"
      :title="processTitle"
      width="520px"
      destroy-on-close
      append-to-body
      class="defect-process-dialog"
    >
      <el-form label-width="100px" class="process-form">
        <el-form-item label="当前状态">
          <el-tag :type="statusTagType(form.status)">{{ statusLabel(form.status) }}</el-tag>
          <span class="process-arrow">→</span>
          <el-tag type="warning">{{ statusLabel(processForm.to_status) }}</el-tag>
        </el-form-item>
        <el-form-item label="处理意见">
          <el-input
            v-model="processForm.comment"
            type="textarea"
            :rows="4"
            placeholder="说明本次处理内容、验证结果或转交原因"
          />
        </el-form-item>
        <el-form-item label="负责人">
          <ProjectMemberSelect
            v-if="projectId"
            v-model="processForm.assignee_id"
            :project-id="projectId"
            clearable
            placeholder="可改派负责人"
            width="100%"
          />
        </el-form-item>
        <el-form-item label="处理人">
          <ProjectMemberSelect
            v-if="projectId"
            v-model="processForm.handler_id"
            :project-id="projectId"
            clearable
            placeholder="当前处理人"
            width="100%"
          />
        </el-form-item>
        <el-form-item label="缺陷归属人">
          <ProjectMemberSelect
            v-if="projectId"
            v-model="processForm.attributor_id"
            :project-id="projectId"
            clearable
            placeholder="引入问题者（可选）"
            width="100%"
          />
        </el-form-item>
        <el-form-item v-if="processNeedsResolution" label="解决方案">
          <el-select v-model="processForm.resolution_type" clearable placeholder="选择方案" style="width: 100%">
            <el-option
              v-for="opt in resolutionOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="processNeedsResolution" label="处理说明">
          <el-input v-model="processForm.resolution_detail" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="processVisible = false">取消</el-button>
        <el-button type="primary" :loading="processSaving" @click="submitProcess">确认提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="linkDialogVisible" title="添加关联" width="520px" append-to-body class="defect-link-dialog">
      <el-form label-position="top" class="link-form">
        <el-form-item label="类型">
          <el-select v-model="linkForm.link_type" style="width: 100%" @change="onLinkTypeChange">
            <el-option label="需求" value="requirement" />
            <el-option label="功能用例" value="functional_case" />
            <el-option label="自动化资产" value="asset" />
            <el-option label="运行项" value="run_item" />
            <el-option label="外部链接" value="external" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="linkForm.link_type === 'requirement'" label="需求">
          <el-select
            v-model="linkForm.requirement_id"
            filterable
            remote
            clearable
            :remote-method="searchRequirements"
            :loading="reqLoading"
            placeholder="按名称搜索需求"
            style="width: 100%"
            @visible-change="(v) => v && searchRequirements('')"
          >
            <el-option v-for="r in requirementOptions" :key="r.id" :label="r.label" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="linkForm.link_type === 'functional_case'" label="功能用例">
          <el-select
            v-model="linkForm.functional_case_id"
            filterable
            remote
            clearable
            :remote-method="searchCases"
            :loading="caseLoading"
            placeholder="按标题搜索用例"
            style="width: 100%"
            @visible-change="(v) => v && searchCases('')"
          >
            <el-option v-for="c in caseOptions" :key="c.id" :label="c.label" :value="c.id" />
          </el-select>
        </el-form-item>
        <template v-if="linkForm.link_type === 'asset'">
          <el-form-item label="资产类型">
            <el-select v-model="linkForm.asset_type" style="width: 100%" @change="() => searchAssets('')">
              <el-option label="UI 用例" value="ui_case" />
              <el-option label="App 用例" value="app_case" />
              <el-option label="API 用例" value="api_case" />
              <el-option label="压测场景" value="perf_scene" />
            </el-select>
          </el-form-item>
          <el-form-item label="资产">
            <el-select
              v-model="linkForm.asset_id"
              filterable
              remote
              clearable
              :remote-method="searchAssets"
              :loading="assetLoading"
              placeholder="按名称搜索"
              style="width: 100%"
              @visible-change="(v) => v && searchAssets('')"
            >
              <el-option v-for="a in assetOptions" :key="a.id" :label="a.label" :value="a.id" />
            </el-select>
          </el-form-item>
        </template>
        <el-form-item v-if="linkForm.link_type === 'run_item'" label="运行项 ID">
          <el-input-number v-model="linkForm.run_item_id" :min="1" controls-position="right" style="width: 100%" />
          <div class="field-hint">建议从测试计划运行页一键提缺陷自动关联；此处仅补录</div>
        </el-form-item>
        <el-form-item v-if="linkForm.link_type === 'external'" label="URL">
          <el-input v-model="linkForm.external_url" placeholder="https://" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="linkForm.note" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="linkDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="linking" @click="submitLink">添加</el-button>
      </template>
    </el-dialog>
  </el-drawer>

  <RequirementPreviewDrawer
    v-model="reqPreviewVisible"
    :ai-requirement-id="previewReqId"
    :project-id="projectId"
    :release-id="scopeReleaseId"
    :show-actions="false"
  />
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { aiRequirementApi, aiFunctionalCaseApi } from '@/api/modules/ai.js'
import { uiCaseApi } from '@/api/modules/ui'
import { appCaseApi } from '@/api/modules/app'
import { httpCaseApi } from '@/api/modules/http'
import { perfSceneApi } from '@/api/modules/perf'
import { testDefectApi, testReleaseApi } from '@/api/testManagement'
import { UserStore } from '@/stores/module/UserStore'
import { safeExternalUrl } from '@/utils/safeExternalUrl'
import { DEFECT_QUICK_TRANSITIONS, canUserProcessDefect, DEFECT_DESCRIPTION_TEMPLATE } from '@/utils/defectDisplay'
import { DEFECT_RESOLUTION_OPTIONS, defectPriorityLabel, defectResolutionLabel } from '@/utils/tmDisplay'
import DefectAttachments from './DefectAttachments.vue'
import ProjectMemberSelect from './ProjectMemberSelect.vue'
import ReleaseSelect from './ReleaseSelect.vue'
import RequirementPreviewDrawer from './RequirementPreviewDrawer.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  canEdit: { type: Boolean, default: false },
  defaultReleaseId: { type: Number, default: null },
  neighborIds: { type: Array, default: () => [] }
})

const emit = defineEmits(['saved', 'deleted', 'closed'])

const router = useRouter()
const uStore = UserStore()

const visible = ref(false)
const loading = ref(false)
const saving = ref(false)
const removing = ref(false)
const commenting = ref(false)
const linking = ref(false)
const isCreate = ref(false)
const activeTab = ref('basic')
const commentText = ref('')
const detail = ref({})
const defectId = ref(null)

const form = reactive({
  title: '',
  description: '',
  severity: 'major',
  priority: 'p2',
  status: 'open',
  release_id: null,
  assignee_id: null,
  reporter_id: null,
  handler_id: null,
  attributor_id: null,
  found_in: '',
  fixed_in: '',
  external_system: '',
  external_key: '',
  external_url: '',
  resolution_type: null,
  resolution_detail: '',
  root_cause: '',
  attachments: []
})

const canView = computed(() => uStore.hasPermission('test_defect:view'))
const scopeReleaseId = computed(() => form.release_id || props.defaultReleaseId || null)
const canProcessCurrent = computed(() =>
  canUserProcessDefect(detail.value, uStore.userInfo, {
    canView: canView.value,
    canEdit: props.canEdit
  })
)
const processAction = computed(() => DEFECT_QUICK_TRANSITIONS[form.status] || null)
const processTitle = computed(() => {
  const key = detail.value?.defect_key || '缺陷'
  return processAction.value ? `${processAction.value.label} · ${key}` : `处理 · ${key}`
})

const STATUS_TRANSITIONS = {
  open: ['open', 'in_progress', 'rejected', 'closed'],
  in_progress: ['in_progress', 'resolved', 'rejected', 'open', 'closed'],
  resolved: ['resolved', 'verified', 'in_progress', 'open'],
  verified: ['verified', 'closed', 'in_progress'],
  closed: ['closed', 'open'],
  rejected: ['rejected', 'open']
}

const severityOptions = ['blocker', 'critical', 'major', 'minor']
const priorityOptions = ['p0', 'p1', 'p2', 'p3']
const resolutionOptions = DEFECT_RESOLUTION_OPTIONS

const linkDialogVisible = ref(false)
const linkForm = reactive({
  link_type: 'requirement',
  run_item_id: null,
  functional_case_id: null,
  requirement_id: null,
  asset_type: 'ui_case',
  asset_id: null,
  external_url: '',
  note: ''
})
const draftRequirementIds = ref([])
const draftCaseIds = ref([])
const requirementOptions = ref([])
const reqPreviewVisible = ref(false)
const previewReqId = ref(null)
const caseOptions = ref([])
const assetOptions = ref([])
const versionHintOptions = ref([])
const reqLoading = ref(false)
const caseLoading = ref(false)
const assetLoading = ref(false)
const processVisible = ref(false)
const processSaving = ref(false)
const processForm = reactive({
  to_status: '',
  comment: '',
  assignee_id: null,
  handler_id: null,
  attributor_id: null,
  resolution_type: null,
  resolution_detail: ''
})
const processNeedsResolution = computed(() =>
  ['resolved', 'verified', 'closed'].includes(processForm.to_status)
)

const originalStatus = computed(() => detail.value.status || 'open')
const statusSelectOptions = computed(() => {
  if (isCreate.value) return ['open']
  return STATUS_TRANSITIONS[originalStatus.value] || [originalStatus.value]
})

const statusLabel = (s) =>
  ({
    open: '打开',
    in_progress: '处理中',
    resolved: '已修复',
    verified: '已验证',
    closed: '已关闭',
    rejected: '已拒绝'
  }[s] || s)
const severityLabel = (s) =>
  ({ blocker: '阻塞', critical: '严重', major: '一般', minor: '轻微' }[s] || s)
const statusTagType = (s) =>
  ({
    open: 'danger',
    in_progress: 'warning',
    resolved: 'success',
    verified: 'success',
    closed: 'info',
    rejected: 'info'
  }[s] || '')
const formatTime = (v) => (v ? String(v).replace('T', ' ').slice(0, 19) : '—')
const linkTypeLabel = (t) =>
  ({
    run_item: '运行项',
    functional_case: '功能用例',
    requirement: '需求',
    asset: '自动化资产',
    external: '外部链接'
  }[t] || t)

const linkSummary = (row) => {
  if (row.link_type === 'run_item') {
    return row.run_item_title || `运行项 #${row.run_item_id}`
  }
  if (row.link_type === 'functional_case') {
    return row.functional_case_title || `用例 #${row.functional_case_id}`
  }
  if (row.link_type === 'requirement') {
    return row.requirement_title || `需求 #${row.requirement_id}`
  }
  if (row.link_type === 'asset') {
    return `${row.asset_type || ''} #${row.asset_id || ''}`
  }
  return row.external_url || '—'
}

const searchRequirements = async (q = '') => {
  if (!props.projectId) return
  reqLoading.value = true
  try {
    const rid = scopeReleaseId.value
    if (rid) {
      const res = await testReleaseApi.listRequirements(rid, props.projectId)
      const rows = res.data?.data || []
      const kw = String(q || '').trim().toLowerCase()
      requirementOptions.value = (Array.isArray(rows) ? rows : [])
        .map((r) => {
          const m = String(r.requirement_key || '').match(/^REQ-(\d+)$/i)
          const aiId = m ? Number(m[1]) : null
          const label = r.title
            ? `${r.requirement_key || ''} · ${r.title}`.trim()
            : (r.requirement_key || `需求 #${r.id}`)
          return { id: aiId, label }
        })
        .filter((r) => r.id != null)
        .filter((r) => !kw || String(r.label).toLowerCase().includes(kw))
      return
    }
    const res = await aiRequirementApi.getList({
      project_id: props.projectId,
      keyword: q || undefined,
      page: 1,
      size: 30
    })
    const rows = res.data?.data?.data || res.data?.data || []
    requirementOptions.value = (Array.isArray(rows) ? rows : []).map((r) => ({
      id: r.id,
      label: r.name || `需求 #${r.id}`
    }))
  } catch {
    requirementOptions.value = []
  } finally {
    reqLoading.value = false
  }
}

const searchCases = async (q = '') => {
  if (!props.projectId) return
  caseLoading.value = true
  try {
    const rid = scopeReleaseId.value
    if (rid) {
      const res = await testReleaseApi.listScopes(rid, props.projectId, {
        keyword: q || undefined
      })
      const rows = res.data?.data || []
      caseOptions.value = (Array.isArray(rows) ? rows : [])
        .map((c) => ({
          id: c.functional_case_id,
          label: c.case_title ? `${c.case_title} (#${c.functional_case_id})` : `用例 #${c.functional_case_id}`
        }))
        .filter((c) => c.id != null)
      return
    }
    const res = await aiFunctionalCaseApi.getList({
      project_id: props.projectId,
      keyword: q || undefined,
      page: 1,
      page_size: 30,
      size: 30
    })
    const rows = res.data?.data?.data || res.data?.data || []
    caseOptions.value = (Array.isArray(rows) ? rows : []).map((c) => ({
      id: c.id,
      label: c.title ? `${c.title} (#${c.id})` : `用例 #${c.id}`
    }))
  } catch {
    caseOptions.value = []
  } finally {
    caseLoading.value = false
  }
}

const onReleaseChange = () => {
  draftRequirementIds.value = []
  draftCaseIds.value = []
  searchRequirements('')
  searchCases('')
}

watch(
  () => form.release_id,
  (nid, oid) => {
    if (!isCreate.value) return
    if (nid === oid) return
    onReleaseChange()
  }
)

const onRequirementDropdown = (open) => {
  if (open) searchRequirements('')
}

const onCaseDropdown = (open) => {
  if (open) searchCases('')
}

const normalizeAssetList = (res) => {
  const data = res?.data?.data
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.items)) return data.items
  if (Array.isArray(data?.list)) return data.list
  return []
}

const searchAssets = async (q = '') => {
  if (!props.projectId) return
  assetLoading.value = true
  try {
    const type = linkForm.asset_type
    const kw = String(q || '').trim()
    let rows = []
    if (type === 'ui_case') {
      const res = await uiCaseApi.getList({
        project_id: props.projectId,
        page: 1,
        size: 30,
        name: kw || undefined
      })
      rows = normalizeAssetList(res)
    } else if (type === 'app_case') {
      const res = await appCaseApi.list({
        project_id: props.projectId,
        page: 1,
        size: 30,
        name: kw || undefined
      })
      rows = normalizeAssetList(res)
    } else if (type === 'api_case') {
      const res = await httpCaseApi.getList({
        project_id: props.projectId,
        page: 1,
        size: 30,
        keyword: kw || undefined
      })
      rows = normalizeAssetList(res)
    } else if (type === 'perf_scene') {
      const res = await perfSceneApi.getList({
        project_id: props.projectId,
        page: 1,
        size: 30,
        keyword: kw || undefined
      })
      rows = normalizeAssetList(res)
    }
    assetOptions.value = rows.map((a) => ({
      id: Number(a.id),
      label: `${a.name || a.title || '未命名'}（#${a.id}）`
    })).filter((a) => Number.isFinite(a.id) && a.id > 0)
  } catch {
    assetOptions.value = []
  } finally {
    assetLoading.value = false
  }
}

const loadVersionHints = async () => {
  if (!props.projectId) return
  try {
    const res = await testReleaseApi.list({ project_id: props.projectId })
    const rows = res.data?.data || []
    const keys = []
    for (const r of rows) {
      if (r.release_key) keys.push(r.release_key)
      if (r.name && r.name !== r.release_key) keys.push(r.name)
    }
    versionHintOptions.value = [...new Set(keys)].slice(0, 40)
  } catch {
    versionHintOptions.value = []
  }
}

const onLinkTypeChange = () => {
  linkForm.run_item_id = null
  linkForm.functional_case_id = null
  linkForm.requirement_id = null
  linkForm.asset_id = null
  linkForm.external_url = ''
}

const activityLabel = (a) => {
  const actor = a.actor || '系统'
  if (a.action === 'created') return `${actor} 创建了缺陷`
  if (a.action === 'status_change') {
    return `${actor} 将状态从「${statusLabel(a.from_value)}」改为「${statusLabel(a.to_value)}」`
  }
  if (a.action === 'assignee_change') {
    return `${actor} 变更了负责人（${a.from_value || '空'} → ${a.to_value || '空'}）`
  }
  if (a.action === 'handler_change') {
    return `${actor} 变更了当前处理人（${a.from_value || '空'} → ${a.to_value || '空'}）`
  }
  if (a.action === 'attributor_change') {
    return `${actor} 变更了缺陷归属人（${a.from_value || '空'} → ${a.to_value || '空'}）`
  }
  if (a.action === 'resolution_change') {
    return `${actor} 更新处理方案为「${defectResolutionLabel(a.to_value)}」`
  }
  if (a.action === 'comment') return `${actor} 发表了评论`
  if (a.action === 'link_add') return `${actor} 添加了关联（${linkTypeLabel(a.to_value)}）`
  if (a.action === 'link_remove') return `${actor} 移除了关联（${linkTypeLabel(a.from_value)}）`
  return `${actor} · ${a.action}`
}

const resetForm = (seed = {}) => {
  form.title = seed.title || ''
  form.description =
    seed.description != null && String(seed.description).trim()
      ? seed.description
      : (isCreate.value ? DEFECT_DESCRIPTION_TEMPLATE : '')
  form.severity = seed.severity || 'major'
  form.priority = seed.priority || 'p2'
  form.status = seed.status || 'open'
  form.release_id = seed.release_id ?? null
  form.assignee_id = seed.assignee_id ?? null
  form.reporter_id = seed.reporter_id ?? (uStore.userInfo?.id || null)
  form.handler_id = seed.handler_id ?? null
  form.attributor_id = seed.attributor_id ?? null
  form.found_in = seed.found_in || ''
  form.fixed_in = seed.fixed_in || ''
  form.external_system = seed.external_system || ''
  form.external_key = seed.external_key || ''
  form.external_url = seed.external_url || ''
  form.resolution_type = seed.resolution_type ?? null
  form.resolution_detail = seed.resolution_detail || ''
  form.root_cause = seed.root_cause || ''
  form.attachments = Array.isArray(seed.attachments) ? [...seed.attachments] : []
}

const applyDetail = (data) => {
  detail.value = data || {}
  defectId.value = data?.id || null
  resetForm(data || {})
}

const loadDetail = async (id) => {
  loading.value = true
  try {
    const res = await testDefectApi.get(id, props.projectId)
    applyDetail(res.data?.data || {})
  } finally {
    loading.value = false
  }
}

const openCreate = (seed = {}) => {
  isCreate.value = true
  activeTab.value = 'basic'
  commentText.value = ''
  detail.value = {}
  defectId.value = null
  draftRequirementIds.value = []
  draftCaseIds.value = []
  resetForm({
    ...seed,
    release_id: seed.release_id ?? props.defaultReleaseId ?? null
  })
  loadVersionHints()
  searchRequirements('')
  searchCases('')
  visible.value = true
}

const open = async (id, opts = {}) => {
  isCreate.value = false
  activeTab.value = opts.tab || 'basic'
  commentText.value = ''
  visible.value = true
  loadVersionHints()
  await loadDetail(id)
}

const onClosed = () => {
  emit('closed')
}

const openProcess = () => {
  const action = processAction.value
  if (!action || !canProcessCurrent.value) return
  processForm.to_status = action.to
  processForm.comment = ''
  processForm.assignee_id = form.assignee_id ?? null
  processForm.handler_id = form.handler_id ?? (uStore.userInfo?.id || null)
  processForm.attributor_id = form.attributor_id ?? null
  processForm.resolution_type = form.resolution_type ?? null
  processForm.resolution_detail = form.resolution_detail || ''
  processVisible.value = true
}

const submitProcess = async () => {
  if (!defectId.value) return
  processSaving.value = true
  try {
    await testDefectApi.transition(defectId.value, props.projectId, {
      to_status: processForm.to_status,
      comment: processForm.comment || null,
      assignee_id: processForm.assignee_id,
      handler_id: processForm.handler_id,
      attributor_id: processForm.attributor_id,
      resolution_type: processForm.resolution_type,
      resolution_detail: processForm.resolution_detail || null
    })
    ElMessage.success('已提交处理')
    processVisible.value = false
    await loadDetail(defectId.value)
    emit('saved')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '处理失败')
  } finally {
    processSaving.value = false
  }
}

const payloadFromForm = () => ({
  title: form.title.trim(),
  description: form.description || null,
  severity: form.severity,
  priority: form.priority,
  status: form.status,
  release_id: form.release_id,
  assignee_id: form.assignee_id,
  reporter_id: form.reporter_id,
  handler_id: form.handler_id,
  attributor_id: form.attributor_id,
  found_in: form.found_in || null,
  fixed_in: form.fixed_in || null,
  resolution_type: form.resolution_type || null,
  resolution_detail: form.resolution_detail || null,
  root_cause: form.root_cause || null,
  external_system: form.external_system || null,
  external_key: form.external_key || null,
  external_url: form.external_url || null,
  attachments: form.attachments || []
})

const save = async () => {
  if (!form.title.trim()) {
    ElMessage.warning('请填写标题')
    activeTab.value = 'basic'
    return
  }
  saving.value = true
  try {
    if (isCreate.value) {
      const links = []
      for (const rid of draftRequirementIds.value || []) {
        links.push({ link_type: 'requirement', requirement_id: rid })
      }
      for (const cid of draftCaseIds.value || []) {
        links.push({ link_type: 'functional_case', functional_case_id: cid })
      }
      const res = await testDefectApi.create({
        project_id: props.projectId,
        ...payloadFromForm(),
        status: 'open',
        links: links.length ? links : undefined
      })
      const data = res.data?.data || {}
      ElMessage.success(`已创建 ${data.defect_key || '缺陷'}`)
      isCreate.value = false
      applyDetail(data)
      emit('saved', data)
    } else {
      const res = await testDefectApi.update(defectId.value, props.projectId, payloadFromForm())
      applyDetail(res.data?.data || {})
      ElMessage.success('已保存')
      emit('saved', detail.value)
    }
  } finally {
    saving.value = false
  }
}

const removeDefect = async () => {
  try {
    await ElMessageBox.confirm('确认删除该缺陷？', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  removing.value = true
  try {
    await testDefectApi.remove(defectId.value, props.projectId)
    ElMessage.success('已删除')
    visible.value = false
    emit('deleted', defectId.value)
  } finally {
    removing.value = false
  }
}

const submitComment = async () => {
  if (!commentText.value.trim()) {
    ElMessage.warning('请输入评论内容')
    return
  }
  commenting.value = true
  try {
    await testDefectApi.addComment(defectId.value, props.projectId, commentText.value.trim())
    commentText.value = ''
    await loadDetail(defectId.value)
  } finally {
    commenting.value = false
  }
}

const removeComment = async (c) => {
  try {
    await ElMessageBox.confirm('删除该评论？', '确认', { type: 'warning' })
  } catch {
    return
  }
  await testDefectApi.removeComment(defectId.value, c.id, props.projectId)
  await loadDetail(defectId.value)
}

const openAddLink = () => {
  linkForm.link_type = 'requirement'
  linkForm.run_item_id = null
  linkForm.functional_case_id = null
  linkForm.requirement_id = null
  linkForm.asset_type = 'ui_case'
  linkForm.asset_id = null
  linkForm.external_url = ''
  linkForm.note = ''
  linkDialogVisible.value = true
  searchRequirements('')
}

const submitLink = async () => {
  const payload = { link_type: linkForm.link_type, note: linkForm.note || null }
  if (linkForm.link_type === 'run_item') payload.run_item_id = linkForm.run_item_id
  if (linkForm.link_type === 'functional_case') payload.functional_case_id = linkForm.functional_case_id
  if (linkForm.link_type === 'requirement') payload.requirement_id = linkForm.requirement_id
  if (linkForm.link_type === 'asset') {
    payload.asset_type = linkForm.asset_type
    payload.asset_id = linkForm.asset_id
  }
  if (linkForm.link_type === 'external') payload.external_url = linkForm.external_url
  linking.value = true
  try {
    await testDefectApi.addLink(defectId.value, props.projectId, payload)
    linkDialogVisible.value = false
    ElMessage.success('已添加关联')
    await loadDetail(defectId.value)
  } finally {
    linking.value = false
  }
}

const removeLink = async (row) => {
  try {
    await ElMessageBox.confirm('移除该关联？', '确认', { type: 'warning' })
  } catch {
    return
  }
  await testDefectApi.removeLink(defectId.value, row.id, props.projectId)
  await loadDetail(defectId.value)
}

const goRun = (runId) => {
  router.push({ path: `/test-plan-runs/${runId}` })
}

const goCase = (caseId) => {
  router.push({ path: '/ai-functional-cases', query: { case_id: String(caseId) } })
}

const goRequirement = (reqId) => {
  router.push({ path: '/ai-requirements', query: { requirement_id: String(reqId) } })
}

const openReqPreview = (reqId) => {
  const id = Number(reqId)
  if (!id) return
  previewReqId.value = id
  reqPreviewVisible.value = true
}

defineExpose({ open, openCreate, reload: () => defectId.value && loadDetail(defectId.value) })
</script>

<style scoped>
.drawer-head .title-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.drawer-head .key {
  font-size: 16px;
  font-weight: 600;
}
.drawer-head .sub {
  margin-top: 4px;
  color: #606266;
  font-size: 13px;
}
.drawer-body {
  min-height: 320px;
}
.defect-form {
  padding-right: 4px;
}
.defect-form :deep(.el-form-item) {
  margin-bottom: 16px;
}
.defect-form :deep(.el-form-item__label) {
  padding-bottom: 4px;
  color: #475467;
  font-weight: 500;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}
.field-hint {
  margin-top: 4px;
  font-size: 12px;
  color: #98a2b3;
  line-height: 1.4;
}
.link-form :deep(.el-form-item) {
  margin-bottom: 16px;
}
.link-form :deep(.el-form-item__label) {
  padding-bottom: 4px;
  color: #475467;
  font-weight: 500;
}
.meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #909399;
  font-size: 12px;
}
.pane-toolbar {
  margin-bottom: 8px;
}
.handle-form {
  margin-bottom: 12px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
}
.comment-btn {
  margin-top: 8px;
}
.comments {
  margin-bottom: 16px;
}
.comment-item {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 8px;
  background: #fafafa;
}
.c-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.c-body {
  white-space: pre-wrap;
  font-size: 13px;
  color: #303133;
}
.timeline {
  padding-left: 4px;
}
.footer {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.drawer-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  flex-wrap: wrap;
}
.footer-spacer { flex: 1; }
.process-arrow { margin: 0 8px; color: #909399; }
.defect-process-dialog .process-form :deep(.el-form-item) { margin-bottom: 16px; }
@media (max-width: 640px) {
  .form-grid { grid-template-columns: 1fr; }
}
</style>
