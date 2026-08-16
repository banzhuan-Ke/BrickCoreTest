<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">🚀 性能测试场景</div>
    </template>
    <template #main>
      <el-collapse v-model="sceneGuideExpanded" class="scene-guide-collapse">
        <el-collapse-item title="常见性能测试场景：目的与平台怎么配" name="guide">
          <div class="scene-guide-intro">
            先想清楚要回答什么问题，再选模式。用例须先在「接口自动化」里准备好；施压由在线执行机完成，请勿对生产误压。
          </div>
          <el-table :data="sceneGuideRows" size="small" border class="scene-guide-table">
            <el-table-column prop="name" label="常见场景" width="120" />
            <el-table-column prop="purpose" label="目的" min-width="200" />
            <el-table-column prop="howto" label="平台大概怎么配" min-width="320" />
          </el-table>
          <div class="scene-guide-extra">
            <div><span class="label">通用项：</span>加压(Ramp-up)、热身(Warmup)、错误率熔断、请求间隔(固定/随机)、多用例权重或固定比例，均可在场景编辑里配置。</div>
            <div><span class="label">快捷创建：</span>可用「AI 创建」一句话生成草稿（只引用项目内已有用例/套件），确认后再落库细调。</div>
          </div>
        </el-collapse-item>
      </el-collapse>

      <CatalogListLayout
        :project-id="proStore.projectInfo.id"
        v-model="filterCatalogId"
        all-node-label="全部场景"
        @change="() => { page = 1; fetchData() }"
      >
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索场景名称"
          clearable
          style="width: 240px"
          @keyup.enter="fetchData"
        />
        <el-button type="primary" @click="fetchData" :icon="Search">搜索</el-button>
        <el-button
          v-permission="'perf_scene:edit'"
          type="success"
          @click="handleAdd"
          :icon="Plus"
        >新建场景</el-button>
        <el-button
          v-if="canAiCreateScene"
          type="warning"
          plain
          @click="openAiCreate"
        >AI 创建</el-button>
      </div>

      <!-- 表格 -->
      <div style="overflow-x: auto; width: 100%;">
        <el-table :data="tableData" v-loading="loading" stripe style="min-width: 1200px;">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="场景名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="description" label="描述" min-width="120" show-overflow-tooltip />
        <el-table-column label="模式" width="90" align="center">
          <template #default="{ row }">
            <div class="mode-cell">
              <el-tag size="small" :type="getModeType(row.config?.mode)">
                {{ getModeLabel(row.config?.mode) }}
              </el-tag>
              <el-tag size="small" :type="row.config?.distribution_mode === 'fixed_ratio' ? 'success' : 'info'" style="margin-top: 2px;">
                {{ row.config?.distribution_mode === 'fixed_ratio' ? '固定' : '随机' }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="case_count" label="用例数" width="80" align="center" />
        <el-table-column label="并发数" width="80" align="center">
          <template #default="{ row }">
            {{ row.config?.concurrent_users || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="Ramp-up" width="90" align="center">
          <template #default="{ row }">
            {{ row.config?.ramp_up_seconds !== undefined ? row.config.ramp_up_seconds + 's' : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="持续时间" width="90" align="center">
          <template #default="{ row }">
            <span v-if="row.config?.mode === 'fixed'">
              {{ row.config?.duration_seconds ? row.config.duration_seconds + 's' : '-' }}
            </span>
            <span v-else-if="row.config?.mode === 'loop'">
              {{ row.config?.loop_count ? row.config.loop_count + '次' : '-' }}
            </span>
            <span v-else-if="row.config?.mode === 'stepping'">
              {{ row.config?.steps ? row.config.steps.length + '阶段' : '-' }}
            </span>
            <span v-else-if="row.config?.mode === 'stream_burst' || row.config?.mode === 'sse_burst'">
              {{ row.config?.concurrent_users ? row.config.concurrent_users + '并发×1次' : '-' }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="create_by" label="创建人" width="100" />
        <el-table-column prop="create_time" label="创建时间" width="160" />
        <el-table-column label="操作" width="340" fixed="right">
          <template #default="{ row }">
            <div class="op-btns">
              <el-button
                v-permission="'perf_scene:execute'"
                type="primary"
                size="small"
                :icon="VideoPlay"
                @click="handleRun(row)"
              >执行</el-button>
              <el-button
                v-permission="'perf_scene:edit'"
                type="info"
                size="small"
                :icon="CopyDocument"
                @click="handleClone(row)"
              >复制</el-button>
              <el-button
                v-permission="'perf_scene:edit'"
                type="warning"
                size="small"
                :icon="Edit"
                @click="handleEdit(row)"
              >编辑</el-button>
              <el-button
                v-permission="'perf_scene:edit'"
                type="danger"
                size="small"
                :icon="Delete"
                @click="handleDelete(row)"
              >删除</el-button>
            </div>
          </template>
        </el-table-column>
        </el-table>
      </div>

      <!-- 分页 -->
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="fetchData"
          @current-change="fetchData"
        />
      </div>
      </CatalogListLayout>

      <!-- 执行对话框 -->
      <el-dialog v-model="runDialogVisible" title="启动性能测试" width="760px">
        <el-form :model="runForm" label-width="90px">
          <el-form-item label="场景">
            <el-input v-model="runForm.sceneName" disabled />
          </el-form-item>
          <el-form-item label="环境" required>
            <el-select v-model="runForm.envId" placeholder="选择执行环境" style="width: 100%">
              <el-option
                v-for="env in envList"
                :key="env.id"
                :label="env.name"
                :value="env.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="配置">
            <div class="config-preview">
              <div class="config-row">
                <span>并发用户: {{ runForm.config?.concurrent_users }}</span>
                <el-tooltip placement="top" content="同时发起请求的虚拟用户数">
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="config-row">
                <span>Ramp-up: {{ runForm.config?.ramp_up_seconds }}s</span>
                <el-tooltip placement="top" content="从0用户到目标并发数的渐进加压时间，0表示立即加压">
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="config-row">
                <span v-if="runForm.config?.mode === 'fixed'">持续时间: {{ runForm.config?.duration_seconds }}s</span>
                <span v-else-if="runForm.config?.mode === 'loop'">循环次数: {{ runForm.config?.loop_count }}次</span>
                <span v-else-if="runForm.config?.mode === 'stepping'">梯度阶段: {{ runForm.config?.steps?.length || 0 }}个</span>
                <span v-else-if="runForm.config?.mode === 'stream_burst' || runForm.config?.mode === 'sse_burst'">并发单次: {{ runForm.config?.concurrent_users }}用户×1次</span>
                <span v-else-if="runForm.config?.mode === 'journey_fixed'">链路持续: {{ runForm.config?.duration_seconds }}s</span>
                <span v-else-if="runForm.config?.mode === 'journey_loop'">链路次数: {{ runForm.config?.loop_count }}次/用户</span>
                <el-tooltip placement="top" :content="getDurationTip(runForm.config)">
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="接口明细">
            <el-radio-group v-model="runForm.requestDetailLevel" class="detail-level-group">
              <el-radio value="brief">简略（失败含完整请求详情）</el-radio>
              <el-radio value="full">详细（含成功请求完整头/体）</el-radio>
            </el-radio-group>
            <div class="detail-level-hint">
              <strong>不影响 QPS、平均/P95 响应时间、错误率等汇总数据</strong>——请求发出与 RT 计时逻辑与简略模式完全相同，仅在请求结束后额外记录接口信息供报告排查。
              失败请求两种模式均保留最多 50 条<strong>完整</strong>请求头/体/响应（单字段上限 32KB）；详细模式另采集最多 500 条成功请求完整明细，报告体积更大。高并发时可能略增内存与收尾耗时，不改变已测得的性能指标。
            </div>
          </el-form-item>
          <el-form-item label="AI 分析">
            <el-checkbox
              v-model="runForm.aiAnalyze"
              :disabled="!perfAiEnabled || !perfAiAllowOverride"
            >
              执行完成后自动 AI 分析
            </el-checkbox>
            <div class="detail-level-hint">
              <template v-if="!perfAiEnabled">
                项目未开启压测 AI 分析，请到「项目设置 → 压测 AI」开启。
              </template>
              <template v-else-if="!perfAiAllowOverride">
                已按项目默认：{{ runForm.aiAnalyze ? '开启' : '关闭' }}（不允许本次覆盖）。
              </template>
              <template v-else>
                分析在后台进行，报告可随时打开；AI 区显示「分析中」，完成后手动刷新即可。
              </template>
            </div>
          </el-form-item>
          <el-form-item label="验收目标">
            <div style="width:100%">
              <div class="detail-level-hint" style="margin-bottom:8px">
                <div v-for="(line, idx) in runPerfTargetSummary" :key="idx">{{ line }}</div>
              </div>
              <el-checkbox v-model="runOverridePerfTargets">本次覆盖性能目标</el-checkbox>
              <template v-if="runOverridePerfTargets">
                <div style="margin-top:10px">
                  <el-switch v-model="runPerfTargets.enabled" active-text="启用目标" inactive-text="关闭" />
                  <div style="display:flex;flex-wrap:wrap;gap:12px;margin:10px 0" v-if="runPerfTargets.enabled">
                    <div>
                      <span style="font-size:12px;margin-right:6px">最小样本</span>
                      <el-input-number v-model="runPerfTargets.min_total_requests" :min="0" size="small" />
                    </div>
                    <div>
                      <span style="font-size:12px;margin-right:6px">最小时长(s)</span>
                      <el-input-number v-model="runPerfTargets.min_duration_seconds" :min="0" size="small" />
                    </div>
                  </div>
                  <el-table
                    v-if="runPerfTargets.enabled"
                    :data="runPerfTargetRows"
                    size="small"
                    border
                    style="width:100%;margin-top:8px"
                  >
                    <el-table-column label="启用" width="60" align="center">
                      <template #default="{ row }"><el-checkbox v-model="row.enabled" /></template>
                    </el-table-column>
                    <el-table-column prop="label" label="指标" min-width="110" />
                    <el-table-column prop="op" label="条件" width="60" align="center" />
                    <el-table-column label="目标值" width="120">
                      <template #default="{ row }">
                        <el-input-number v-model="row.value" :controls="false" :precision="2" :min="0" size="small" style="width:100px" />
                      </template>
                    </el-table-column>
                    <el-table-column label="不满足" width="110">
                      <template #default="{ row }">
                        <el-select v-model="row.severity" size="small" style="width:90px">
                          <el-option label="失败" value="fail" />
                          <el-option label="警告" value="warn" />
                        </el-select>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </template>
            </div>
          </el-form-item>
          <el-form-item label="执行器">
            <div style="width: 100%;">
              <el-alert
                type="info"
                :closable="false"
                show-icon
                style="margin-bottom: 10px;"
              >
                <template #title>如何理解下面三列</template>
                <template #default>
                  <div style="font-size: 12px; line-height: 1.7;">
                    压测由在线执行机施压（平台不本机直跑）。
                    <strong>本机上限</strong>：这台机器最多能扛多少并发；
                    <strong>分压比例</strong>：多机时按比例拆分场景并发（只比大小，不是人数）；
                    <strong>本机分到</strong>：最终落在这台机器上的虚拟用户数（VU）。
                    仅勾选一台时，分压比例无效，场景并发会全部落在该机。
                  </div>
                </template>
              </el-alert>
              <el-alert
                v-if="workerList.length === 0"
                type="warning"
                :closable="false"
                show-icon
              >
                <template #title>暂无在线执行机，无法启动</template>
                <template #default>
                  <div style="font-size: 12px; line-height: 1.6;">
                    任选其一：安装并上线 <strong>BrickCoreRunner</strong>（压测角色），或精简包 <strong>BrickCorePerf</strong>。
                    压测施压由执行机提供，平台不会本机直跑。项目 ID 须与当前项目（{{ proStore.projectInfo?.id }}）一致。
                  </div>
                </template>
              </el-alert>
              <el-alert
                v-else-if="selectedWorkerCapacity < runNeededConcurrent"
                type="warning"
                :closable="false"
                show-icon
                :title="`容量不足：场景需要 ${runNeededConcurrent} 并发，已勾选机器合计上限仅 ${selectedWorkerCapacity}`"
              />
              <el-alert
                v-else
                type="success"
                :closable="false"
                show-icon
              >
                <template #title>
                  <span>
                    {{ workerDispatchSummary }}
                    <el-tooltip placement="top" :content="workerDispatchTip">
                      <el-icon class="tip-icon" style="margin-left: 4px; vertical-align: middle"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>
              </el-alert>
              <el-alert
                v-if="workerVersionMismatch"
                type="warning"
                :closable="false"
                show-icon
                style="margin-top: 8px;"
                title="部分执行机引擎版本与平台期望不一致，建议升级 BrickCoreRunner / BrickCorePerf 后重新上线"
              />
              <el-table
                v-if="workerList.length > 0"
                :data="workerList"
                size="small"
                border
                style="margin-top: 8px; width: 100%;"
                table-layout="fixed"
              >
                <el-table-column label="选用" width="56" align="center">
                  <template #default="{ row }">
                    <el-checkbox v-model="row.selected" />
                  </template>
                </el-table-column>
                <el-table-column label="执行器" min-width="180">
                  <template #default="{ row }">
                    <div>{{ row.name }} ({{ row.host }})</div>
                    <div style="font-size: 12px; color: #909399;">
                      {{ agentKindShort(row.agent_kind) }} · 引擎 {{ row.engine_version || '-' }}
                    </div>
                  </template>
                </el-table-column>
                <el-table-column width="88" align="center">
                  <template #header>
                    <span>
                      本机上限
                      <el-tooltip placement="top" content="执行机申报的最大并发能力（max_concurrent），不是本次会启动的人数。">
                        <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </span>
                  </template>
                  <template #default="{ row }">{{ row.max_concurrent }}</template>
                </el-table-column>
                <el-table-column width="118" align="center">
                  <template #header>
                    <span>
                      分压比例
                      <el-tooltip placement="top" content="多机时按比例拆分场景并发，例如 2:1 约分到 2/3 与 1/3。单机时无需调整。">
                        <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </span>
                  </template>
                  <template #default="{ row }">
                    <el-input-number
                      v-model="row.weight"
                      :min="1"
                      :max="100000"
                      size="small"
                      :disabled="!row.selected || selectedWorkerRows.length <= 1"
                      controls-position="right"
                      style="width: 96px;"
                    />
                  </template>
                </el-table-column>
                <el-table-column width="110" align="center">
                  <template #header>
                    <span>
                      本机分到
                      <el-tooltip placement="top" content="本次场景并发按分压比例落到本机的虚拟用户数（VU）。">
                        <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </span>
                  </template>
                  <template #default="{ row }">
                    <span :style="{ color: row.selected ? undefined : '#c0c4cc' }">
                      {{ row.selected ? (workerPreviewMap[row.id] ?? 0) : '-' }}
                    </span>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="runDialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            @click="confirmRun"
            :loading="runLoading"
            :disabled="!canConfirmRun"
          >
            确认执行
          </el-button>
        </template>
      </el-dialog>

      <!-- AI 一句话创建场景 -->
      <el-dialog
        v-model="aiDialogVisible"
        title="AI 一句话创建压测场景"
        width="760px"
        destroy-on-close
        class="ai-scene-dialog"
        @closed="resetAiDialog"
      >
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 12px;"
          title="仅引用项目内已有用例/套件，不会新建接口。生成后请确认再落库；请勿对生产环境误压。"
        />
        <el-form label-width="96px">
          <el-form-item label="描述" required>
            <div class="ai-prompt-wrap">
              <el-input
                v-model="aiForm.prompt"
                type="textarea"
                :rows="3"
                maxlength="2000"
                show-word-limit
                placeholder="点击下方示例可填入，再按需微调"
              />
              <div class="ai-example-block">
                <div class="ai-example-title">示例（点击填入，可再微调）</div>
                <div class="ai-example-list">
                  <button
                    v-for="ex in aiPromptExamples"
                    :key="ex.id"
                    type="button"
                    class="ai-example-btn"
                    @click="applyAiExample(ex)"
                  >
                    <span class="ai-example-label">{{ ex.label }}</span>
                    <span class="ai-example-text">{{ ex.prompt }}</span>
                  </button>
                </div>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="接口用例">
            <el-select
              v-model="aiForm.case_ids"
              multiple
              filterable
              clearable
              collapse-tags
              collapse-tags-tooltip
              class="ai-case-select"
              placeholder="可选，测单接口时直接选用例（优先于套件）"
              style="width: 100%"
              @change="onAiCaseIdsChange"
            >
              <el-option
                v-for="c in caseOptions"
                :key="c.id"
                :label="formatAiCaseLabel(c)"
                :value="c.id"
              >
                <div class="ai-case-option">
                  <span class="ai-case-option-name">{{ formatAiCaseShort(c) }}</span>
                  <span class="ai-case-option-api">{{ formatAiCaseApi(c) }}</span>
                </div>
              </el-option>
            </el-select>
            <div class="ai-case-hint">测单接口建议只选 1 个；多选则按加权混合施压（非链路）。已选用例时不再按标签过滤。</div>
          </el-form-item>
          <el-form-item label="套件">
            <el-select
              v-model="aiForm.suite_id"
              clearable
              filterable
              :disabled="(aiForm.case_ids || []).length > 0"
              placeholder="可选，优先按套件生成链路"
              style="width: 100%"
            >
              <el-option
                v-for="s in suiteOptions"
                :key="s.id"
                :label="s.name"
                :value="s.id"
              />
            </el-select>
            <div v-if="(aiForm.case_ids || []).length" class="ai-case-hint">已选用例时套件禁用，清空用例后可选套件。</div>
          </el-form-item>
          <el-form-item label="标签">
            <el-select
              v-model="aiForm.tags"
              multiple
              filterable
              allow-create
              default-first-option
              clearable
              :disabled="(aiForm.case_ids || []).length > 0"
              placeholder="可选，缩小候选用例（未点选用例时生效）"
              style="width: 100%"
            >
              <el-option
                v-for="t in aiTagOptions"
                :key="t.value"
                :label="t.label"
                :value="t.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="模型">
            <el-select
              v-model="aiForm.ai_config_id"
              clearable
              filterable
              placeholder="默认按场景绑定"
              style="width: 100%"
            >
              <el-option
                v-for="c in aiConfigOptions"
                :key="c.id"
                :label="formatAiConfigLabel(c)"
                :value="c.id"
              />
            </el-select>
          </el-form-item>
        </el-form>

        <div v-if="aiDraft" class="ai-draft">
          <el-divider content-position="left">预览草稿（可改）</el-divider>
          <el-alert
            v-if="aiDraft.warnings?.length"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 10px;"
            :title="aiDraft.warnings.join('；')"
          />
          <el-alert
            v-if="aiDraft.unmatched?.length"
            type="error"
            :closable="false"
            show-icon
            style="margin-bottom: 10px;"
            :title="`未匹配：${aiDraft.unmatched.join('、')}`"
          />
          <el-form label-width="96px" size="default">
            <el-form-item label="名称">
              <el-input v-model="aiDraft.name" maxlength="100" />
            </el-form-item>
            <el-form-item label="模式">
              <el-tag size="small" :type="getModeType(aiDraft.config?.mode)">
                {{ getModeLabel(aiDraft.config?.mode) }}
              </el-tag>
            </el-form-item>
            <el-form-item v-if="aiDraft.config?.mode !== 'stepping'" label="并发">
              <el-input-number v-model="aiDraft.config.concurrent_users" :min="1" :max="1000" />
            </el-form-item>
            <el-form-item
              v-if="['fixed', 'journey_fixed'].includes(aiDraft.config?.mode)"
              label="时长(秒)"
            >
              <el-input-number v-model="aiDraft.config.duration_seconds" :min="1" :max="86400" />
            </el-form-item>
            <el-form-item
              v-if="['loop', 'journey_loop'].includes(aiDraft.config?.mode)"
              label="循环次数"
            >
              <el-input-number v-model="aiDraft.config.loop_count" :min="1" :max="100000" />
            </el-form-item>
            <el-form-item
              v-if="aiDraft.config?.mode !== 'stream_burst'"
              label="加压(秒)"
            >
              <el-input-number v-model="aiDraft.config.ramp_up_seconds" :min="0" :max="600" />
            </el-form-item>
            <el-form-item label="错误率熔断(%)">
              <el-input-number
                v-model="aiDraft.config.error_rate_threshold"
                :min="0"
                :max="100"
                :step="1"
              />
              <span class="ai-case-hint" style="margin-left: 8px;">0 表示不启用</span>
            </el-form-item>
            <el-form-item v-if="aiDelaySummary" label="间隔">
              <span class="ai-delay-summary">{{ aiDelaySummary }}</span>
            </el-form-item>
            <el-form-item v-if="aiDraft.config?.stream_profile" label="流式">
              <el-tag size="small" type="success">
                {{ aiDraft.config.stream_profile.parser_id || 'SSE' }}
              </el-tag>
            </el-form-item>
            <el-form-item v-if="aiDraft.config?.mode === 'stepping'" label="梯度阶段">
              <div class="ai-steps-preview">
                <div
                  v-for="(st, idx) in (aiDraft.config.steps || [])"
                  :key="idx"
                  class="ai-step-row"
                >
                  <span class="ai-step-idx">第{{ idx + 1 }}阶</span>
                  <el-input-number v-model="st.users" :min="1" :max="200" size="small" />
                  <span>并发 ·</span>
                  <el-input-number v-model="st.duration" :min="1" :max="3600" size="small" />
                  <span>秒</span>
                </div>
                <div v-if="!(aiDraft.config.steps || []).length" class="ai-case-hint">暂无阶段，请重新生成</div>
              </div>
            </el-form-item>
            <el-form-item label="匹配用例">
              <el-table
                ref="aiCaseTableRef"
                :data="aiDraft.matched_cases || []"
                size="small"
                max-height="220"
                stripe
                row-key="id"
                @selection-change="onAiCaseSelectionChange"
              >
                <el-table-column type="selection" width="44" align="center" />
                <el-table-column prop="id" label="ID" width="70" />
                <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
                <el-table-column label="接口" min-width="160" show-overflow-tooltip>
                  <template #default="{ row }">
                    {{ [row.method, row.path].filter(Boolean).join(' ') || '-' }}
                  </template>
                </el-table-column>
              </el-table>
              <div class="ai-case-hint">可取消勾选不需要的用例；至少保留一个才能创建。</div>
            </el-form-item>
          </el-form>
        </div>

        <template #footer>
          <el-button @click="aiDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="aiGenerating" @click="handleAiGenerate">
            {{ aiDraft ? '重新生成' : '生成草稿' }}
          </el-button>
          <el-button
            type="success"
            :disabled="!aiDraft?.importable || !aiSelectedCaseIds.length"
            :loading="aiImporting"
            @click="handleAiImport"
          >确认创建</el-button>
        </template>
      </el-dialog>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Plus, Edit, Delete, VideoPlay, QuestionFilled, CopyDocument } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import CatalogListLayout from '@/components/CatalogListLayout.vue'
import { perfSceneApi, perfExecApi, perfWorkerApi, httpSuiteApi, httpCaseApi } from '@/api'
import { parseWorkerList, filterOnlineWorkers, agentKindShort, distributeByWeights, neededConcurrentFromConfig } from './perfWorkerUtils'
import { envApi } from '@/api'
import { aiConfigApi, aiGenerateApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import {
  defaultPerfTargets,
  normalizePerfTargetsLocal,
  perfTargetsSummaryLines,
} from '@/views/Perf/perfTargets'

const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()

const canAiCreateScene = computed(
  () => uStore.hasPermission('perf_scene:edit') && uStore.hasPermission('ai_test:execute')
)

const formatApiDetail = (err, fallback = '操作失败') => {
  const detail = err?.response?.data?.detail ?? err?.data?.detail
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (typeof detail?.message === 'string') return detail.message
  try {
    return JSON.stringify(detail)
  } catch {
    return fallback
  }
}
const loading = ref(false)
const tableData = ref([])
const page = ref(1)
const size = ref(20)
const total = ref(0)
const searchKeyword = ref('')
const filterCatalogId = ref(null)

const runDialogVisible = ref(false)
const runLoading = ref(false)
const runForm = ref({
  sceneId: null,
  sceneName: '',
  envId: null,
  config: {},
  useWorkers: false,
  requestDetailLevel: 'brief',
  aiAnalyze: false
})
const runOverridePerfTargets = ref(false)
const runPerfTargets = ref(defaultPerfTargets())
const runPerfTargetSummary = computed(() =>
  perfTargetsSummaryLines(runForm.value?.config?.perf_targets)
)
const runPerfTargetRows = computed(() =>
  (runPerfTargets.value.items || []).filter((it) => it.scope === 'global')
)
const perfAiEnabled = ref(false)
const perfAiAllowOverride = ref(true)
const workerList = ref([])
const workerVersionMismatch = computed(() => workerList.value.some(w => w.version_ok === false))
const selectedWorkerRows = computed(() => (workerList.value || []).filter((w) => w.selected))
const selectedWorkerCapacity = computed(() =>
  selectedWorkerRows.value.reduce((sum, w) => sum + (Number(w.max_concurrent) || 0), 0)
)
const runNeededConcurrent = computed(() => neededConcurrentFromConfig(runForm.value?.config))
const workerPreviewAssignments = computed(() => {
  const rows = selectedWorkerRows.value
  if (!rows.length) return []
  return distributeByWeights(
    runNeededConcurrent.value,
    rows.map((w) => Number(w.max_concurrent) || 0),
    rows.map((w) => Math.max(1, Number(w.weight) || 1))
  )
})
const workerPreviewMap = computed(() => {
  const map = {}
  selectedWorkerRows.value.forEach((w, i) => {
    map[w.id] = workerPreviewAssignments.value[i] ?? 0
  })
  return map
})
const previewAssignedTotal = computed(() =>
  workerPreviewAssignments.value.reduce((a, b) => a + b, 0)
)
const workerDispatchSummary = computed(() => {
  const need = runNeededConcurrent.value
  const n = selectedWorkerRows.value.length
  const total = workerList.value.length
  const cap = selectedWorkerCapacity.value
  if (n <= 1) {
    const name = selectedWorkerRows.value[0]?.name || '该执行机'
    return `场景需要 ${need} 并发 · 已选 ${n}/${total} 台（上限合计 ${cap}）· 将全部落在 ${name}（${previewAssignedTotal.value} VU）`
  }
  return `场景需要 ${need} 并发 · 已选 ${n}/${total} 台（上限合计 ${cap}）· 按分压比例拆到各机，合计 ${previewAssignedTotal.value} VU`
})
const workerDispatchTip = computed(() => {
  if (selectedWorkerRows.value.length <= 1) {
    return '只选一台时不看分压比例：场景并发会全部落到该机，且不得超过本机上限。'
  }
  return '多机时按「分压比例」拆分场景并发；本机分到的人数不会超过该机上限。VU = 虚拟用户（并发施压人数）。'
})
const canConfirmRun = computed(() => {
  if (!workerList.value.length || !selectedWorkerRows.value.length) return false
  return selectedWorkerCapacity.value >= runNeededConcurrent.value
})
const envList = ref([])

const sceneGuideExpanded = ref([])
/** 列表页场景选型说明（与编辑页模式说明互补，偏「测什么 / 怎么配」） */
const sceneGuideRows = [
  {
    name: '冒烟试跑',
    purpose: '确认接口通、脚本与环境无误，再做正式加压。',
    howto: '模式选「固定」；小并发（如 5）+ 短时长（如 30 秒）；可先不开熔断。',
  },
  {
    name: '负载 / 长稳',
    purpose: '在目标并发下观察延迟、错误率与稳定性（可到数十分钟～数小时）。',
    howto: '「固定」+ 目标并发 + 持续时长；建议设 Ramp-up；长稳可开错误率熔断。',
  },
  {
    name: '容量 / 探极限',
    purpose: '找性能拐点与大致最大可支撑并发。',
    howto: '「梯度」分阶段递增并发（如围绕已知 40：20→30→40→50→60）；看错误率与 P95 突变点。',
  },
  {
    name: '峰值 / 尖峰',
    purpose: '验证高峰负载能否扛住、会不会雪崩。',
    howto: '「固定」高并发短时长，或梯度快速摸高；错误率阈值建议 50% 左右自动停。',
  },
  {
    name: '瞬时 / 吞吐',
    purpose: '总量可控的一批请求，适合回归与版本对比。',
    howto: '「循环」：并发 × 每人循环次数；打完即停。',
  },
  {
    name: '业务链路',
    purpose: '按真实用户路径（登录→业务）评估端到端容量。',
    howto: '「链路固定/循环」；从套件导入步骤，配置步骤间隔与变量传递。',
  },
  {
    name: '混合流量',
    purpose: '多接口接近真实配比的综合压力。',
    howto: '非链路模式下添加多个用例，设「随机权重」或「固定比例」。',
  },
  {
    name: '流式 / SSE',
    purpose: '评估问答流式首字、阶段耗时等（非纯 HTTP QPS）。',
    howto: '「流式阶段」每人 1 次；或固定/梯度下打开「流式问答」开关。',
  },
]
const aiDialogVisible = ref(false)
const aiGenerating = ref(false)
const aiImporting = ref(false)
const aiForm = ref({
  prompt: '',
  suite_id: null,
  case_ids: [],
  tags: [],
  ai_config_id: null
})
const aiDraft = ref(null)
const aiRecordId = ref(null)
const aiSelectedCaseIds = ref([])
const aiCaseTableRef = ref(null)
const suiteOptions = ref([])
const caseOptions = ref([])
const aiConfigOptions = ref([])

/** 标签：展示中文，value 仍为用例库英文 tag，与后端匹配一致 */
const aiTagOptions = [
  { label: '压测常用', value: 'perf' },
  { label: '业务链路', value: 'journey' },
  { label: '登录相关', value: 'login' },
]

/**
 * 可直接生成场景的示例（对齐后端 resolve：梯度/固定/循环/链路/流式/间隔/熔断）
 * tags 为建议约束，点击时写入表单，用户可再改。
 */
const aiPromptExamples = [
  {
    id: 'stepping-capacity',
    label: '梯度·探最大并发',
    prompt: '我想测该接口最大并发是多少，我之前测大概是 40 并发，请按 40 附近生成梯度压测',
    tags: ['perf'],
  },
  {
    id: 'fixed-long',
    label: '常规·长稳压',
    prompt: '对该接口做压力测试，大概 30 并发，持续 1 小时，加压 30 秒',
    tags: ['perf'],
  },
  {
    id: 'journey-fixed',
    label: '链路·固定时长',
    prompt: '用登录业务链路 50 并发压 3 分钟，步骤间带 1～3 秒随机间隔',
    tags: ['journey', 'login'],
  },
  {
    id: 'loop-burst',
    label: '瞬时·循环',
    prompt: '瞬时压测：每人循环 1 次，并发 20，打完即停',
    tags: ['perf'],
  },
  {
    id: 'stream-burst',
    label: '流式·阶段',
    prompt: 'SSE 流式阶段压测：20 并发，每人发一次流式问答请求',
    tags: ['perf'],
  },
  {
    id: 'peak',
    label: '峰值加压',
    prompt: '峰值压测：50 并发持续 3 分钟，加压 20 秒，错误率超过 50% 自动停止',
    tags: ['perf'],
  },
  {
    id: 'smoke',
    label: '冒烟试跑',
    prompt: '冒烟试跑：5 并发持续 30 秒，验证接口能通即可',
    tags: ['perf'],
  },
  {
    id: 'journey-loop',
    label: '链路·循环',
    prompt: '业务链路压测：每人跑 10 轮，并发 20',
    tags: ['journey'],
  },
]

const formatAiConfigLabel = (c) => {
  if (!c) return ''
  const name = (c.name || '').trim()
  const model = (c.model || c.model_name || '').trim()
  const provider = (c.provider || '').trim()
  if (name && model && name !== model) return `${name}（${model}）`
  if (name) return name
  if (model) return provider ? `${provider} / ${model}` : model
  return `配置#${c.id}`
}

const formatAiCaseApi = (c) => {
  if (!c) return ''
  const method = (c.api_method || c.method || c.api?.method || '').trim()
  const path = (c.api_path || c.path || c.api?.path || '').trim()
  return [method, path].filter(Boolean).join(' ')
}

const formatAiCaseShort = (c) => {
  if (!c) return ''
  const name = (c.name || `用例#${c.id}`).trim()
  return `#${c.id} ${name}`
}

const formatAiCaseLabel = (c) => {
  if (!c) return ''
  // 选中 tag 用短名，避免撑破选择框；下拉项另有完整展示
  return formatAiCaseShort(c)
}

const onAiCaseIdsChange = (ids) => {
  if (Array.isArray(ids) && ids.length) {
    aiForm.value.suite_id = null
    aiForm.value.tags = []
  }
}

const applyAiExample = (ex) => {
  if (!ex) return
  aiForm.value.prompt = ex.prompt
  if (!(aiForm.value.case_ids || []).length && Array.isArray(ex.tags) && ex.tags.length) {
    aiForm.value.tags = [...ex.tags]
  }
  ElMessage.success(`已填入「${ex.label}」，可微调后再生成`)
}
const syncAiDraftSelection = () => {
  if (!aiDraft.value) return
  const selected = new Set(aiSelectedCaseIds.value.map((id) => Number(id)))
  const matched = aiDraft.value.matched_cases || []
  const config = { ...(aiDraft.value.config || {}) }
  // 优先沿用后端 journey / journey_source / scene_items 顺序，避免用 matched_cases 表序打乱套件链路
  let canonicalOrder = []
  const journeySteps = (config.journey?.phases || []).flatMap((p) => p.steps || [])
  if (journeySteps.length) {
    canonicalOrder = journeySteps.map((s) => Number(s.case_id)).filter((id) => !Number.isNaN(id))
  } else if (Array.isArray(config.journey_source?.case_ids) && config.journey_source.case_ids.length) {
    canonicalOrder = config.journey_source.case_ids.map((id) => Number(id)).filter((id) => !Number.isNaN(id))
  } else if ((aiDraft.value.scene_items || []).length) {
    canonicalOrder = (aiDraft.value.scene_items || [])
      .map((i) => Number(i.case_id))
      .filter((id) => !Number.isNaN(id))
  } else {
    canonicalOrder = matched.map((c) => Number(c.id)).filter((id) => !Number.isNaN(id))
  }
  const seenCanonical = new Set(canonicalOrder)
  for (const c of matched) {
    const id = Number(c.id)
    if (!Number.isNaN(id) && !seenCanonical.has(id)) {
      canonicalOrder.push(id)
      seenCanonical.add(id)
    }
  }
  const ordered = canonicalOrder.filter((id) => selected.has(id))
  const delaySrc = (aiDraft.value.scene_items || [])[0] || journeySteps[0] || {}
  const delay = {
    delay_mode: delaySrc.delay_mode || 'fixed',
    delay_ms: Number(delaySrc.delay_ms) || 0,
    delay_ms_min: Number(delaySrc.delay_ms_min) || 0,
    delay_ms_max: Number(delaySrc.delay_ms_max) || 0
  }
  const mode = config.mode || 'fixed'
  const useJourney = !['stepping', 'stream_burst', 'sse_burst'].includes(mode)
    && (['journey_fixed', 'journey_loop'].includes(mode) || !!config.journey)
  let scene_items = []
  if (useJourney && ordered.length) {
    const steps = ordered.map((cid, i) => ({
      case_id: cid,
      delay_ms: delay.delay_ms,
      delay_mode: delay.delay_mode,
      delay_ms_min: delay.delay_ms_min,
      delay_ms_max: delay.delay_ms_max,
      use_stream: false,
      order: i
    }))
    const phaseName = config.journey?.phases?.[0]?.name || '业务链路'
    config.journey = {
      stop_on_step_fail: true,
      delay_between_journeys_ms: Number(config.journey?.delay_between_journeys_ms) || 0,
      phases: [{
        name: phaseName,
        execution: 'serial',
        sync_before: false,
        max_parallel: 6,
        steps
      }]
    }
    if (config.journey_source) {
      config.journey_source = { ...config.journey_source, case_ids: ordered }
    }
    if (!['journey_fixed', 'journey_loop'].includes(config.mode)) {
      config.mode = 'journey_fixed'
    }
    const seen = new Set()
    scene_items = ordered.filter((id) => {
      if (seen.has(id)) return false
      seen.add(id)
      return true
    }).map((cid) => ({ case_id: cid, weight: 1, ...delay }))
  } else {
    delete config.journey
    if (['journey_fixed', 'journey_loop'].includes(config.mode)) {
      config.mode = config.mode === 'journey_loop' ? 'loop' : 'fixed'
    }
    scene_items = ordered.map((cid) => ({ case_id: cid, weight: 1, ...delay }))
  }
  aiDraft.value = {
    ...aiDraft.value,
    config,
    scene_items,
    importable: scene_items.length > 0
  }
}

const onAiCaseSelectionChange = (rows) => {
  aiSelectedCaseIds.value = (rows || []).map((r) => Number(r.id))
  syncAiDraftSelection()
}

const selectAllMatchedCases = async () => {
  await nextTick()
  const table = aiCaseTableRef.value
  const rows = aiDraft.value?.matched_cases || []
  if (!table || !rows.length) return
  rows.forEach((row) => table.toggleRowSelection(row, true))
  aiSelectedCaseIds.value = rows.map((r) => Number(r.id))
  syncAiDraftSelection()
}
const loadPerfAiSettings = async () => {
  const pid = proStore.projectInfo?.id
  if (!pid) return
  try {
    const fromStore = proStore.projectInfo?.global_vars?.ai_settings
    let data = fromStore
    if (!data) {
      const res = await aiConfigApi.getExecutionSettings(pid)
      data = res.data?.data || res.data || {}
    }
    perfAiEnabled.value = data.perf_ai_analysis_enabled === true
    perfAiAllowOverride.value = data.perf_ai_analysis_allow_run_override !== false
    return {
      enabled: perfAiEnabled.value,
      defaultOn: data.perf_ai_analysis_default_on_run === true,
      allowOverride: perfAiAllowOverride.value
    }
  } catch {
    perfAiEnabled.value = false
    return { enabled: false, defaultOn: false, allowOverride: true }
  }
}
const getModeType = (mode) => {
  const map = {
    fixed: 'primary',
    loop: 'success',
    stepping: 'warning',
    stream_burst: 'danger',
    sse_burst: 'danger',
    journey_fixed: 'primary',
    journey_loop: 'success',
  }
  return map[mode] || ''
}

const getModeLabel = (mode) => {
  const map = {
    fixed: '固定',
    loop: '循环',
    stepping: '梯度',
    stream_burst: '流式阶段',
    sse_burst: '流式阶段',
    journey_fixed: '链路·固定',
    journey_loop: '链路·循环',
  }
  return map[mode] || mode
}

const aiDelaySummary = computed(() => {
  const items = aiDraft.value?.scene_items || []
  const src = items[0] || {}
  const mode = src.delay_mode || 'fixed'
  if (mode === 'random') {
    const a = Number(src.delay_ms_min) || 0
    const b = Number(src.delay_ms_max) || 0
    if (!a && !b) return ''
    return `随机 ${(a / 1000).toFixed(a % 1000 ? 1 : 0)}～${(b / 1000).toFixed(b % 1000 ? 1 : 0)} 秒`
  }
  const ms = Number(src.delay_ms) || 0
  if (!ms) return ''
  return `固定 ${(ms / 1000).toFixed(ms % 1000 ? 1 : 0)} 秒`
})

const fetchData = async () => {
  if (!proStore.projectInfo?.id) return
  loading.value = true
  try {
    const catalogId = filterCatalogId.value && filterCatalogId.value !== 'all' ? filterCatalogId.value : undefined
    const res = await perfSceneApi.getList({
      project_id: proStore.projectInfo.id,
      keyword: searchKeyword.value || undefined,
      catalog_id: catalogId,
      page: page.value,
      size: size.value
    })
    const data = res.data || res
    tableData.value = data.data || []
    total.value = data.total || 0
  } catch (err) {
    console.error(err)
    ElMessage.error('获取场景列表失败')
  } finally {
    loading.value = false
  }
}

const handleAdd = () => {
  router.push('/perf-scene/add')
}

const resetAiDialog = () => {
  aiForm.value = { prompt: '', suite_id: null, case_ids: [], tags: [], ai_config_id: null }
  aiDraft.value = null
  aiRecordId.value = null
  aiSelectedCaseIds.value = []
  aiGenerating.value = false
  aiImporting.value = false
}

const openAiCreate = async () => {
  if (!proStore.projectInfo?.id) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!canAiCreateScene.value) {
    ElMessage.warning('需要同时具备「场景编辑」与「AI 执行」权限')
    return
  }
  resetAiDialog()
  aiDialogVisible.value = true
  try {
    const [suiteRes, caseRes, cfgRes] = await Promise.all([
      httpSuiteApi.getList({ project_id: proStore.projectInfo.id, page: 1, size: 200 }),
      httpCaseApi.getList({ project_id: proStore.projectInfo.id, page: 1, size: 2000 }),
      aiConfigApi.getSelectOptions().catch(() => null)
    ])
    const suiteData = suiteRes.data?.data || suiteRes.data || []
    suiteOptions.value = Array.isArray(suiteData) ? suiteData : []
    const caseData = caseRes.data?.data || caseRes.data || []
    caseOptions.value = Array.isArray(caseData) ? caseData : []
    const cfgData = cfgRes?.data?.data || cfgRes?.data || cfgRes || []
    aiConfigOptions.value = Array.isArray(cfgData) ? cfgData : []
  } catch (e) {
    console.error(e)
    suiteOptions.value = []
    caseOptions.value = []
    aiConfigOptions.value = []
  }
}

const handleAiGenerate = async () => {
  const prompt = (aiForm.value.prompt || '').trim()
  if (!prompt) {
    ElMessage.warning('请填写自然语言描述')
    return
  }
  aiGenerating.value = true
  try {
    const res = await aiGenerateApi.generatePerfScene({
      project_id: proStore.projectInfo.id,
      prompt,
      suite_id: (aiForm.value.case_ids || []).length ? undefined : (aiForm.value.suite_id || undefined),
      case_ids: (aiForm.value.case_ids || []).length ? aiForm.value.case_ids : undefined,
      tags: (aiForm.value.case_ids || []).length
        ? undefined
        : (aiForm.value.tags?.length ? aiForm.value.tags : undefined),
      ai_config_id: aiForm.value.ai_config_id || undefined
    })
    const data = res.data?.data || res.data || res
    aiDraft.value = data.draft || null
    aiRecordId.value = data.record_id || null
    if (!aiDraft.value) {
      ElMessage.error('未返回草稿')
      return
    }
    if (!aiDraft.value.config) aiDraft.value.config = {}
    await selectAllMatchedCases()
    if (aiDraft.value.importable) {
      ElMessage.success('已生成草稿，请确认后创建')
    } else {
      ElMessage.warning('未匹配到可用用例，请改写描述或选择套件/标签')
    }
  } catch (err) {
    console.error(err)
    ElMessage.error(formatApiDetail(err, '生成失败'))
  } finally {
    aiGenerating.value = false
  }
}

const handleAiImport = async () => {
  if (!aiDraft.value?.importable || !aiSelectedCaseIds.value.length) {
    ElMessage.warning('请至少勾选一个用例')
    return
  }
  aiImporting.value = true
  try {
    const res = await aiGenerateApi.importPerfScene({
      project_id: proStore.projectInfo.id,
      name: aiDraft.value.name,
      description: aiDraft.value.description,
      catalog_id: aiDraft.value.catalog_id || undefined,
      scene_items: aiDraft.value.scene_items || [],
      config: aiDraft.value.config || {},
      record_id: aiRecordId.value || undefined,
      selected_case_ids: (aiDraft.value.scene_items || [])
        .map((i) => Number(i.case_id))
        .filter((id) => !Number.isNaN(id))
    })
    const data = res.data?.data || res.data || res
    ElMessage.success('场景已创建')
    aiDialogVisible.value = false
    if (data?.id) {
      router.push(`/perf-scene/edit/${data.id}`)
    } else {
      fetchData()
    }
  } catch (err) {
    console.error(err)
    ElMessage.error(formatApiDetail(err, '创建失败'))
  } finally {
    aiImporting.value = false
  }
}

const handleEdit = (row) => {
  router.push(`/perf-scene/edit/${row.id}`)
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除场景 "${row.name}" 吗？`, '提示', { type: 'warning' })
    await perfSceneApi.delete(row.id)
    ElMessage.success('删除成功')
    fetchData()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const handleClone = async (row) => {
  try {
    await perfSceneApi.clone(row.id)
    ElMessage.success('复制成功')
    fetchData()
  } catch (err) {
    console.error(err)
    ElMessage.error('复制失败')
  }
}

const handleRun = async (row) => {
  const aiCfg = await loadPerfAiSettings()
  runForm.value = {
    sceneId: row.id,
    sceneName: row.name,
    envId: null,
    config: row.config || {},
    useWorkers: true,
    requestDetailLevel: 'brief',
    aiAnalyze: aiCfg.enabled && aiCfg.defaultOn
  }
  runOverridePerfTargets.value = false
  runPerfTargets.value = normalizePerfTargetsLocal(row.config?.perf_targets)
  // 加载环境列表
  try {
    const res = await envApi.getEnvList({ project_id: proStore.projectInfo.id })
    envList.value = res.data || res || []
  } catch (e) {
    console.error(e)
  }
  // 加载 Worker 列表
  try {
    const res = await perfWorkerApi.getList({ project_id: proStore.projectInfo.id })
    workerList.value = filterOnlineWorkers(parseWorkerList(res)).map((w) => ({
      ...w,
      selected: true,
      // 默认等权；勿用 max_concurrent 当权重，否则会和「本机上限」数字撞车、难理解
      weight: 1,
    }))
  } catch (e) {
    console.error(e)
    workerList.value = []
  }
  runDialogVisible.value = true
}

const getDurationTip = (config) => {
  const mode = config?.mode || 'fixed'
  const tips = {
    fixed: '压测持续的总时长',
    loop: '每个并发用户执行的总次数',
    stepping: '分阶段递增并发的阶段数',
    stream_burst: '每个虚拟用户只发送 1 次流式请求',
    sse_burst: '每个虚拟用户只发送 1 次流式请求',
    journey_fixed: '每位用户在持续时间内反复执行完整链路',
    journey_loop: '每个并发用户执行的完整链路次数'
  }
  return tips[mode] || ''
}

const extractApiError = (err, fallback = '操作失败') => {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    return detail.map(d => d.msg || d.message || JSON.stringify(d)).join('；')
  }
  return err?.message || fallback
}

const confirmRun = async () => {
  if (!runForm.value.envId) {
    ElMessage.warning('请选择执行环境')
    return
  }
  if (!workerList.value.length) {
    ElMessage.warning('暂无在线压测 Worker：请安装并上线 BrickCoreRunner / BrickCorePerf 后再启动')
    return
  }
  const selected = selectedWorkerRows.value
  if (!selected.length) {
    ElMessage.warning('请至少勾选一个压测执行器')
    return
  }
  if (selectedWorkerCapacity.value < runNeededConcurrent.value) {
    ElMessage.warning(
      `选中执行器容量不足：需要并发 ${runNeededConcurrent.value}，当前勾选总容量 ${selectedWorkerCapacity.value}`
    )
    return
  }
  runLoading.value = true
  try {
    const worker_ids = selected.map((w) => w.id)
    const worker_weights = {}
    for (const w of selected) {
      worker_weights[String(w.id)] = Math.max(1, Number(w.weight) || 1)
    }
    const startOpts = { worker_ids, worker_weights }
    if (runOverridePerfTargets.value) {
      startOpts.perf_targets = normalizePerfTargetsLocal(runPerfTargets.value)
    }
    await perfExecApi.start(
      runForm.value.sceneId,
      runForm.value.envId,
      true,
      runForm.value.requestDetailLevel,
      runForm.value.aiAnalyze,
      startOpts
    )
    ElMessage.success('性能测试已启动')
    runDialogVisible.value = false
    router.push('/perf-records')
  } catch (err) {
    console.error(err)
    ElMessage.error(extractApiError(err, '启动失败'))
  } finally {
    runLoading.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.scene-guide-collapse {
  margin-bottom: 14px;
}
.scene-guide-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  color: #606266;
  height: 40px;
  line-height: 40px;
}
.scene-guide-intro {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  margin-bottom: 10px;
}
.scene-guide-table {
  width: 100%;
  margin-bottom: 10px;
}
.scene-guide-extra {
  font-size: 12px;
  color: #909399;
  line-height: 1.7;
}
.scene-guide-extra .label {
  font-weight: 600;
  color: #606266;
}
.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.config-preview {
  background: #f5f7fa;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
  color: #666;
}
.config-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 4px 0;
}
.tip-icon {
  color: #909399;
  cursor: pointer;
  font-size: 14px;
}
.tip-icon:hover {
  color: #409eff;
}
.op-btns {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
}
.detail-level-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
}
.detail-level-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
  line-height: 1.65;
  max-width: 100%;
}
.ai-draft {
  margin-top: 4px;
}
.ai-case-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}
.ai-steps-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.ai-step-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 13px;
  color: #606266;
}
.ai-step-idx {
  min-width: 48px;
  color: #909399;
}
.ai-delay-summary {
  font-size: 13px;
  color: #606266;
}
.ai-prompt-wrap {
  width: 100%;
}
.ai-example-block {
  margin-top: 10px;
  width: 100%;
}
.ai-example-title {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  text-align: left;
}
.ai-example-list {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  width: 100%;
}
.ai-example-btn {
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 10px;
  width: 100%;
  margin: 0;
  padding: 8px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  line-height: 1.45;
  transition: border-color 0.15s, background 0.15s;
}
.ai-example-btn:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}
.ai-example-label {
  flex: 0 0 7.5em;
  width: 7.5em;
  color: #409eff;
  font-weight: 600;
  font-size: 13px;
  text-align: left;
  white-space: nowrap;
}
.ai-example-text {
  flex: 1;
  min-width: 0;
  color: #606266;
  font-weight: 400;
  font-size: 13px;
  text-align: left;
  word-break: break-word;
}
.ai-case-select {
  width: 100%;
}
.ai-case-select :deep(.el-select__selection) {
  flex-wrap: wrap;
  max-width: 100%;
}
.ai-case-select :deep(.el-tag) {
  max-width: 220px;
}
.ai-case-select :deep(.el-tag .el-select__tags-text),
.ai-case-select :deep(.el-tag__content) {
  display: inline-block;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}
.ai-case-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.35;
  padding: 2px 0;
}
.ai-case-option-name {
  font-size: 13px;
  color: #303133;
}
.ai-case-option-api {
  font-size: 12px;
  color: #909399;
}
</style>
