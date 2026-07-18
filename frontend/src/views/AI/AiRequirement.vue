<template>
  <div :class="{ 'requirement-embed-host': embedMode }">
  <PageCard :class="{ 'embed-hidden-card': embedMode }">
    <template v-if="!embedMode" #title>
      <div style="font-size: 18px; font-weight: bold;">📄 需求 → 功能用例</div>
    </template>
    <template #main>
      <!-- 工具栏 -->
      <div v-if="!embedMode" class="toolbar">
        <el-button type="primary" @click="openUpload" icon="Upload">上传需求文档</el-button>
        <el-button @click="loadList" icon="Refresh">刷新</el-button>
        <TableColumnPicker
          :items="reqListPickerItems"
          @toggle="setReqListColumnVisible"
          @reorder="setReqListPickerOrder"
          @reset="resetReqListColumns"
        />
      </div>

      <!-- 需求列表 -->
      <el-table v-if="!embedMode" :key="reqListTableKey" :data="reqList" v-loading="listLoading" stripe border style="margin-top: 12px;">
        <template v-for="col in reqListActiveColumns" :key="col.key">
          <el-table-column
            v-if="col.key === 'id'"
            prop="id"
            label="ID"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'name'"
            prop="name"
            label="需求名称"
            :min-width="col.minWidth || 160"
            show-overflow-tooltip
          />
          <el-table-column
            v-else-if="col.key === 'source_type'"
            label="类型"
            :width="col.width"
          >
            <template #default="{ row }">
              <el-tag size="small">{{ row.source_type?.toUpperCase() }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'image_count'"
            prop="image_count"
            label="图片"
            :width="col.width"
            align="center"
          />
          <el-table-column
            v-else-if="col.key === 'case_count'"
            prop="case_count"
            label="用例数"
            :width="col.width"
            align="center"
          />
          <el-table-column
            v-else-if="col.key === 'parse_status'"
            label="状态"
            :width="col.width"
          >
            <template #default="{ row }">
              <el-tag :type="row.parse_status === 'parsed' ? 'success' : 'info'" size="small">
                {{ statusLabel(row.parse_status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'create_time'"
            prop="create_time"
            label="创建时间"
            :width="col.width"
          />
        </template>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">用例</el-button>
            <el-button v-if="!isCommunityEdition" link type="success" @click="openArchiveDialog(row)">归档</el-button>
            <el-button link type="danger" @click="handleDeleteReq(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 上传弹窗 -->
      <el-dialog v-model="uploadVisible" width="520px" destroy-on-close>
        <template #header>
          <span class="dialog-title-with-tip">
            上传需求文档
            <el-tooltip
              :content="uploadUsageTooltip"
              placement="bottom-start"
              raw-content
              :show-after="200"
              popper-class="requirement-usage-tooltip"
            >
              <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <el-form label-width="90px">
          <el-form-item label="需求名称">
            <el-input v-model="uploadForm.name" placeholder="可选，默认取文件名" />
          </el-form-item>
          <el-form-item label="文档文件" required>
            <el-upload
              ref="uploadRef"
              :auto-upload="false"
              :limit="1"
              accept=".pdf,.docx,.txt,.md"
              :on-change="onFileChange"
              :on-remove="() => uploadForm.file = null"
            >
              <el-button type="primary" icon="Upload">选择文件</el-button>
              <template #tip>
                <div class="upload-tip">支持 PDF、Word(.docx)、TXT、Markdown；含图文档需配置 Vision 模型</div>
              </template>
            </el-upload>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="uploadVisible = false">取消</el-button>
          <el-button type="primary" :loading="uploading" @click="handleUpload">上传</el-button>
        </template>
      </el-dialog>

      <el-dialog v-if="!isCommunityEdition" v-model="archiveDialog.visible" title="归档到资料库" width="480px" destroy-on-close>
        <el-form label-width="90px">
          <el-form-item label="需求">
            <span>{{ archiveDialog.reqName }}</span>
          </el-form-item>
          <el-form-item label="目标文件夹">
            <el-select v-model="archiveDialog.folderId" placeholder="可选，不选则归入未分类" clearable filterable style="width: 100%;">
              <el-option v-for="f in archiveFolders" :key="f.id" :label="f.name" :value="f.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="文档标题">
            <el-input v-model="archiveDialog.title" placeholder="默认使用需求名称" />
          </el-form-item>
          <el-form-item label="">
            <el-checkbox v-model="archiveDialog.replaceIfExists">若已归档则替换</el-checkbox>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="archiveDialog.visible = false">取消</el-button>
          <el-button type="primary" :loading="archiveDialog.loading" @click="submitArchive">确认归档</el-button>
        </template>
      </el-dialog>

      <!-- 详情 / 用例抽屉 -->
      <TestingEmbedShell
        :inline="embedMode"
        v-model="detailVisible"
        :drawer-size="embedMode ? '100%' : '85%'"
        :with-header="!embedMode"
        :destroy-on-close="!embedMode"
      >
        <template v-if="!embedMode" #header>
          <span class="dialog-title-with-tip drawer-title-with-tip">
            {{ currentReq?.name || '需求用例' }}
            <el-tooltip
              :content="detailUsageTooltip"
              placement="bottom-start"
              raw-content
              :show-after="200"
              popper-class="requirement-usage-tooltip"
            >
              <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </span>
        </template>
        <div v-if="currentReq" class="detail-panel">
          <el-descriptions v-if="showEmbedSection('meta')" :column="4" border size="small" class="req-meta">
            <el-descriptions-item label="文档">{{ currentReq.file_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="字数">{{ currentReq.text_length || 0 }}</el-descriptions-item>
            <el-descriptions-item label="图片">{{ currentReq.image_count || 0 }} 张</el-descriptions-item>
            <el-descriptions-item label="页数">{{ currentReq.page_count || '-' }}</el-descriptions-item>
          </el-descriptions>
          <div v-if="showEmbedSection('meta') && canImportLibrary && !isCommunityEdition" class="detail-archive-bar">
            <el-button type="success" plain size="small" @click="openArchiveDialog(currentReq)">
              归档到资料库
            </el-button>
            <span class="detail-archive-hint">将需求正文归档为资料库文档，供报告生成与 RAG 检索引用</span>
          </div>

          <el-alert
            v-if="showEmbedSection('meta') && currentReq.image_count > 0"
            type="info"
            :closable="false"
            show-icon
            style="margin: 12px 0;"
            :title="`文档含 ${currentReq.image_count} 张图片：读图建议选 VL/Vision 模型（如 qwen-vl-max）；下拉列出全部已启用配置，可按名称自由切换`"
          />

          <!-- 导出与集成 -->
          <el-card v-if="showEmbedSection('config')" shadow="never" class="export-profile-card">
            <template #header>
              <div class="report-header">
                <b>导出与集成</b>
                <el-tag size="small" type="info">{{ exportProfileLabel }}</el-tag>
              </div>
            </template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              style="margin-bottom: 12px;"
              title="禅道模式需填写产品/模块/研发需求后再生成或导出；通用模式可直接生成，导出通用 XLSX（无禅道专属列）。命名槽位告警仅检查标题模板中实际用到的变量。"
            />
            <el-form :inline="true" class="export-defaults-form">
              <el-form-item label="导出目标">
                <el-radio-group v-model="exportProfile">
                  <el-radio
                    v-for="opt in exportProfileOptions"
                    :key="opt.value"
                    :label="opt.value"
                  >{{ opt.label }}</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item>
                <el-button :loading="savingExportProfile" @click="saveExportProfile">保存到项目</el-button>
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 禅道导入配置（无 API，手工绑定） -->
          <el-card v-if="showEmbedSection('config') && exportProfile === 'zentao'" shadow="never" class="zentao-card">
            <template #header>
              <div class="report-header">
                <b>禅道导入配置</b>
                <el-tag v-if="zentaoBindingsReady" type="success" size="small">已就绪</el-tag>
                <el-tag v-else type="warning" size="small">生成/导出前必填</el-tag>
              </div>
            </template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              style="margin-bottom: 12px;"
              title="所属产品、所属模块、相关研发需求需在禅道后台查准后填写；研发需求建议填「编号:名称」，编号仅用于标题前缀（可选）。适用阶段：优先级 1→冒烟测试阶段，2~4→系统测试阶段（自动）。"
            />
            <div class="zentao-section-title">项目级（当前项目，所有需求默认继承）</div>
            <el-form :inline="true" :model="projectZentao" class="export-defaults-form">
              <el-form-item label="所属产品" required>
                <el-input v-model="projectZentao.product" placeholder="知识中台产品(481)" style="width: 200px;" />
              </el-form-item>
              <el-form-item label="所属模块" required>
                <el-input v-model="projectZentao.module" placeholder="/2025-S1[#7743]" style="width: 200px;" />
              </el-form-item>
              <el-form-item label="相关研发需求" required>
                <el-input
                  v-model="projectZentao.related_story"
                  placeholder="58514:知识库重构 (优先级: 1.高...)"
                  style="width: 320px;"
                />
              </el-form-item>
              <el-form-item>
                <el-button :loading="savingProjectZentao" @click="saveProjectZentao">保存到项目</el-button>
              </el-form-item>
            </el-form>
            <div class="zentao-section-title">本需求覆盖（可选，留空则继承项目）</div>
            <el-form :inline="true" :model="reqZentao" class="export-defaults-form">
              <el-form-item label="所属产品">
                <el-input v-model="reqZentao.product" placeholder="继承项目" style="width: 200px;" />
              </el-form-item>
              <el-form-item label="所属模块">
                <el-input v-model="reqZentao.module" placeholder="继承项目" style="width: 200px;" />
              </el-form-item>
              <el-form-item label="相关研发需求">
                <el-input v-model="reqZentao.related_story" placeholder="继承项目" style="width: 320px;" />
              </el-form-item>
              <el-form-item>
                <el-button :loading="savingReqZentao" @click="saveReqZentao">保存本需求</el-button>
                <el-button
                  :disabled="!caseList.length || !zentaoBindingsReady"
                  @click="handleReapplyBindings"
                >刷新全部用例</el-button>
              </el-form-item>
            </el-form>
            <div v-if="effectiveZentao.product" class="effective-preview">
              <span class="effective-label">当前生效（导出 XLSX 使用）：</span>
              {{ effectiveZentao.product }} · {{ effectiveZentao.module }} · {{ effectiveZentao.related_story }}
            </div>
          </el-card>

          <!-- 用例命名规范（项目级模板，管理员可改） -->
          <el-card v-if="showEmbedSection('config')" shadow="never" class="naming-card">
            <template #header>
              <div class="report-header">
                <b>用例命名规范</b>
                <el-tag v-if="activeNamingTemplate" size="small" type="info">
                  {{ activeNamingTemplate.name }} v{{ activeNamingTemplate.version }}
                </el-tag>
                <el-tag v-if="!canEditNaming" size="small" type="warning">仅项目管理员可修改模板</el-tag>
              </div>
            </template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              style="margin-bottom: 12px;"
            >
              <template #title>
                <span>
                  标题由平台按 Jinja 模板组装：AI 输出语义字段后拼成最终标题。
                  内置模板：禅道·含编号 / 禅道·无编号 / 通用·简洁。
                  <el-button link type="primary" size="small" @click="namingSlotsHelpVisible = true">查看模板变量说明</el-button>
                </span>
              </template>
            </el-alert>
            <div class="zentao-section-title">本需求命名设置</div>
            <el-form :inline="true" class="gen-inline-form">
              <el-form-item label="指定模板">
                <el-select
                  v-model="reqNamingMeta.naming_template_id"
                  clearable
                  placeholder="按导出目标自动匹配"
                  style="width: 240px;"
                >
                  <el-option
                    v-for="t in namingConfig.templates"
                    :key="t.id"
                    :label="formatNamingTemplateOption(t)"
                    :value="t.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item v-if="suggestedTemplateId" label="推荐">
                <el-tag size="small" type="success">{{ suggestedTemplateName }}</el-tag>
              </el-form-item>
              <el-form-item>
                <el-button :loading="savingReqNaming" @click="saveReqNamingMeta">保存本需求</el-button>
                <el-button
                  :disabled="!caseList.length"
                  :loading="recalcTitlesLoading"
                  @click="handleRecalcTitles"
                >重算草稿标题</el-button>
              </el-form-item>
            </el-form>
            <div v-if="canEditNaming" class="naming-admin-block">
              <div class="zentao-section-title">项目级模板（管理员）</div>
              <el-form label-width="108px" label-position="right" class="naming-template-form">
                <el-form-item label="当前模板">
                  <el-select v-model="namingEditTemplateId" style="width: 220px;" @change="onNamingTemplateSelect">
                    <el-option
                      v-for="t in namingConfig.templates"
                      :key="t.id"
                      :label="`${t.name} (${t.id})`"
                      :value="t.id"
                    />
                  </el-select>
                  <el-button style="margin-left: 8px;" @click="addNamingTemplate">新增模板</el-button>
                  <el-button
                    type="danger"
                    plain
                    :disabled="namingConfig.templates.length <= 1"
                    @click="removeNamingTemplate"
                  >删除当前</el-button>
                </el-form-item>
                <el-form-item label="模板名称">
                  <el-input v-model="namingEditTemplate.name" style="width: 320px;" />
                </el-form-item>
                <el-form-item label="适用类型">
                  <el-input
                    v-model="namingRequirementTypesText"
                    placeholder="* 表示全部，或 default,api 逗号分隔"
                    style="width: 420px;"
                  />
                </el-form-item>
                <el-form-item>
                  <template #label>
                    <span class="naming-label-with-help">
                      标题模板
                      <el-button link type="primary" size="small" @click="namingSlotsHelpVisible = true">变量说明</el-button>
                    </span>
                  </template>
                  <el-input
                    v-model="namingEditTemplate.title_template"
                    type="textarea"
                    :rows="3"
                    placeholder="Jinja2，如 【#{{ story_no }}_{{ main_module }}_{{ sub_module }}】（{{ feature_point }}）{{ case_description }}"
                    style="width: 100%; max-width: 720px;"
                  />
                </el-form-item>
                <el-form-item label="导出列映射">
                  <el-input
                    v-model="namingExportColumnsJson"
                    type="textarea"
                    :rows="6"
                    placeholder="JSON 数组：[{column, expr}, ...]"
                    style="width: 100%; max-width: 720px; font-family: monospace;"
                  />
                </el-form-item>
                <el-form-item label="预览样例">
                  <div class="naming-preview-grid">
                    <el-input v-model="namingPreviewSample.story_no" placeholder="需求编号 story_no" size="small" />
                    <el-input v-model="namingPreviewSample.main_module" placeholder="主模块 main_module" size="small" />
                    <el-input v-model="namingPreviewSample.sub_module" placeholder="子模块 sub_module" size="small" />
                    <el-input v-model="namingPreviewSample.feature_point" placeholder="功能点 feature_point" size="small" />
                    <el-input
                      v-model="namingPreviewSample.case_description"
                      placeholder="用例描述 case_description"
                      size="small"
                      style="grid-column: span 2;"
                    />
                    <el-button size="small" :loading="namingPreviewLoading" @click="runNamingPreview">预览标题</el-button>
                  </div>
                </el-form-item>
                <el-form-item v-if="namingPreviewResult.title" label="预览结果">
                  <div class="naming-preview-result">{{ namingPreviewResult.title }}</div>
                  <el-alert
                    v-for="(w, i) in namingPreviewResult.warnings"
                    :key="i"
                    type="warning"
                    :closable="false"
                    show-icon
                    style="margin-top: 6px;"
                    :title="w"
                  />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :loading="savingNamingConfig" @click="saveNamingConfig">
                    保存项目命名配置
                  </el-button>
                  <el-checkbox v-model="setActiveOnSave" style="margin-left: 12px;">设为项目默认模板</el-checkbox>
                </el-form-item>
              </el-form>
            </div>
            <div v-else-if="activeNamingTemplate?.title_template" class="naming-readonly">
              <span class="effective-label">当前生效模板：</span>
              <code class="naming-template-code">{{ activeNamingTemplate.title_template }}</code>
            </div>
          </el-card>

          <!-- 生成范围 + 侧栏队列 -->
          <el-card v-if="showEmbedSection('document')" shadow="never" class="scope-card">
            <template #header>
              <div class="report-header">
                <b>生成范围</b>
                <el-button link type="primary" @click="selectAllSections">全选</el-button>
                <el-button link @click="clearSectionSelection">清空</el-button>
                <el-button
                  link
                  type="success"
                  :loading="selectingUncovered"
                  :disabled="!docSections.length"
                  @click="selectUncoveredSections"
                >
                  选未覆盖
                </el-button>
                <el-button link type="warning" :loading="reparsing" @click="handleReparseDocument">
                  重新解析
                </el-button>
              </div>
            </template>
            <el-alert
              v-if="scopeEstimate"
              :type="scopeEstimate.level === 'block' ? 'error' : scopeEstimate.level === 'warn' ? 'warning' : 'success'"
              :closable="false"
              show-icon
              style="margin-bottom: 10px;"
              :title="scopeEstimate.message"
            />
            <div v-if="docSections.length" class="scope-layout">
              <div class="scope-main">
                <div class="scope-body">
                  <el-tree
                    ref="sectionTreeRef"
                    :data="sectionTreeData"
                    show-checkbox
                    node-key="id"
                    default-expand-all
                    :props="{ label: 'label', children: 'children' }"
                    @check="onSectionCheck"
                  />
                  <p v-if="scopeEstimate" class="scope-meta">
                    已选 {{ selectedSectionIds.length }} 个章节 ·
                    约 {{ scopeEstimate.char_count }} 字 ·
                    {{ scopeEstimate.image_count }} 张图 ·
                    预估输入 ~{{ scopeEstimate.estimated_input_tokens }} tokens
                    <template v-if="scopeEstimate.recommended_count">
                      · <b>建议用例 {{ scopeEstimate.recommended_count }} 条</b>
                    </template>
                  </p>
                </div>
                <div class="scope-actions">
                  <el-button type="primary" plain size="small" @click="addToBatchQueue">
                    将当前勾选加入队列
                  </el-button>
                </div>
              </div>
              <div class="batch-sidebar">
                <div class="batch-sidebar-header">
                  <b>生成队列</b>
                  <el-tag size="small" type="info">{{ batchQueue.length }}</el-tag>
                </div>
                <el-empty v-if="!batchQueue.length" description="勾选章节后点「加入队列」" :image-size="48" />
                <div v-else class="batch-queue-list">
                  <div
                    v-for="(item, idx) in batchQueue"
                    :key="item._key"
                    class="batch-queue-item"
                    :class="{ active: activeBatchKey === item._key }"
                    @click="activeBatchKey = item._key"
                  >
                    <div class="batch-queue-title">
                      <span class="batch-idx">{{ idx + 1 }}</span>
                      <el-input v-model="item.name" size="small" @click.stop />
                    </div>
                    <p class="batch-queue-meta">{{ batchSectionSummary(item.scope_section_ids) }}</p>
                    <div class="batch-queue-row">
                      <span>参考条数</span>
                      <el-input-number v-model="item.count" :min="1" :max="50" size="small" @click.stop />
                    </div>
                    <p v-if="countCasesForBatch(item.name)" class="batch-queue-existing">
                      本批已有 {{ countCasesForBatch(item.name) }} 条
                    </p>
                    <div class="batch-queue-ops" @click.stop>
                      <el-button link type="warning" size="small" @click="handleSupplementBatch(item)">补充</el-button>
                      <el-button link size="small" :disabled="idx === 0" @click="moveBatchItem(idx, -1)">↑</el-button>
                      <el-button link size="small" :disabled="idx === batchQueue.length - 1" @click="moveBatchItem(idx, 1)">↓</el-button>
                      <el-button link type="danger" size="small" @click="removeBatchItem(idx)">删</el-button>
                    </div>
                  </div>
                </div>
                <div v-if="batchQueue.length" class="batch-sidebar-footer">
                  <el-button size="small" @click="clearBatchQueue">清空队列</el-button>
                </div>
              </div>
            </div>
            <el-empty v-else description="无章节结构（旧文档可重新上传 Word 以解析标题）" :image-size="60" />
          </el-card>

          <!-- 章节覆盖检查 -->
          <el-card v-if="showCoverageCard" shadow="never" class="coverage-card">
            <template #header>
              <div class="report-header">
                <b>章节覆盖检查</b>
                <el-tag :type="coverageTagType" size="small">{{ coverageSummary }}</el-tag>
                <el-button link type="primary" size="small" @click="refreshSectionCoverage">刷新</el-button>
              </div>
            </template>
            <div class="coverage-stats">
              <span>文档共 <b>{{ sectionCoverage.total }}</b> 节</span>
              <span>已有用例覆盖 <b>{{ sectionCoverage.covered_count }}</b> 节</span>
              <span>未覆盖 <b class="coverage-warn">{{ sectionCoverage.uncovered_count }}</b> 节</span>
              <span
                v-if="sectionCoverage.projected_covered_count != null && pendingQueueSectionIds.length"
                class="coverage-projected"
              >
                队列执行后预计覆盖 <b>{{ sectionCoverage.projected_covered_count }}</b> 节
              </span>
            </div>
            <el-collapse v-if="sectionCoverage.uncovered_sections?.length" class="coverage-collapse">
              <el-collapse-item :title="`未覆盖章节（${sectionCoverage.uncovered_sections.length}）`" name="uncovered">
                <ul class="coverage-list">
                  <li v-for="s in sectionCoverage.uncovered_sections" :key="s.id">
                    <el-tag size="small" type="info">L{{ s.level || 1 }}</el-tag>
                    {{ s.title }}
                  </li>
                </ul>
              </el-collapse-item>
            </el-collapse>
          </el-card>

          <!-- 批量配置表（与侧栏队列同源） -->
          <el-card v-if="batchQueue.length" shadow="never" class="batch-table-card">
            <template #header>
              <div class="report-header">
                <b>批量生成配置</b>
                <span class="report-meta">与右侧队列同步，可在此精细编辑</span>
                <el-button link type="primary" size="small" @click="addEmptyBatchRow">+ 新增一行</el-button>
              </div>
            </template>
            <el-table :data="batchQueue" border size="small" row-key="_key" class="batch-config-table">
              <el-table-column label="#" width="44" align="center">
                <template #default="{ $index }">{{ $index + 1 }}</template>
              </el-table-column>
              <el-table-column label="批次名称" min-width="160">
                <template #default="{ row }">
                  <el-input v-model="row.name" size="small" placeholder="如：场景一" />
                </template>
              </el-table-column>
              <el-table-column label="章节范围" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">
                  <el-button link type="primary" size="small" class="batch-range-btn" @click="openSectionPicker(row)">
                    {{ batchSectionSummary(row.scope_section_ids) }}
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column width="88" align="center">
                <template #header>
                  <span class="label-with-tip">
                    <span>AI自定</span>
                    <el-tooltip content="开启后本批不传精确条数，按软区间覆盖生成" placement="top">
                      <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>
                <template #default="{ row }">
                  <el-switch
                    :model-value="row.count_mode === 'auto'"
                    size="small"
                    @change="(v) => { row.count_mode = v ? 'auto' : 'fixed' }"
                  />
                </template>
              </el-table-column>
              <el-table-column width="120" align="center" class-name="batch-count-col">
                <template #header>
                  <span class="label-with-tip">
                    <span>参考条数</span>
                    <el-tooltip content="本批 Prompt 参考目标；AI 自定模式下忽略" placement="top">
                      <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>
                <template #default="{ row }">
                  <el-input-number
                    v-model="row.count"
                    :min="1"
                    :max="fixedCountHardMax"
                    size="small"
                    controls-position="right"
                    class="batch-count-input"
                    :disabled="row.count_mode === 'auto'"
                  />
                </template>
              </el-table-column>
              <el-table-column label="禅道" width="72" align="center">
                <template #default="{ row }">
                  <el-switch v-model="row.useCustomZentao" size="small" />
                </template>
              </el-table-column>
              <el-table-column label="禅道配置" min-width="120">
                <template #default="{ row }">
                  <span v-if="!row.useCustomZentao" class="batch-inherit-tip">继承项目/需求</span>
                  <el-button v-else link type="primary" size="small" @click="openBatchZentaoDialog(row)">
                    {{ row.product?.trim() ? '已配置 · 编辑' : '点击填写' }}
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column width="76" align="center">
                <template #header>
                  <span class="label-with-tip">
                    <span>替换</span>
                    <el-tooltip content="勾选后：生成前删除同批次名已有用例" placement="top">
                      <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>
                <template #default="{ row }">
                  <el-switch
                    v-model="row.replace"
                    size="small"
                    @change="(v) => onBatchReplaceChange(row, v)"
                  />
                </template>
              </el-table-column>
              <el-table-column width="76" align="center">
                <template #header>
                  <span class="label-with-tip">
                    <span>补充</span>
                    <el-tooltip content="勾选后：批量生成时读取同批次名已有用例并追加" placement="top">
                      <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>
                <template #default="{ row }">
                  <el-switch
                    v-model="row.supplement"
                    size="small"
                    @change="(v) => onBatchSupplementChange(row, v)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="已有" width="52" align="center">
                <template #default="{ row }">
                  {{ countCasesForBatch(row.name) || '-' }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="148" fixed="right" align="center">
                <template #default="{ row, $index }">
                  <el-button link type="warning" size="small" @click="handleSupplementBatch(row)">补充</el-button>
                  <el-button link size="small" :disabled="$index === 0" @click="moveBatchItem($index, -1)">上移</el-button>
                  <el-button link type="danger" size="small" @click="removeBatchItem($index)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <el-dialog v-model="sectionPickerVisible" title="选择章节范围" width="520px" destroy-on-close>
            <el-tree
              ref="pickerTreeRef"
              :data="sectionTreeData"
              show-checkbox
              node-key="id"
              default-expand-all
              :props="{ label: 'label', children: 'children' }"
            />
            <template #footer>
              <el-button @click="sectionPickerVisible = false">取消</el-button>
              <el-button type="primary" @click="confirmSectionPicker">确定</el-button>
            </template>
          </el-dialog>

          <el-dialog
            v-model="batchZentaoVisible"
            title="批次禅道配置"
            width="560px"
            destroy-on-close
            @closed="batchZentaoForm = null"
          >
            <el-form v-if="batchZentaoForm" label-width="110px" class="batch-zentao-form">
              <div class="batch-zentao-sync-row">
                <el-button size="small" @click="syncBatchZentaoFrom('project')">同步项目配置</el-button>
                <el-button size="small" @click="syncBatchZentaoFrom('effective')">同步需求生效配置</el-button>
                <span class="batch-zentao-sync-tip">产品与模块多批次通常相同，可一键填入</span>
              </div>
              <el-form-item label="所属产品" required>
                <el-input v-model="batchZentaoForm.product" placeholder="知识中台产品(481)" />
              </el-form-item>
              <el-form-item label="所属模块" required>
                <el-input v-model="batchZentaoForm.module" placeholder="/2026-S3[#8193]" />
              </el-form-item>
              <el-form-item label="相关研发需求" required>
                <el-input
                  v-model="batchZentaoForm.related_story"
                  type="textarea"
                  :rows="2"
                  placeholder="58514:知识库重构 (优先级: 1.高...)"
                />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="batchZentaoVisible = false">取消</el-button>
              <el-button type="primary" @click="saveBatchZentaoDialog">确定</el-button>
            </template>
          </el-dialog>

          <el-dialog
            v-model="namingSlotsHelpVisible"
            title="标题模板变量说明"
            width="720px"
            destroy-on-close
          >
            <p class="naming-help-intro">
              标题模板使用 Jinja2 语法，变量写作 <code v-pre>{{ 变量名 }}</code>。可自由组合括号、标点与固定文字；修改后点「预览标题」查看效果，保存后才会用于生成与导出。
            </p>
            <el-table :data="namingSlotHelpRows" border size="small" class="naming-slot-help-table">
              <el-table-column prop="name" label="变量" width="148">
                <template #default="{ row }">
                  <code>{{ formatNamingSlotVar(row.name) }}</code>
                </template>
              </el-table-column>
              <el-table-column prop="label" label="含义" width="108" />
              <el-table-column prop="source" label="取值来源" min-width="200" show-overflow-tooltip />
              <el-table-column prop="example" label="示例" width="140" show-overflow-tooltip />
            </el-table>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              style="margin-top: 12px;"
              title="feature_point 与 case_description 由 AI 按用例生成；story_no 来自禅道「相关研发需求」首部数字（可选，缺失时回退需求短码/ID）；main_module / sub_module 优先取 AI 输出，缺失时回退为文档章节标题。缺槽告警仅针对标题模板中用到的变量。"
            />
            <template #footer>
              <el-button type="primary" @click="namingSlotsHelpVisible = false">知道了</el-button>
            </template>
          </el-dialog>

          <!-- 生成配置 -->
          <el-card v-if="showEmbedSection('document')" shadow="never" class="gen-card">
            <template #header><b>AI 生成配置</b></template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              class="count-expectation-alert"
              title="条数为参考目标：实际入库条数由模型决定，常与填写值不同（略多或略少均正常）。报告会对比「参考目标 / 实际入库」；批量执行仅以表格每行「条数」为准，不会与底部条数相加。"
            />
            <el-form :inline="true" :model="genForm" class="gen-inline-form">
              <el-form-item label="Vision 模型" v-if="scopedImageCount > 0 || batchQueueImageCount > 0">
                <el-select
                  v-model="genForm.vision_config_id"
                  placeholder="选择已启用配置"
                  clearable
                  style="width: 260px;"
                >
                  <el-option
                    v-for="c in enabledConfigs"
                    :key="c.id"
                    :label="configOptionLabel(c)"
                    :value="c.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="用例生成">
                <el-select
                  v-model="genForm.case_gen_config_id"
                  placeholder="选择已启用配置"
                  clearable
                  style="width: 260px;"
                >
                  <el-option
                    v-for="c in enabledConfigs"
                    :key="c.id"
                    :label="configOptionLabel(c)"
                    :value="c.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span class="label-with-tip">
                    <span>AI 自定条数</span>
                    <el-tooltip
                      content="开启后不传精确条数，由模型按功能点覆盖生成，受项目配置的软区间约束；可在 AI 模型配置里调整上下限"
                      placement="top"
                    >
                      <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>
                <el-switch
                  :model-value="isAutoCountMode"
                  @change="(v) => { genForm.count_mode = v ? 'auto' : 'fixed' }"
                />
              </el-form-item>
              <el-form-item v-if="!batchQueue.length && !isAutoCountMode">
                <template #label>
                  <span class="label-with-tip">
                    <span>参考条数</span>
                    <el-tooltip
                      content="写入 Prompt 的参考目标，非精确上限；实际条数见生成报告。条数偏少时模型会优先输出各模块主路径核心用例。"
                      placement="top"
                    >
                      <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>
                <div class="count-with-recommend">
                  <el-input-number v-model="genForm.count" :min="1" :max="fixedCountHardMax" />
                  <template v-if="recommendedCaseCount">
                    <el-tag size="small" type="info" class="count-recommend-tag">
                      建议 {{ recommendedCaseCount }}
                    </el-tag>
                    <el-button
                      link
                      type="primary"
                      size="small"
                      @click="applyRecommendedCount"
                    >采用建议</el-button>
                  </template>
                </div>
              </el-form-item>
              <el-form-item v-else-if="batchQueue.length && !isAutoCountMode">
                <template #label>
                  <span class="label-with-tip">
                    <span>入队参考条数</span>
                    <el-tooltip
                      content="新入队批次默认用当前勾选范围的建议条数；表格「条数」可再改。若批次开了 AI 自定则忽略本值。"
                      placement="top"
                    >
                      <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>
                <div class="count-with-recommend">
                  <el-input-number v-model="genForm.count" :min="1" :max="fixedCountHardMax" />
                  <template v-if="recommendedCaseCount">
                    <el-tag size="small" type="info" class="count-recommend-tag">
                      建议 {{ recommendedCaseCount }}
                    </el-tag>
                    <el-button
                      link
                      type="primary"
                      size="small"
                      @click="applyRecommendedCount"
                    >采用建议</el-button>
                  </template>
                </div>
              </el-form-item>
              <el-alert
                v-if="isAutoCountMode && softMinCount && softMaxCount"
                type="info"
                :closable="false"
                show-icon
                class="count-auto-alert"
                :title="`AI 自定 · 软区间约 ${softMinCount}～${softMaxCount} 条`"
                :description="softRangeExplain || '区间由当前勾选范围建议条数与项目配置计算'"
              />
              <p
                v-else-if="scopeEstimate?.recommend_reason && !isAutoCountMode"
                class="count-recommend-hint"
              >{{ scopeEstimate.recommend_reason }}</p>
              <el-form-item v-if="!batchQueue.length">
                <template #label>
                  <span class="label-with-tip">
                    <span>替换已有</span>
                    <el-tooltip
                      content="生成前清空本需求下全部旧用例，再写入本次结果"
                      placement="top"
                    >
                      <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>
                <el-switch
                  v-model="genForm.replace_existing"
                  @change="onSingleGenReplaceChange"
                />
              </el-form-item>
              <el-form-item v-if="!batchQueue.length">
                <template #label>
                  <span class="label-with-tip">
                    <span>补充本批</span>
                    <el-tooltip
                      content="按当前勾选推断的批次名，读取同批已有用例后追加生成；与「替换已有」互斥"
                      placement="top"
                    >
                      <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>
                <el-switch
                  v-model="genForm.supplement"
                  @change="onSingleGenSupplementChange"
                />
              </el-form-item>
              <el-form-item v-else>
                <template #label>
                  <span class="label-with-tip">
                    <span>批量前清空</span>
                    <el-tooltip
                      content="批量生成开始前清空本需求下全部旧用例（各批次「替换本批」仅删除同批次名用例）"
                      placement="top"
                    >
                      <el-icon class="title-tip-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>
                <el-switch v-model="genForm.replace_existing" />
              </el-form-item>
            </el-form>
            <KnowledgeRefSelector v-model="knowledgeRefs" />
            <el-form :model="genForm" label-width="88px" class="extra-instructions-form">
              <el-form-item label="额外要求">
                <el-input
                  v-model="genForm.extra_instructions"
                  type="textarea"
                  :rows="3"
                  maxlength="2000"
                  show-word-limit
                  placeholder="例如：多用边界/异常场景；步骤写细到具体按钮与提示文案；不要生成登录相关用例。&#10;标题、禅道导出字段等由平台自动处理，无需在此填写。"
                />
              </el-form-item>
            </el-form>
            <el-alert
              v-if="batchProgress"
              :type="batchProgress.failed ? 'warning' : 'success'"
              :closable="false"
              show-icon
              style="margin-bottom: 10px;"
              :title="batchProgress.title"
            />
            <div v-if="batchGenerating && batchJobProgress" class="batch-job-progress">
              <el-progress
                :percentage="batchJobProgress.percent"
                :status="batchJobProgress.failed ? 'exception' : undefined"
              />
              <div class="batch-job-progress-text">{{ batchJobProgress.title }}</div>
            </div>
            <el-form :inline="true">
              <el-form-item>
                <el-button type="primary" :loading="generating" @click="handleGenerate" icon="MagicStick">
                  单次生成（当前勾选）
                </el-button>
                <el-button
                  type="primary"
                  :loading="batchGenerating"
                  :disabled="!batchQueue.length"
                  @click="handleBatchGenerate"
                  icon="List"
                >
                  批量生成（队列 {{ batchQueue.length }} 批）
                </el-button>
                <el-button
                  type="success"
                  :disabled="!caseList.length"
                  @click="handleExport"
                  icon="Download"
                >导出 XLSX</el-button>
              </el-form-item>
            </el-form>
          </el-card>

          <!-- AI 生成报告 -->
          <el-card
            v-if="showEmbedSection('document') && (generateReport || generateJobHistory.length)"
            shadow="never"
            class="report-card"
          >
            <template #header>
              <div class="report-header report-header-wrap">
                <b>AI 生成报告</b>
                <el-select
                  v-if="generateJobHistory.length"
                  v-model="selectedReportJobId"
                  placeholder="历史生成记录"
                  size="small"
                  style="width: 320px; margin-left: 8px;"
                  @change="onSelectGenerateJob"
                >
                  <el-option
                    v-for="j in generateJobHistory"
                    :key="j.id"
                    :label="jobHistoryLabel(j)"
                    :value="j.id"
                  />
                </el-select>
                <el-button
                  v-if="selectedReportJobId && canDeleteGenerateJob"
                  link
                  type="danger"
                  size="small"
                  @click="deleteGenerateJobRecord"
                >删除记录</el-button>
                <span v-if="reportMeta.time" class="report-meta">{{ reportMeta.time }}</span>
                <span v-if="reportMeta.duration_ms" class="report-meta">
                  耗时 {{ (reportMeta.duration_ms / 1000).toFixed(1) }}s · Token {{ reportMeta.tokens_used || 0 }}
                </span>
              </div>
            </template>
            <el-empty
              v-if="!generateReport"
              description="请选择一条生成记录查看报告"
              :image-size="48"
            />
            <el-collapse v-else v-model="reportCollapse">
              <el-collapse-item
                v-if="generateReport.batch_mode && (generateReport.batch_results?.length || generateReport.in_progress)"
                name="batch"
              >
                <template #title>
                  <span>批量执行</span>
                  <el-tag
                    v-if="generateReport.in_progress"
                    size="small"
                    type="warning"
                    style="margin-left: 8px;"
                  >
                    进行中 {{ batchResultsDoneCount }}/{{ generateReport.total_batches || '?' }} 批
                    · 已成功 {{ batchSuccessCount }}
                    <template v-if="batchFailCount"> · 失败 {{ batchFailCount }}</template>
                  </el-tag>
                  <el-tag v-else size="small" style="margin-left: 8px;">
                    {{ batchSuccessCount }}/{{ generateReport.batch_results.length }} 批成功
                  </el-tag>
                </template>
                <el-table :data="generateReport.batch_results" border size="small">
                  <el-table-column prop="name" label="批次" min-width="120" />
                  <el-table-column label="章节范围" min-width="180" show-overflow-tooltip>
                    <template #default="{ row }">
                      <span class="report-meta">{{ batchReportSectionSummary(row) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="模式" width="100" align="center">
                    <template #default="{ row }">
                      <el-tag v-if="row.supplement" type="warning" size="small">补充</el-tag>
                      <el-tag v-else-if="row.replace" type="danger" size="small">替换</el-tag>
                      <el-tag v-else-if="row.count_mode === 'auto'" type="success" size="small">AI自定</el-tag>
                      <el-tag v-else size="small" type="info">新建</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="状态" width="90">
                    <template #default="{ row }">
                      <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                        {{ row.success ? '成功' : '失败' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="条数" width="120" align="center">
                    <template #default="{ row }">
                      <template v-if="row.count_mode === 'auto'">
                        {{ row.soft_min_count || '?' }}～{{ row.soft_max_count || '?' }}
                        <div v-if="row.partial_truncated" class="report-meta">已截断</div>
                      </template>
                      <template v-else>
                        参考 {{ row.requested_count ?? '-' }} / 实际 {{ row.parsed_count ?? row.created_count ?? 0 }}
                      </template>
                    </template>
                  </el-table-column>
                  <el-table-column label="条数说明" min-width="200" show-overflow-tooltip>
                    <template #default="{ row }">
                      <span class="report-meta">{{ row.count_note || '-' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="读图" width="88" align="center">
                    <template #default="{ row }">
                      <template v-if="row.generate_report?.vision">
                        <el-tag
                          v-if="row.generate_report.vision.skipped"
                          size="small"
                          type="info"
                        >跳过</el-tag>
                        <el-tag
                          v-else-if="row.generate_report.vision.success"
                          size="small"
                          type="success"
                        >{{ row.generate_report.vision.ok_count || 0 }} 张</el-tag>
                        <el-tag v-else size="small" type="warning">
                          {{ row.generate_report.vision.ok_count || 0 }}/{{ row.generate_report.vision.image_total || 0 }}
                        </el-tag>
                      </template>
                      <span v-else class="report-meta">-</span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="tokens_used" label="Token" width="80" align="center" />
                  <el-table-column prop="error" label="错误信息" min-width="160" show-overflow-tooltip />
                  <el-table-column label="操作" width="96" align="center" fixed="right">
                    <template #default="{ row, $index }">
                      <el-button
                        v-if="!row.success && !generateReport.in_progress"
                        link
                        type="primary"
                        size="small"
                        :loading="retryingBatchIndex === (row.index ?? $index)"
                        :disabled="batchGenerating || generating || (retryingBatchIndex != null && retryingBatchIndex !== (row.index ?? $index))"
                        @click="handleRetryFailedBatch(row, row.index ?? $index)"
                      >重新生成</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-collapse-item>
              <el-collapse-item
                name="vision"
                v-if="generateReport.vision && (currentReq.image_count > 0 || !generateReport.vision.skipped)"
              >
                <template #title>
                  <span>Vision 读图</span>
                  <el-tag
                    :type="visionStatusType"
                    size="small"
                    style="margin-left: 8px;"
                  >{{ visionStatusText }}</el-tag>
                  <span class="report-sub" v-if="generateReport.vision.model">
                    {{ generateReport.vision.config_name }} ({{ generateReport.vision.model }})
                  </span>
                </template>
                <el-alert
                  v-if="generateReport.vision.batch_note"
                  type="info"
                  :closable="false"
                  :title="generateReport.vision.batch_note"
                  show-icon
                  style="margin-bottom: 8px;"
                />
                <el-alert
                  v-if="generateReport.vision.skipped && generateReport.vision.message"
                  type="warning"
                  :closable="false"
                  :title="generateReport.vision.message"
                  show-icon
                  style="margin-bottom: 8px;"
                />
                <el-alert
                  v-if="generateReport.vision.warning"
                  type="warning"
                  :closable="false"
                  :title="generateReport.vision.warning"
                  show-icon
                  style="margin-bottom: 8px;"
                />
                <p v-if="!generateReport.vision.skipped" class="report-line">
                  成功 {{ generateReport.vision.ok_count || 0 }} / 失败 {{ generateReport.vision.fail_count || 0 }}
                  · 共 {{ generateReport.vision.image_total || 0 }} 张
                </p>
                <div
                  v-for="img in (generateReport.vision.images || [])"
                  :key="img.index"
                  class="report-block"
                >
                  <div class="report-block-title">
                    图片 {{ img.index }}
                    <el-tag :type="img.ok ? 'success' : 'danger'" size="small">
                      {{ img.ok ? '成功' : '失败' }}
                    </el-tag>
                    <span v-if="img.tokens" class="report-meta">Token {{ img.tokens }}</span>
                  </div>
                  <pre v-if="img.error" class="report-pre report-pre-error">{{ img.error }}</pre>
                  <pre v-else-if="img.content" class="report-pre">{{ img.content }}</pre>
                </div>
              </el-collapse-item>
              <el-collapse-item name="case_gen">
                <template #title>
                  <span>用例生成</span>
                  <el-tag
                    :type="caseGenStatusType"
                    size="small"
                    style="margin-left: 8px;"
                  >{{ caseGenStatusText }}</el-tag>
                  <span class="report-sub" v-if="generateReport.case_gen?.model">
                    {{ generateReport.case_gen.config_name }} ({{ generateReport.case_gen.model }})
                  </span>
                </template>
                <p class="report-line" v-if="generateReport.case_gen?.aggregated || generateReport.batch_mode">
                  <el-tag type="info" size="small" style="margin-right: 8px;">批量汇总</el-tag>
                  <el-tag
                    v-if="generateReport.case_gen?.count_mode === 'mixed'"
                    type="warning"
                    size="small"
                    style="margin-right: 8px;"
                  >混合模式（{{ (generateReport.case_gen.modes || []).join('/') }}）</el-tag>
                  <el-tag
                    v-else-if="generateReport.case_gen?.count_mode === 'auto'"
                    type="success"
                    size="small"
                    style="margin-right: 8px;"
                  >
                    AI 自定
                    <template v-if="generateReport.case_gen.soft_min_count != null">
                      ·
                      <template v-if="(generateReport.case_gen.batch_success_count || 0) > 1">合计 </template>
                      {{ generateReport.case_gen.soft_min_count }}～{{ generateReport.case_gen.soft_max_count }}
                    </template>
                  </el-tag>
                  <el-tag v-if="generateReport.case_gen?.partial_truncated" type="danger" size="small" style="margin-right: 8px;">
                    含截断批次
                  </el-tag>
                  成功 {{ generateReport.case_gen?.batch_success_count ?? batchSuccessCount }}/{{ generateReport.case_gen?.batch_total ?? batchResultsDoneCount }} 批
                  · 合计入库 {{ generateReport.case_gen?.actual_created_count ?? generateReport.case_gen?.parsed_count ?? 0 }} 条
                  <span class="report-sub"> · 各批条数语义见「批量执行」</span>
                  <span v-if="generateReport.case_gen?.tokens"> · Token {{ generateReport.case_gen.tokens }}</span>
                </p>
                <p class="report-line" v-else>
                  <el-tag v-if="generateReport.case_gen?.supplement_mode" type="warning" size="small" style="margin-right: 8px;">
                    补充 · {{ generateReport.case_gen.supplement_batch_name }}
                    <template v-if="generateReport.case_gen.existing_cases_count != null">
                      （原有 {{ generateReport.case_gen.existing_cases_count }} 条）
                    </template>
                  </el-tag>
                  <el-tag v-if="generateReport.case_gen?.count_mode === 'auto'" type="success" size="small" style="margin-right: 8px;">
                    AI 自定 · {{ generateReport.case_gen.soft_min_count }}～{{ generateReport.case_gen.soft_max_count }}
                  </el-tag>
                  <el-tag v-if="generateReport.case_gen?.partial_truncated" type="danger" size="small" style="margin-right: 8px;">
                    已截断
                  </el-tag>
                  <template v-if="generateReport.case_gen?.count_mode === 'auto'">
                    入库 {{ generateReport.case_gen?.parsed_count }} 条
                    <span v-if="generateReport.case_gen?.range_explain" class="report-sub">
                      · {{ generateReport.case_gen.range_explain }}
                    </span>
                  </template>
                  <template v-else>
                    参考目标 {{ generateReport.case_gen?.requested_count }} 条 · 本次新增入库 {{ generateReport.case_gen?.parsed_count }} 条
                  </template>
                  <el-tag
                    v-if="caseCountVarianceTag"
                    :type="caseCountVarianceTag.type"
                    size="small"
                    style="margin-left: 8px;"
                  >{{ caseCountVarianceTag.text }}</el-tag>
                  <span v-if="generateReport.case_gen?.tokens"> · Token {{ generateReport.case_gen.tokens }}</span>
                </p>
                <el-alert
                  v-if="generateReport.case_gen?.count_note"
                  type="info"
                  :closable="false"
                  show-icon
                  style="margin-bottom: 8px;"
                  :title="generateReport.case_gen.count_note"
                />
                <el-alert
                  v-if="generateReport.naming_warnings?.length"
                  type="warning"
                  :closable="false"
                  show-icon
                  style="margin-bottom: 8px;"
                  :title="`命名槽位告警 ${generateReport.naming_warnings.length} 条`"
                >
                  <ul class="naming-warn-list">
                    <li v-for="(w, i) in generateReport.naming_warnings" :key="i">{{ w }}</li>
                  </ul>
                </el-alert>
                <pre class="report-pre">{{ generateReport.case_gen?.raw_response || '（无返回内容）' }}</pre>
              </el-collapse-item>
            </el-collapse>
          </el-card>

          <!-- 本次生成用例 · 快速审核 -->
          <el-card
            v-if="showEmbedSection('document') && lastSessionCaseIds.length"
            shadow="never"
            class="session-card"
          >
            <template #header>
              <div class="session-header">
                <b>本次生成用例</b>
                <el-tag size="small" type="primary">{{ lastSessionCaseIds.length }} 条</el-tag>
                <el-tag size="small" type="success">已入库 {{ sessionImportedCount }}</el-tag>
                <el-tag size="small" type="warning">待审核 {{ sessionPendingCount }}</el-tag>
                <span v-if="reportMeta.time" class="report-meta">{{ reportMeta.time }}</span>
              </div>
            </template>
            <div class="session-toolbar">
              <el-button
                size="small"
                :type="sessionFilterOnly ? 'primary' : 'default'"
                @click="sessionFilterOnly = !sessionFilterOnly"
              >
                {{ sessionFilterOnly ? '取消「只看本次」' : '在列表中只看本次' }}
              </el-button>
              <el-button
                v-if="canImportLibrary && sessionPendingCount"
                size="small"
                type="success"
                :loading="importingToLibrary"
                @click="handleSessionImportPending"
              >
                批量审核入库 ({{ sessionPendingCount }})
              </el-button>
              <el-select
                v-if="canImportLibrary"
                v-model="importDuplicateMode"
                size="small"
                style="width: 120px"
                title="库中标题+模块重复时的处理方式"
              >
                <el-option label="重复跳过" value="skip" />
                <el-option label="重复覆盖" value="overwrite" />
              </el-select>
              <el-button
                v-if="canImportLibrary && sessionPendingCount"
                size="small"
                @click="selectSessionPending"
              >
                勾选待审核
              </el-button>
            </div>
            <el-table :data="sessionCasePreview" border size="small" max-height="280">
              <el-table-column prop="title" label="用例标题" min-width="220" show-overflow-tooltip />
              <el-table-column prop="module" label="AI功能模块" width="120" show-overflow-tooltip />
              <el-table-column prop="priority" label="优先级" width="72" align="center" />
              <el-table-column label="入库状态" width="100" align="center">
                <template #default="{ row }">
                  <el-tag v-if="isCaseInLibrary(row)" size="small" type="success">已入库</el-tag>
                  <el-tag v-else size="small" type="info">待审核</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="100" fixed="right">
                <template #default="{ row }">
                  <el-button
                    v-if="canImportLibrary && !isCaseInLibrary(row)"
                    link
                    type="primary"
                    :loading="importingOneId === row.id"
                    @click="handleImportOneToLibrary(row.id)"
                  >审核入库</el-button>
                  <span v-else-if="isCaseInLibrary(row)" class="report-meta">×{{ libraryCopyCount(row) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- 用例表格 -->
          <template v-if="showEmbedSection('cases')">
          <el-alert
            v-if="caseList.length"
            type="info"
            :closable="false"
            show-icon
            class="cases-module-hint"
            title="「AI功能模块」来自模型语义拆分（用于标题命名）；导出 XLSX 的「所属产品 / 所属模块 / 相关研发需求」取自上方「禅道导入配置」，二者含义不同。"
          />
          <el-alert
            v-if="caseFilterHint"
            type="info"
            :closable="false"
            show-icon
            class="cases-filter-hint"
          >
            <template #title>筛选说明</template>
            <p class="cases-filter-hint-body">{{ caseFilterHint }}</p>
          </el-alert>
          <div
            class="cases-panel"
            v-loading="casesLoading"
            element-loading-text="正在加载用例…"
          >
          <div class="cases-toolbar">
            <span>
              <template v-if="casesLoading">正在加载用例…</template>
              <template v-else>
                共 {{ caseList.length }} 条用例
                <template v-if="caseFilterSectionId || caseFilterSourceRef || caseFilterPointId || caseFilterLibraryStatus || sessionFilterOnly">
                  （筛选后 {{ filteredCaseList.length }} 条）
                </template>
              </template>
            </span>
            <div class="cases-filters">
              <el-select
                v-model="caseFilterSectionId"
                clearable
                placeholder="按来源章节"
                size="small"
                style="width: 220px;"
              >
                <el-option
                  v-for="s in sectionFilterOptions"
                  :key="s.id"
                  :label="s.label"
                  :value="s.id"
                />
              </el-select>
              <el-select
                v-model="caseFilterSourceRef"
                clearable
                placeholder="按来源批次"
                size="small"
                style="width: 260px;"
              >
                <el-option
                  v-for="o in caseSourceRefOptions"
                  :key="o.value"
                  :label="o.label"
                  :value="o.value"
                />
              </el-select>
              <el-select
                v-model="caseFilterLibraryStatus"
                clearable
                placeholder="入库状态"
                size="small"
                style="width: 120px;"
              >
                <el-option label="待审核" value="pending" />
                <el-option label="已入库" value="imported" />
              </el-select>
              <el-select
                v-if="caseTestPointFilterOptions.length"
                v-model="caseFilterPointId"
                clearable
                placeholder="按测试点"
                size="small"
                style="width: 160px;"
              >
                <el-option
                  v-for="o in caseTestPointFilterOptions"
                  :key="o.value"
                  :label="o.label"
                  :value="o.value"
                />
              </el-select>
              <el-button
                v-if="lastSessionCaseIds.length"
                size="small"
                :type="sessionFilterOnly ? 'primary' : 'default'"
                @click="sessionFilterOnly = !sessionFilterOnly"
              >
                {{ sessionFilterOnly ? '取消本次筛选' : `只看本次 (${lastSessionCaseIds.length})` }}
              </el-button>
            </div>
            <el-select
              v-if="selectedCaseIds.length && canImportLibrary"
              v-model="importDuplicateMode"
              size="small"
              style="width: 120px"
              title="库中标题+模块重复时的处理方式"
            >
              <el-option label="重复跳过" value="skip" />
              <el-option label="重复覆盖" value="overwrite" />
            </el-select>
            <el-button
              v-if="selectedCaseIds.length && canImportLibrary"
              type="primary"
              size="small"
              :loading="importingToLibrary"
              @click="handleImportToLibrary"
            >审核入库 ({{ selectedCaseIds.length }})</el-button>
            <el-button
              v-if="selectedCaseIds.length"
              type="danger"
              size="small"
              @click="handleDeleteCases"
            >删除选中 ({{ selectedCaseIds.length }})</el-button>
          </div>

          <el-table
            :data="flatCaseRows"
            border
            stripe
            max-height="520"
            @selection-change="onCaseSelect"
          >
            <el-table-column type="selection" width="45" :selectable="row => row._isFirstStep" />
            <el-table-column prop="funcModule" label="AI功能模块" width="120" show-overflow-tooltip />
            <el-table-column prop="zentaoModule" label="禅道所属模块" min-width="160" show-overflow-tooltip />
            <el-table-column label="来源" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <template v-if="row._isFirstStep">
                  <div>{{ row.sourceLabel }}</div>
                  <div v-if="row._case?.test_point_ids?.length" class="tp-links">
                    <el-button
                      v-for="pid in row._case.test_point_ids"
                      :key="pid"
                      link
                      type="primary"
                      size="small"
                      @click="goTestAnalysisPoint(pid)"
                    >测试点 #{{ pid }}</el-button>
                  </div>
                </template>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="用例标题" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <template v-if="row._isFirstStep">
                  <span>{{ row.title }}</span>
                </template>
              </template>
            </el-table-column>
            <el-table-column label="入库状态" width="96" align="center">
              <template #default="{ row }">
                <template v-if="row._isFirstStep">
                  <el-tag v-if="isCaseInLibrary(row._case)" size="small" type="success">已入库</el-tag>
                  <el-tag v-else size="small" type="warning">待审核</el-tag>
                </template>
              </template>
            </el-table-column>
            <el-table-column prop="precondition" label="前置条件" min-width="120" show-overflow-tooltip />
            <el-table-column prop="step" label="步骤" min-width="160" show-overflow-tooltip />
            <el-table-column prop="expect" label="预期" min-width="160" show-overflow-tooltip />
            <el-table-column prop="priority" label="优先级" width="80" align="center" />
            <el-table-column prop="type" label="用例类型" width="96" />
            <el-table-column prop="stage" label="适用阶段" width="120" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row._isFirstStep">{{ row.stage }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="168" fixed="right">
              <template #default="{ row }">
                <template v-if="row._isFirstStep">
                  <el-button
                    v-if="canImportLibrary && !isCaseInLibrary(row._case)"
                    link
                    type="success"
                    :loading="importingOneId === row._case.id"
                    @click="handleImportOneToLibrary(row._case.id)"
                  >审核入库</el-button>
                  <el-button link type="primary" @click="openEditCase(row._case)">编辑</el-button>
                  <el-button link type="danger" @click="handleDeleteOneCase(row._case)">删除</el-button>
                </template>
              </template>
            </el-table-column>
          </el-table>
          </div>
          </template>
        </div>
        <div
          v-else-if="embedMode"
          v-loading="true"
          element-loading-text="正在加载需求…"
          class="embed-loading-holder"
        />
      </TestingEmbedShell>

      <!-- 编辑用例 -->
      <el-dialog v-model="editVisible" title="编辑用例" width="760px" destroy-on-close>
        <el-form v-if="editForm" label-width="110px">
          <el-alert
            type="info"
            :closable="false"
            style="margin-bottom: 12px;"
            title="禅道三项在上方「禅道导入配置」统一维护；修改优先级会自动更新适用阶段。下方「AI功能模块」与导出「所属模块」含义不同。"
          />
          <el-form-item label="AI功能模块"><el-input v-model="editForm.module" /></el-form-item>
          <el-form-item label="禅道所属模块">
            <el-input :model-value="resolveCaseZentaoModule(editForm)" disabled />
          </el-form-item>
          <el-form-item label="用例标题"><el-input v-model="editForm.title" /></el-form-item>
          <el-form-item label="前置条件"><el-input v-model="editForm.precondition" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="优先级">
            <el-select v-model="editForm.priority" style="width: 120px;">
              <el-option label="1-高" value="1" /><el-option label="2-中" value="2" />
              <el-option label="3-低" value="3" /><el-option label="4-建议" value="4" />
            </el-select>
          </el-form-item>
          <el-form-item label="用例类型">
            <el-select v-model="editForm.type" style="width: 100%;">
              <el-option v-for="t in ZENTAO_CASE_TYPES" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="适用阶段">
            <el-input :model-value="editForm.stage" disabled style="width: 200px;" />
          </el-form-item>
          <el-form-item label="关键词"><el-input v-model="editForm.keywords" /></el-form-item>
          <el-form-item v-if="editForm.test_point_ids?.length" label="关联测试点">
            <el-button
              v-for="pid in editForm.test_point_ids"
              :key="pid"
              link
              type="primary"
              @click="goTestAnalysisPoint(pid)"
            >#{{ pid }}</el-button>
          </el-form-item>
          <el-form-item label="步骤">
            <div v-for="(st, idx) in editForm.steps" :key="idx" class="step-row">
              <div class="step-block-head">步骤 {{ idx + 1 }}</div>
              <div class="step-field">
                <span class="step-field-label">操作步骤</span>
                <el-input v-model="st.step" type="textarea" :rows="2" placeholder="具体操作（对象 + 动作 + 关键数据）" />
              </div>
              <div class="step-field">
                <span class="step-field-label">预期结果</span>
                <el-input v-model="st.expect" type="textarea" :rows="2" placeholder="该步操作后可观察、可判定的结果" />
              </div>
              <el-button link type="danger" @click="editForm.steps.splice(idx, 1)">删除</el-button>
            </div>
            <el-button size="small" @click="editForm.steps.push({ step: '', expect: '' })">+ 添加步骤</el-button>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="editSaving" @click="saveEditCase">保存</el-button>
        </template>
      </el-dialog>
    </template>
  </PageCard>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import PageCard from '@/components/PageCard.vue'
import TableColumnPicker from '@/components/TableColumnPicker.vue'
import TestingEmbedShell from '@/components/TestingEmbedShell.vue'
import { useCommunityEdition } from '@/composables/useCommunityEdition.js'
import { useTableColumns } from '@/composables/useTableColumns.js'
import { aiRequirementApi, aiConfigApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'
import { ZENTAO_CASE_TYPES } from '@/constants/zentaoCaseTypes.js'
import {
  buildCaseSourceRefOptions,
  caseMatchesSourceFilter,
  caseMatchesSectionFilter,
  summarizePendingBySource,
  formatCaseSourceRefLabel,
  isCaseInLibraryCopy
} from '@/utils/aiCaseSource.js'
import {
  applyPendingSectionProjection,
  computeSectionCoverage
} from '@/utils/sectionCoverage.js'
import KnowledgeRefSelector from '@/modules/knowledge/components/KnowledgeRefSelector.vue'
import { knowledgeApi } from '@/api/modules/knowledge.js'

const props = defineProps({
  embedMode: { type: Boolean, default: false },
  embedReqId: { type: Number, default: null },
  embedSection: { type: String, default: '' },
  highlightPointId: { type: Number, default: null }
})

const showEmbedSection = (name) => {
  if (!props.embedMode || !props.embedSection) return true
  if (props.embedSection === 'document') return name === 'document' || name === 'config'
  if (props.embedSection === 'cases') return name === 'cases'
  if (props.embedSection === 'config') return name === 'config' || name === 'document'
  return true
}

const proStore = ProjectStore()
const uStore = UserStore()
const route = useRoute()
const router = useRouter()
const { isCommunityEdition, loadCommunityEdition } = useCommunityEdition()
const canEditNaming = computed(() => uStore.hasPermission('project:edit'))
const canImportLibrary = computed(() => uStore.hasPermission('ai_test:execute'))
const canDeleteGenerateJob = computed(() => uStore.hasPermission('ai_test:execute'))
const importingToLibrary = ref(false)
const importDuplicateMode = ref('skip')
const importingOneId = ref(null)
const lastSessionCaseIds = ref([])
const sessionFilterOnly = ref(false)

const namingSlotsHelpVisible = ref(false)
const formatNamingSlotVar = (name) => `{{ ${name} }}`
const namingSlotHelpRows = [
  {
    name: 'story_no',
    label: '需求编号',
    source: '禅道「相关研发需求」中提取首部数字',
    example: '3174'
  },
  {
    name: 'main_module',
    label: '主功能模块',
    source: 'AI 生成；缺失时取文档一级章节标题',
    example: '基础资料录入'
  },
  {
    name: 'sub_module',
    label: '子功能模块',
    source: 'AI 生成；缺失时取当前生成范围章节标题',
    example: '原因代码作业'
  },
  {
    name: 'feature_point',
    label: '功能点',
    source: 'AI 为单条用例命名的功能点，同批次勿重复',
    example: '导出功能01'
  },
  {
    name: 'case_description',
    label: '用例描述',
    source: 'AI 描述本条用例的验证点，会拼入最终标题',
    example: '导入成功，已存在失败'
  }
]

/** 上传弹窗：简要说明 */
const uploadUsageTooltip = `
<b>新增需求文档</b><br/>
1. 选择 PDF、Word(.docx)、TXT 或 Markdown 文件并上传。<br/>
2. 上传成功后，在列表点击「用例」进入详情页。<br/>
3. 含截图/流程图的 Word 文档，后续生成时需配置 Vision 模型（如 qwen-vl）。<br/>
4. 更完整的批量生成步骤，请进入详情后点击标题旁 <b>?</b> 查看。
`

/** 详情抽屉：完整使用教程 */
const detailUsageTooltip = `
<b>需求 → 功能用例 · 使用说明</b><br/><br/>
<b>① 禅道配置（必填）</b><br/>
在「禅道导入配置」填写所属产品、所属模块、相关研发需求（禅道后台查准后填写）；可保存到项目级，本需求可覆盖。AI 不生成这三项；适用阶段按优先级自动：1→冒烟，2~4→系统测试。<br/><br/>
<b>② 生成范围</b><br/>
左侧章节树按标题层级展示父子章节；勾选要覆盖的段落，可全选/清空/选未覆盖（仅勾选尚无对应用例的章节，便于补生成）。范围过大时系统会提示缩小勾选。下方「章节覆盖检查」可查看已覆盖/未覆盖节数；右侧队列可拆多批。补缺口：选未覆盖 → 加入队列 → 对该批点「补充」。<br/><br/>
<b>③ 批量队列（推荐大文档）</b><br/>
· 勾选「场景一」等相关章节 → 点「将当前勾选加入队列」<br/>
· 再勾选其他场景重复入队，右侧队列可改批次名、条数、排序<br/>
· 下方「批量生成配置」表格与队列同步，可点章节范围精调、某批自定义禅道<br/><br/>
<b>④ AI 生成</b><br/>
· 填写的条数为<b>参考目标</b>，实际入库可能略多/略少，以报告「参考/实际」为准<br/>
· <b>单次生成</b>：仅对当前树勾选范围生成一批<br/>
· <b>批量生成</b>：按队列逐批调用 AI（每批独立参考条数，不与底部条数相加）<br/>
· 文档含图：请选择 Vision 模型；用例正文选文本模型（如 DeepSeek）<br/>
· 「替换已有」：生成前清空本需求下全部旧用例（单次生成）<br/>
· 「补充本批」：单次生成时按推断批次名读取同批已有用例后追加<br/>
· 批量各批可单独勾选「替换」（删同批旧用例）或「补充」（读同批追加）；「批量前清空」可一次删掉全部旧用例<br/><br/>
<b>⑤ 结果与导出</b><br/>
用例表可按「来源章节」「批次」筛选；查看「AI 生成报告」后编辑并「导出 XLSX」导入禅道。
`

const listLoading = ref(false)
const reqList = ref([])
const uploadVisible = ref(false)
const archiveDialog = ref({
  visible: false,
  loading: false,
  requirementId: null,
  reqName: '',
  folderId: null,
  title: '',
  replaceIfExists: false
})
const archiveFolders = ref([])
const uploading = ref(false)
const uploadForm = reactive({ name: '', file: null })

const {
  activeColumns: reqListActiveColumns,
  pickerItems: reqListPickerItems,
  tableRenderKey: reqListTableKey,
  setColumnVisible: setReqListColumnVisible,
  setPickerOrder: setReqListPickerOrder,
  resetColumns: resetReqListColumns
} = useTableColumns('ai.requirements.list')

const detailVisible = ref(false)
const currentReq = ref(null)
const caseList = ref([])
const casesLoading = ref(false)
const generating = ref(false)
const selectedCaseIds = ref([])
const configList = ref([])

const genForm = reactive({
  vision_config_id: null,
  case_gen_config_id: null,
  count: 15,
  count_mode: 'fixed', // fixed | auto
  replace_existing: false,
  supplement: false,
  extra_instructions: ''
})
const reqCaseSettings = reactive({
  auto_count_enabled_default: false,
  auto_count_min_floor: 4,
  auto_count_max_cap: 30,
  auto_count_min_ratio: 0.7,
  auto_count_max_ratio: 1.5,
  fixed_count_hard_max: 50
})
const fixedCountHardMax = computed(() => Number(reqCaseSettings.fixed_count_hard_max) || 50)
const isAutoCountMode = computed(() => genForm.count_mode === 'auto')
const knowledgeRefs = ref({ folder_ids: [], document_ids: [] })

const projectZentao = reactive({ export_profile: 'zentao', product: '', module: '', related_story: '' })
const reqZentao = reactive({ product: '', module: '', related_story: '' })
const effectiveZentao = reactive({ product: '', module: '', related_story: '' })
const exportProfile = ref('zentao')
const exportProfileOptions = ref([
  { value: 'zentao', label: '禅道 XLSX' },
  { value: 'generic', label: '通用 XLSX' }
])
const savingExportProfile = ref(false)
const suggestedTemplateId = ref('')
const builtinTemplateCatalog = ref([])
const savingProjectZentao = ref(false)
const savingReqZentao = ref(false)

const namingConfig = reactive({ active_template_id: 'default', templates: [] })
const activeNamingTemplate = ref(null)
const namingEditTemplateId = ref('default')
const namingEditTemplate = reactive({
    id: 'default',
    name: '公司默认规范',
    version: 1,
    enabled: true,
    requirement_types: ['*'],
    title_template: '',
    export_columns: []
})
const namingRequirementTypesText = ref('*')
const namingExportColumnsJson = ref('[]')
const reqNamingMeta = reactive({ requirement_type: 'default', naming_template_id: '' })
const namingPreviewSample = reactive({
    story_no: '3174',
    main_module: '基础资料录入',
    sub_module: '原因代码作业',
    feature_point: '导出功能01',
    case_description: '有多余字段时不存在的导入成功，已存在的导入失败'
})
const namingPreviewResult = reactive({ title: '', warnings: [] })
const savingNamingConfig = ref(false)
const savingReqNaming = ref(false)
const namingPreviewLoading = ref(false)
const recalcTitlesLoading = ref(false)
const setActiveOnSave = ref(true)
const exportTemplateName = ref('禅道默认模板')

const docSections = ref([])
const selectedSectionIds = ref([])
const scopeEstimate = ref(null)

const softMinCount = computed(() => Number(scopeEstimate.value?.soft_min_count) || null)
const softMaxCount = computed(() => Number(scopeEstimate.value?.soft_max_count) || null)
const softRangeExplain = computed(() => scopeEstimate.value?.range_explain || '')

const recommendedCaseCount = computed(() => {
  const n = Number(scopeEstimate.value?.recommended_count)
  return Number.isFinite(n) && n > 0 ? n : null
})

const applyRecommendedCount = () => {
  if (!recommendedCaseCount.value) return
  genForm.count = recommendedCaseCount.value
  ElMessage.success(`已采用建议条数 ${recommendedCaseCount.value}`)
}

const resolveCountForNewBatch = () => {
  // 入队优先用当前范围建议条数，避免默认 15 一刀切
  if (recommendedCaseCount.value) return recommendedCaseCount.value
  return genForm.count
}
const sectionTreeRef = ref(null)
const reparsing = ref(false)
const selectingUncovered = ref(false)
const treeSyncing = ref(false)

let batchKeySeq = 0
const batchQueue = ref([])
const activeBatchKey = ref(null)
const batchGenerating = ref(false)
const retryingBatchIndex = ref(null)
const batchProgress = ref(null)
const batchJobProgress = ref(null)
const batchJobId = ref(null)
let batchJobPollTimer = null
const sectionPickerVisible = ref(false)
const sectionPickerTarget = ref(null)
const pickerTreeRef = ref(null)

const batchSuccessCount = computed(() => {
  const list = generateReport.value?.batch_results || []
  return list.filter(b => b.success).length
})

const batchFailCount = computed(() => {
  const list = generateReport.value?.batch_results || []
  return list.filter(b => b && b.success === false).length
})

/** 已有结果的批次数（进行中任务与 done_batches 一致） */
const batchResultsDoneCount = computed(() => generateReport.value?.batch_results?.length || 0)

const caseCountVarianceTag = computed(() => {
  const cg = generateReport.value?.case_gen
  if (!cg || cg.parsed_count == null) return null
  // 批量汇总/混合模式不做单批偏差提示
  if (cg.aggregated || cg.count_mode === 'mixed' || generateReport.value?.batch_mode) return null
  if (cg.count_mode === 'auto') {
    const lo = cg.soft_min_count
    const hi = cg.soft_max_count
    const got = cg.parsed_count
    if (lo != null && got < lo) return { type: 'warning', text: `低于软下限 ${lo}` }
    if (hi != null && got > hi) return { type: 'warning', text: `高于软上限 ${hi}` }
    if (cg.partial_truncated) return { type: 'danger', text: '已截断' }
    return { type: 'success', text: '落在软区间' }
  }
  if (cg.requested_count == null) return null
  const req = cg.requested_count
  const got = cg.parsed_count
  if (got === req) return { type: 'success', text: '与参考一致' }
  if (got < req) return { type: 'warning', text: `少 ${req - got} 条` }
  return { type: 'info', text: `多 ${got - req} 条` }
})

/** 批量进行中时 job.generate_report 尚未汇总，回退取最近一批的 case_gen */
const pickCaseGenFromReport = (gr, batchResults = []) => {
  if (gr?.case_gen) return gr.case_gen
  const batches = batchResults || []
  for (let i = batches.length - 1; i >= 0; i -= 1) {
    const cg = batches[i]?.generate_report?.case_gen
    if (cg) return cg
  }
  return null
}

const batchQueueImageCount = computed(() => {
  let n = 0
  const seen = new Set()
  for (const item of batchQueue.value) {
    for (const sid of item.scope_section_ids || []) {
      const sec = docSections.value.find(s => s.id === sid)
      for (const idx of sec?.image_indices || []) {
        if (!seen.has(idx)) {
          seen.add(idx)
          n += 1
        }
      }
    }
  }
  return n
})

const buildSectionTree = (sections) => {
  if (!sections?.length) return []
  const nodes = new Map()
  for (const s of sections) {
    nodes.set(s.id, {
      id: s.id,
      label: `${s.title}（约 ${s.char_count || 0} 字${s.image_indices?.length ? ` · ${s.image_indices.length} 图` : ''}）`,
      children: [],
      title: s.title
    })
  }
  const roots = []
  for (const s of sections) {
    const node = nodes.get(s.id)
    const pid = s.parent_id
    if (pid && nodes.has(pid)) {
      nodes.get(pid).children.push(node)
    } else {
      roots.push(node)
    }
  }
  return roots
}

/** 某 id 是否为另一章节的祖先 */
const isSectionAncestor = (sections, ancestorId, descId) => {
  const byId = new Map(sections.map(s => [s.id, s]))
  let cur = byId.get(descId)
  while (cur?.parent_id) {
    if (cur.parent_id === ancestorId) return true
    cur = byId.get(cur.parent_id)
  }
  return false
}

/** 去掉被其它未覆盖节包含的祖先 id，避免 el-tree 级联勾选整棵子树 */
const leafOnlySectionIds = (sections, ids) => {
  const arr = [...new Set((ids || []).filter(Boolean))]
  return arr.filter(id => !arr.some(other => other !== id && isSectionAncestor(sections, id, other)))
}

const sectionTreeData = computed(() => buildSectionTree(docSections.value))

const sectionCoverage = ref(null)
const showCoverageCard = computed(() => {
  if (!sectionCoverage.value?.total) return false
  if (props.embedMode && props.embedSection === 'cases' && casesLoading.value) return false
  return true
})
const caseFilterSectionId = ref('')
const caseFilterSourceRef = ref('')
const caseFilterLibraryStatus = ref('')
const caseFilterPointId = ref(null)
const batchZentaoVisible = ref(false)
const batchZentaoForm = ref(null)

const pendingQueueSectionIds = computed(() => {
  const ids = new Set()
  for (const item of batchQueue.value) {
    for (const sid of item.scope_section_ids || []) ids.add(sid)
  }
  return [...ids]
})

const coverageSummary = computed(() => {
  const c = sectionCoverage.value
  if (!c?.total) return ''
  let text = `已覆盖 ${c.covered_count}/${c.total} 节`
  if (c.projected_covered_count != null && pendingQueueSectionIds.value.length) {
    text += ` · 队列执行后预计 ${c.projected_covered_count}/${c.total}`
  }
  return text
})

const coverageTagType = computed(() => {
  const c = sectionCoverage.value
  if (!c?.total) return 'info'
  const uncovered = c.projected_uncovered_count ?? c.uncovered_count
  if (uncovered === 0) return 'success'
  if (uncovered <= Math.max(1, Math.floor(c.total * 0.3))) return 'warning'
  return 'danger'
})

const scopedImageCount = computed(() => {
  let n = 0
  for (const sid of selectedSectionIds.value) {
    const sec = docSections.value.find(s => s.id === sid)
    if (sec?.image_indices?.length) n += sec.image_indices.length
  }
  return n
})

const zentaoBindingsReady = computed(() => {
  const e = effectiveZentao
  return !!(e.product?.trim() && e.module?.trim() && e.related_story?.trim())
})

const exportBindingsReady = computed(() => {
  if (exportProfile.value === 'generic') return true
  return zentaoBindingsReady.value
})

const exportProfileLabel = computed(() => {
  const opt = exportProfileOptions.value.find(o => o.value === exportProfile.value)
  return opt?.label || '禅道 XLSX'
})

const suggestedTemplateName = computed(() => {
  const tpl = namingConfig.templates.find(t => t.id === suggestedTemplateId.value)
  if (tpl?.name) return tpl.name
  const cat = builtinTemplateCatalog.value.find(t => t.id === suggestedTemplateId.value)
  return cat?.name || suggestedTemplateId.value
})

const formatNamingTemplateOption = (tpl) => {
  if (!tpl) return ''
  const cat = builtinTemplateCatalog.value.find(c => c.id === tpl.id)
  return cat?.description ? `${tpl.name} — ${cat.description}` : tpl.name
}

const editVisible = ref(false)
const editForm = ref(null)
const editSaving = ref(false)

function normalizeCaseSteps(steps) {
  if (!Array.isArray(steps) || !steps.length) return [{ step: '', expect: '' }]
  return steps.map((st) => {
    if (typeof st === 'string') return { step: st, expect: '' }
    if (!st || typeof st !== 'object') return { step: '', expect: '' }
    return {
      step: st.step || st.action || st['步骤'] || st['操作'] || '',
      expect: st.expect || st.expected || st['预期'] || st['期望'] || ''
    }
  })
}

const generateReport = ref(null)
const reportMeta = ref({})
const generateJobHistory = ref([])
const selectedReportJobId = ref(null)
const reportCollapse = ref([])

/** 启发式：是否更适合读图（仅用于选项标注，不限制下拉） */
function isLikelyVisionModel(c) {
  const model = (c.model || '').toLowerCase()
  return /vl|vision|gpt-4o|gpt-4-turbo|qvq|gemini|claude-3/.test(model)
}

const enabledConfigs = computed(() =>
  configList.value.filter(c => c.is_enabled !== false)
)

function configOptionLabel(c) {
  const tag = isLikelyVisionModel(c) ? ' · 推荐读图' : ''
  return `${c.name} (${c.model})${tag}`
}

const sectionTitleById = (id) =>
  docSections.value.find(s => s.id === id)?.title || id

/** 禅道所属模块：优先后端快照，旧数据回退到当前禅道配置 */
function resolveCaseZentaoModule(c) {
  if (!c) return '—'
  const fromCase = (c.zentao_module || c.extra?.zentao_module || '').trim()
  if (fromCase) return fromCase
  return (effectiveZentao.module || '').trim() || '—'
}

const caseSourceLabel = (c) => {
  const parts = []
  const ids = c.section_ids || []
  if (ids.length) {
    const titles = ids.slice(0, 2).map(sectionTitleById)
    parts.push(
      titles.length < ids.length ? `${titles.join('、')} 等${ids.length}节` : titles.join('、')
    )
  }
  if (c.source_ref) {
    parts.push(formatCaseSourceRefLabel(c.source_ref))
  }
  return parts.length ? parts.join(' · ') : '-'
}

const caseSourceRefOptions = computed(() =>
  buildCaseSourceRefOptions(caseList.value, {
    withCounts: true,
    libraryStatus: caseFilterLibraryStatus.value
  })
)

const sectionFilterOptions = computed(() => {
  const sections = docSections.value || []
  const pool = caseList.value
  return sections.map(s => {
    const n = pool.filter(c =>
      caseMatchesSectionFilter(c.section_ids, s.id, sections)
    ).length
    return {
      id: s.id,
      label: n > 0 ? `${s.title}（${n}）` : s.title
    }
  })
})

const pendingSourceSummary = computed(() => summarizePendingBySource(caseList.value))

const caseFilterHint = computed(() => {
  if (!caseList.value.length) return ''
  const parts = []
  const ps = pendingSourceSummary.value
  if (ps.total > 0) {
    const details = []
    if (ps.doc) details.push(`文档批次 ${ps.doc}`)
    if (ps.unlabeled) details.push(`未标注批次 ${ps.unlabeled}`)
    if (ps.testPoints) details.push(`测试点 ${ps.testPoints}`)
    parts.push(
      details.length
        ? `待审核共 ${ps.total} 条（${details.join(' · ')}）。`
        : `待审核共 ${ps.total} 条。`
    )
  }
  parts.push(
    '「待审核」= 尚未复制到功能用例库；「来源批次」仅统计带批次名的用例（批量队列或单次生成会自动命名）；「来源章节」含所选节及其子节。多个筛选项同时生效（取交集）。'
  )
  if (
    caseFilterLibraryStatus.value === 'pending' &&
    (caseFilterSourceRef.value || caseFilterSectionId.value) &&
    filteredCaseList.value.length < ps.total
  ) {
    parts.push(
      `当前组合筛选 ${filteredCaseList.value.length} 条，少于全部待审核 ${ps.total} 条，可清空批次/章节或选「未标注批次」查看其余。`
    )
  }
  return parts.join('')
})

const caseTestPointFilterOptions = computed(() => {
  const map = new Map()
  for (const c of caseList.value) {
    for (const pid of c.test_point_ids || []) {
      if (!map.has(pid)) map.set(pid, 0)
      map.set(pid, map.get(pid) + 1)
    }
  }
  return [...map.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([id, n]) => ({ value: id, label: `测试点 #${id}（${n} 条用例）` }))
})

const isCaseInLibrary = (c) => isCaseInLibraryCopy(c)
const libraryCopyCount = (c) => (c?.extra?.library_copies?.length) || 0

const syncSessionFromReport = (report, fallbackCases = null, { autoFilter = true } = {}) => {
  let ids = report?.created_case_ids
  if ((!ids || !ids.length) && Array.isArray(fallbackCases) && fallbackCases.length) {
    ids = fallbackCases.map(c => c.id).filter(Boolean)
  }
  if (!ids?.length) return
  const idSet = new Set(ids)
  const matched = caseList.value.filter(c => idSet.has(c.id)).map(c => c.id)
  if (!matched.length) return
  lastSessionCaseIds.value = [...new Set(matched)]
  if (autoFilter) sessionFilterOnly.value = true
}

const sessionCases = computed(() => {
  if (!lastSessionCaseIds.value.length) return []
  const idSet = new Set(lastSessionCaseIds.value)
  return caseList.value.filter(c => idSet.has(c.id))
})

const sessionCasePreview = computed(() => sessionCases.value.slice(0, 50))

const sessionImportedCount = computed(() =>
  sessionCases.value.filter(c => isCaseInLibrary(c)).length
)

const sessionPendingCount = computed(() =>
  sessionCases.value.filter(c => !isCaseInLibrary(c)).length
)

const filteredCaseList = computed(() => {
  let list = caseList.value
  if (sessionFilterOnly.value && lastSessionCaseIds.value.length) {
    const idSet = new Set(lastSessionCaseIds.value)
    list = list.filter(c => idSet.has(c.id))
  }
  if (caseFilterSectionId.value) {
    list = list.filter(c =>
      caseMatchesSectionFilter(c.section_ids, caseFilterSectionId.value, docSections.value)
    )
  }
  list = list.filter(c =>
    caseMatchesSourceFilter(c, caseFilterSourceRef.value, caseFilterPointId.value)
  )
  if (caseFilterLibraryStatus.value === 'pending') {
    list = list.filter(c => !isCaseInLibrary(c))
  } else if (caseFilterLibraryStatus.value === 'imported') {
    list = list.filter(c => isCaseInLibrary(c))
  }
  return list
})

const flatCaseRows = computed(() => {
  const rows = []
  for (const c of filteredCaseList.value) {
    const steps = normalizeCaseSteps(c.steps?.length ? c.steps : [{ step: '', expect: '' }])
    steps.forEach((st, i) => {
      rows.push({
        _case: c,
        _caseId: c.id,
        _isFirstStep: i === 0,
        product: i === 0 ? c.product : '',
        funcModule: i === 0 ? c.module : '',
        zentaoModule: i === 0 ? resolveCaseZentaoModule(c) : '',
        related_story: i === 0 ? c.related_story : '',
        title: i === 0 ? c.title : '',
        precondition: i === 0 ? c.precondition : '',
        priority: i === 0 ? c.priority : '',
        type: i === 0 ? c.type : '',
        stage: i === 0 ? c.stage : '',
        sourceLabel: i === 0 ? caseSourceLabel(c) : '',
        step: st.step,
        expect: st.expect
      })
    })
  }
  return rows
})

const statusLabel = (s) => ({ parsed: '已解析', pending: '待处理', failed: '失败' }[s] || s)

const visionStatusType = computed(() => {
  const v = generateReport.value?.vision
  if (!v || v.skipped) return 'info'
  if (v.success) return 'success'
  if (v.partial) return 'warning'
  if ((v.ok_count || 0) > 0) return 'warning'
  return 'danger'
})

const visionStatusText = computed(() => {
  const v = generateReport.value?.vision
  if (!v) return '-'
  if (v.skipped) return '已跳过'
  if (v.success) return '全部成功'
  if (v.partial) return '部分成功'
  if ((v.ok_count || 0) > 0) return '部分成功'
  return '全部失败'
})

const caseGenStatusType = computed(() => {
  const cg = generateReport.value?.case_gen
  if (generateReport.value?.in_progress && !cg) return 'warning'
  if (!cg) return 'info'
  return cg.success ? 'success' : 'danger'
})

const caseGenStatusText = computed(() => {
  const cg = generateReport.value?.case_gen
  if (generateReport.value?.in_progress && !cg) return '执行中'
  if (!cg) return '暂无'
  return cg.success ? '解析成功' : '解析失败'
})

const applyGenerateReport = (report, meta = {}, fallbackCases = null, opts = {}) => {
  const r = report ? { ...report, in_progress: false } : null
  generateReport.value = r
  reportMeta.value = meta || {}
  if (opts.syncSession) {
    syncSessionFromReport(r, fallbackCases, { autoFilter: opts.autoFilterSession !== false })
  }
  // 默认全部收起；批量模式仅展开「批量执行」摘要
  reportCollapse.value = r?.batch_mode ? ['batch'] : []
}

const formatJobTime = (job) => {
  const raw = job?.finish_time || job?.create_time
  if (!raw) return ''
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return String(raw)
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
}

const jobHistoryLabel = (job) => {
  const time = formatJobTime(job)
  const batches = (job.total_batches || 0) > 1 ? `${job.total_batches}批` : '单批'
  const count = job.case_count ?? job.generate_report?.created_case_ids?.length ?? 0
  let status = `${count}条`
  if (job.status === 'running' || job.status === 'pending') status = '执行中'
  else if (job.status === 'failed') status = '失败'
  return `#${job.id} · ${time || '—'} · ${batches} · ${status}`
}

const applyGenerateJobRecord = (job) => {
  if (!job) return
  selectedReportJobId.value = job.id
  applyGenerateReport(
    {
      ...(job.generate_report || {}),
      job_id: job.id
    },
    {
      time: formatJobTime(job),
      duration_ms: job.duration_ms,
      tokens_used: job.tokens_used
    }
  )
}

const loadGenerateJobHistory = async (reqId) => {
  if (!reqId || !proStore.projectInfo?.id) {
    generateJobHistory.value = []
    return
  }
  try {
    const res = await aiRequirementApi.listGenerateJobs(reqId, proStore.projectInfo.id, {
      page: 1,
      size: 50
    })
    if (res.data?.code === 200) {
      generateJobHistory.value = res.data.data?.list || []
    }
  } catch (_) {
    generateJobHistory.value = []
  }
}

const refreshGenerateJobAfterSave = async (reqId, jobId) => {
  if (!reqId) return
  await loadGenerateJobHistory(reqId)
  if (jobId) {
    const job = generateJobHistory.value.find(j => j.id === jobId)
    if (job) applyGenerateJobRecord(job)
    else selectedReportJobId.value = jobId
  } else if (generateJobHistory.value.length) {
    applyGenerateJobRecord(generateJobHistory.value[0])
  }
}

const onSelectGenerateJob = (jobId) => {
  const job = generateJobHistory.value.find(j => j.id === jobId)
  if (!job) return
  if (job.status === 'running' || job.status === 'pending') {
    selectedReportJobId.value = job.id
    syncGenerateReportFromJob(job)
    if (batchJobId.value !== job.id) startBatchJobPolling(job.id)
    return
  }
  applyGenerateJobRecord(job)
}

const deleteGenerateJobRecord = async () => {
  const jobId = selectedReportJobId.value
  if (!jobId || !currentReq.value) return
  const job = generateJobHistory.value.find(j => j.id === jobId)
  if (job?.status === 'running' || job?.status === 'pending') {
    ElMessage.warning('任务执行中，无法删除')
    return
  }
  try {
    await ElMessageBox.confirm('仅删除生成记录，已生成的用例不会删除。确定继续？', '删除记录', {
      type: 'warning'
    })
    const res = await aiRequirementApi.deleteGenerateJob(jobId, proStore.projectInfo.id)
    if (res.data?.code === 200) {
      ElMessage.success('已删除')
      await loadGenerateJobHistory(currentReq.value.id)
      if (generateJobHistory.value.length) {
        applyGenerateJobRecord(generateJobHistory.value[0])
      } else {
        selectedReportJobId.value = null
        generateReport.value = null
        reportMeta.value = {}
      }
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(apiErrorMsg(e, '删除失败'))
  }
}

/** 新批量任务开始：清空上次 last_generate，避免误显示「2/3 成功」 */
const initInProgressBatchReport = (totalBatches, jobId = null) => {
  generateReport.value = {
    batch_mode: true,
    in_progress: true,
    total_batches: totalBatches,
    job_id: jobId,
    batch_results: [],
    vision: null,
    case_gen: null
  }
  reportMeta.value = {
    time: jobId ? `任务 #${jobId} 执行中` : '任务提交中…',
    duration_ms: null,
    tokens_used: 0
  }
  reportCollapse.value = ['batch']
}

/** 轮询时同步当前任务的批次结果（仅展示本 job，不用 last_generate） */
const syncGenerateReportFromJob = (job) => {
  if (!job || !['pending', 'running'].includes(job.status)) return
  const br = job.batch_results || []
  const gr = job.generate_report || {}
  generateReport.value = {
    batch_mode: true,
    in_progress: true,
    total_batches: job.total_batches || generateReport.value?.total_batches || 0,
    job_id: job.id,
    batch_results: br,
    vision: gr.vision || null,
    case_gen: pickCaseGenFromReport(gr, br),
    tokens_used: job.tokens_used
  }
  reportMeta.value = {
    time: `任务 #${job.id} 执行中${job.current_batch_name ? ` · ${job.current_batch_name}` : ''}`,
    duration_ms: null,
    tokens_used: job.tokens_used || 0
  }
  reportCollapse.value = ['batch']
}

const batchSectionSummary = (ids) => {
  if (!ids?.length) return '未选择章节'
  const titles = ids
    .map(id => docSections.value.find(s => s.id === id)?.title)
    .filter(Boolean)
  if (!titles.length) return `${ids.length} 节`
  if (titles.length <= 2) return titles.join('、')
  return `${titles[0]} 等 ${titles.length} 节`
}

/** 生成报告批次表：优先用记录内章节标题，兼容旧数据嵌套 scope */
const batchReportSectionSummary = (row) => {
  const titles = row?.scope_section_titles?.length
    ? row.scope_section_titles
    : (row?.generate_report?.scope?.section_titles || [])
  if (titles.length) {
    const clean = titles.map(t => (t || '').trim()).filter(Boolean)
    if (!clean.length) return '—'
    if (clean.length <= 2) return clean.join('、')
    return `${clean[0]} 等 ${clean.length} 节`
  }
  const ids = row?.scope_section_ids?.length
    ? row.scope_section_ids
    : (row?.generate_report?.scope?.section_ids || [])
  if (!ids.length) return '—'
  return batchSectionSummary(ids)
}

const inferBatchName = (ids) => {
  const first = docSections.value.find(s => s.id === ids[0])
  const t = (first?.title || '').trim()
  return t ? t.slice(0, 40) : `批次${batchQueue.value.length + 1}`
}

const batchSourceRef = (name) => {
  const n = (name || '').trim()
  return n ? `batch:${n}` : ''
}

const knowledgeRefsPayload = () => {
  const folderIds = (knowledgeRefs.value?.folder_ids || []).filter(Boolean)
  const docIds = (knowledgeRefs.value?.document_ids || []).filter(Boolean)
  if (!folderIds.length && !docIds.length) return {}
  return {
    knowledge_folder_ids: folderIds.length ? folderIds : undefined,
    knowledge_document_ids: docIds.length ? docIds : undefined
  }
}

const countCasesForBatch = (name) => {
  const ref = batchSourceRef(name)
  if (!ref) return 0
  return caseList.value.filter(c => c.source_ref === ref).length
}

const onSingleGenReplaceChange = (val) => {
  if (val) genForm.supplement = false
}

const onSingleGenSupplementChange = (val) => {
  if (val) genForm.replace_existing = false
}

const onBatchReplaceChange = (row, val) => {
  if (val) row.supplement = false
}

const onBatchSupplementChange = (row, val) => {
  if (val) row.replace = false
}

const buildGeneratePayload = (row, { supplement = false } = {}) => {
  const batchName = (row.name || '').trim()
  const mode = row.count_mode === 'auto' ? 'auto' : 'fixed'
  const payload = {
    count_mode: mode,
    count: mode === 'auto' ? undefined : (row.count ?? row.requested_count ?? genForm.count),
    replace_existing: false,
    batch_name: batchName || undefined,
    case_gen_config_id: genForm.case_gen_config_id || undefined,
    vision_config_id: genForm.vision_config_id || undefined,
    scope_section_ids: row.scope_section_ids,
    supplement_batch_name: supplement ? batchName : undefined,
    extra_instructions: (genForm.extra_instructions || '').trim() || undefined
  }
  Object.assign(payload, knowledgeRefsPayload())
  const hasBatchZentao =
    row.useCustomZentao ||
    (row.product?.trim() && row.module?.trim() && row.related_story?.trim())
  if (hasBatchZentao) {
    payload.export_defaults = {
      product: row.product?.trim() || effectiveZentao.product,
      module: row.module?.trim() || effectiveZentao.module,
      related_story: row.related_story?.trim() || effectiveZentao.related_story
    }
  }
  return payload
}

const createBatchItem = (scopeIds, name = '', count = null) => ({
  _key: ++batchKeySeq,
  name: name || inferBatchName(scopeIds),
  scope_section_ids: [...scopeIds],
  count: count ?? resolveCountForNewBatch(),
  count_mode: genForm.count_mode || 'fixed',
  supplement: false,
  replace: false,
  useCustomZentao: false,
  product: '',
  module: '',
  related_story: ''
})

const addToBatchQueue = async () => {
  if (!selectedSectionIds.value.length) {
    ElMessage.warning('请先在左侧勾选章节')
    return
  }
  if (!scopeEstimate.value?.recommended_count) {
    await refreshScopeEstimate()
  }
  const count = resolveCountForNewBatch()
  genForm.count = count
  const item = createBatchItem(selectedSectionIds.value, '', count)
  batchQueue.value.push(item)
  activeBatchKey.value = item._key
  refreshSectionCoverage()
  const tip = recommendedCaseCount.value
    ? `（建议条数 ${count}）`
    : `（条数 ${count}）`
  ElMessage.success(`已加入队列：${item.name}${tip}`)
}

const addEmptyBatchRow = () => {
  const ids = selectedSectionIds.value.length
    ? [...selectedSectionIds.value]
    : docSections.value.slice(0, 1).map(s => s.id)
  if (!ids.length) {
    ElMessage.warning('文档无章节，无法新增批次')
    return
  }
  batchQueue.value.push(createBatchItem(ids))
}

const removeBatchItem = (idx) => {
  const removed = batchQueue.value[idx]
  batchQueue.value.splice(idx, 1)
  if (activeBatchKey.value === removed?._key) {
    activeBatchKey.value = batchQueue.value[0]?._key || null
  }
  refreshSectionCoverage()
}

watch(batchQueue, () => refreshSectionCoverage(), { deep: true })

const moveBatchItem = (idx, delta) => {
  const next = idx + delta
  if (next < 0 || next >= batchQueue.value.length) return
  const arr = [...batchQueue.value]
  const [item] = arr.splice(idx, 1)
  arr.splice(next, 0, item)
  batchQueue.value = arr
}

const clearBatchQueue = () => {
  batchQueue.value = []
  activeBatchKey.value = null
  batchProgress.value = null
  refreshSectionCoverage()
}

const openSectionPicker = (row) => {
  sectionPickerTarget.value = row
  sectionPickerVisible.value = true
  nextTick(() => {
    syncTreeCheckedKeys(pickerTreeRef.value, row.scope_section_ids || [])
  })
}

const confirmSectionPicker = () => {
  const row = sectionPickerTarget.value
  if (!row) {
    sectionPickerVisible.value = false
    return
  }
  const keys = getExplicitCheckedSectionIds(pickerTreeRef.value)
  if (!keys.length) {
    ElMessage.warning('请至少选择一个章节')
    return
  }
  row.scope_section_ids = keys
  if (!row.name || row.name.startsWith('批次')) {
    row.name = inferBatchName(keys)
  }
  sectionPickerVisible.value = false
}

const ensureProject = () => {
  if (!proStore.projectInfo?.id) {
    ElMessage.warning('请先在顶部导航栏选择项目')
    return false
  }
  return true
}

const apiErrorMsg = (e, fallback = '操作失败') =>
  e?.response?.data?.detail || e?.data?.detail || e.message || fallback

const loadExportTemplate = async () => {
  try {
    const res = await aiRequirementApi.getExportTemplate()
    if (res.data?.code === 200) {
      exportTemplateName.value = res.data.data?.name || '禅道默认模板'
    }
  } catch (e) {
    console.error(e)
  }
}

const loadDocumentStructure = async ({ lightweight = false } = {}) => {
  if (!currentReq.value?.id || !proStore.projectInfo?.id) return
  try {
    const res = await aiRequirementApi.getDocumentStructure(
      currentReq.value.id,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      docSections.value = res.data.data?.sections || []
      if (lightweight) {
        refreshSectionCoverage()
        return
      }
      const ids = docSections.value.map(s => s.id)
      selectedSectionIds.value = [...ids]
      await syncTreeCheckedKeys(sectionTreeRef.value, ids)
      scopeEstimate.value = res.data.data?.estimate_all || null
      if (ids.length) await refreshScopeEstimate()
      refreshSectionCoverage()
    }
  } catch (e) {
    console.error(e)
  }
}

const refreshScopeEstimate = async () => {
  if (!currentReq.value?.id || !selectedSectionIds.value.length) {
    scopeEstimate.value = null
    return
  }
  try {
    const res = await aiRequirementApi.estimateScope(
      currentReq.value.id,
      { scope_section_ids: selectedSectionIds.value },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      scopeEstimate.value = res.data.data
    }
  } catch (e) {
    console.error(e)
  }
}

const refreshSectionCoverage = async () => {
  if (!currentReq.value?.id || !proStore.projectInfo?.id || !docSections.value.length) {
    sectionCoverage.value = null
    return
  }
  const pending = pendingQueueSectionIds.value
  if (!pending.length) {
    sectionCoverage.value = computeSectionCoverage(docSections.value, caseList.value)
    return
  }
  try {
    const res = await aiRequirementApi.getSectionCoverage(
      currentReq.value.id,
      proStore.projectInfo.id,
      pending.length ? pending : null
    )
    if (res.data?.code === 200) {
      sectionCoverage.value = res.data.data
    }
  } catch (e) {
    console.error(e)
    sectionCoverage.value = applyPendingSectionProjection(
      computeSectionCoverage(docSections.value, caseList.value),
      docSections.value,
      pending
    )
  }
}

/** 仅取明确勾选的节点，不含半选父节点（半选父节点会把整章内容误带入） */
const getExplicitCheckedSectionIds = (tree) => {
  if (!tree) return []
  return [...new Set(tree.getCheckedKeys(false) || [])]
}

/** 同步树勾选；默认 leafOnly 避免祖先节点级联误勾选子树；全选时传 allNodes */
const syncTreeCheckedKeys = async (tree, keys, { allNodes = false } = {}) => {
  if (!tree) return
  treeSyncing.value = true
  try {
    const sections = docSections.value || []
    const idSet = allNodes
      ? new Set((keys || []).filter(Boolean))
      : new Set(leafOnlySectionIds(sections, keys || []))
    for (const s of sections) {
      tree.setChecked(s.id, idSet.has(s.id), false)
    }
    await nextTick()
  } finally {
    treeSyncing.value = false
  }
}

const onSectionCheck = () => {
  if (treeSyncing.value) return
  const tree = sectionTreeRef.value
  if (!tree) return
  selectedSectionIds.value = getExplicitCheckedSectionIds(tree)
  refreshScopeEstimate()
  refreshSectionCoverage()
}

const openBatchZentaoDialog = (row) => {
  batchZentaoForm.value = row
  row.useCustomZentao = true
  batchZentaoVisible.value = true
}

const syncBatchZentaoFrom = (source) => {
  const row = batchZentaoForm.value
  if (!row) return
  const src = source === 'project' ? projectZentao : effectiveZentao
  row.product = src.product || ''
  row.module = src.module || ''
  row.related_story = src.related_story || ''
  row.useCustomZentao = true
  ElMessage.success(source === 'project' ? '已填入项目禅道配置' : '已填入当前需求生效配置')
}

const saveBatchZentaoDialog = () => {
  const row = batchZentaoForm.value
  if (row) {
    const ok = row.product?.trim() && row.module?.trim() && row.related_story?.trim()
    if (!ok) {
      ElMessage.warning('请填写完整禅道三项，或使用上方同步按钮')
      return
    }
    row.useCustomZentao = true
  }
  batchZentaoVisible.value = false
}

const selectAllSections = async () => {
  const ids = docSections.value.map(s => s.id)
  selectedSectionIds.value = ids
  await syncTreeCheckedKeys(sectionTreeRef.value, ids, { allNodes: true })
  refreshScopeEstimate()
}

const clearSectionSelection = async () => {
  selectedSectionIds.value = []
  await syncTreeCheckedKeys(sectionTreeRef.value, [])
  scopeEstimate.value = null
}

const selectUncoveredSections = async () => {
  if (!docSections.value.length) return
  selectingUncovered.value = true
  try {
    await refreshSectionCoverage()
    const uncovered = sectionCoverage.value?.uncovered_sections || []
    if (!uncovered.length) {
      ElMessage.info('所有章节均已覆盖，无需补充')
      return
    }
    const ids = leafOnlySectionIds(
      docSections.value,
      uncovered.map(s => s.id).filter(Boolean)
    )
    if (!ids.length) {
      ElMessage.info('所有章节均已覆盖，无需补充')
      return
    }
    selectedSectionIds.value = ids
    await syncTreeCheckedKeys(sectionTreeRef.value, ids)
    await refreshScopeEstimate()
    ElMessage.success(`已勾选 ${ids.length} 个未覆盖章节`)
  } finally {
    selectingUncovered.value = false
  }
}

const handleReparseDocument = async () => {
  if (!currentReq.value || !ensureProject()) return
  reparsing.value = true
  try {
    const res = await aiRequirementApi.reparseDocument(
      currentReq.value.id,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '重新解析成功')
      currentReq.value = { ...currentReq.value, ...res.data.data }
      await loadDocumentStructure()
      await loadList()
    } else {
      ElMessage.error(res.data?.message || '重新解析失败')
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '重新解析失败'))
  } finally {
    reparsing.value = false
  }
}

const loadZentaoBindings = async () => {
  if (!proStore.projectInfo?.id) return
  try {
    const res = await aiRequirementApi.getZentaoBindings(
      proStore.projectInfo.id,
      currentReq.value?.id
    )
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      Object.assign(projectZentao, {
        export_profile: 'zentao',
        product: '',
        module: '',
        related_story: '',
        ...(d.project || {})
      })
      exportProfile.value = d.export_profile || projectZentao.export_profile || 'zentao'
      if (Array.isArray(d.export_profile_options) && d.export_profile_options.length) {
        exportProfileOptions.value = d.export_profile_options
      }
      Object.assign(reqZentao, {
        product: '',
        module: '',
        related_story: '',
        ...(d.requirement || {})
      })
      Object.assign(effectiveZentao, d.effective || {})
    }
  } catch (e) {
    console.error(e)
  }
}

const syncNamingEditTemplate = (tpl) => {
  if (!tpl) return
  Object.assign(namingEditTemplate, {
    id: tpl.id,
    name: tpl.name,
    version: tpl.version,
    enabled: tpl.enabled !== false,
    requirement_types: tpl.requirement_types || ['*'],
    title_template: tpl.title_template || '',
    export_columns: tpl.export_columns || []
  })
  namingEditTemplateId.value = tpl.id
  namingRequirementTypesText.value = (tpl.requirement_types || ['*']).join(', ')
  try {
    namingExportColumnsJson.value = JSON.stringify(tpl.export_columns || [], null, 2)
  } catch {
    namingExportColumnsJson.value = '[]'
  }
}

const loadCaseNaming = async () => {
  if (!proStore.projectInfo?.id) return
  try {
    const res = await aiRequirementApi.getCaseNaming(
      proStore.projectInfo.id,
      currentReq.value?.id
    )
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      const cfg = d.config || { active_template_id: 'default', templates: [] }
      namingConfig.active_template_id = cfg.active_template_id || 'default'
      namingConfig.templates = cfg.templates || []
      activeNamingTemplate.value = d.active_template || null
      exportProfile.value = d.export_profile || exportProfile.value
      suggestedTemplateId.value = d.suggested_template_id || ''
      builtinTemplateCatalog.value = d.builtin_templates || []
      reqNamingMeta.requirement_type = d.requirement_type || currentReq.value?.requirement_type || 'default'
      reqNamingMeta.naming_template_id = d.naming_template_id || currentReq.value?.naming_template_id || ''
      const editId = namingConfig.active_template_id || activeNamingTemplate.value?.id || 'default'
      const tpl = namingConfig.templates.find(t => t.id === editId) || activeNamingTemplate.value
      syncNamingEditTemplate(tpl)
    }
  } catch (e) {
    console.error(e)
  }
}

const onNamingTemplateSelect = (id) => {
  const tpl = namingConfig.templates.find(t => t.id === id)
  syncNamingEditTemplate(tpl)
}

const addNamingTemplate = () => {
  const id = `tpl_${Date.now()}`
  namingConfig.templates.push({
    id,
    name: '新模板',
    version: 1,
    enabled: true,
    requirement_types: ['*'],
    title_template: '【#{{ story_no }}_{{ main_module }}_{{ sub_module }}】（{{ feature_point }}）{{ case_description }}',
    export_columns: []
  })
  syncNamingEditTemplate(namingConfig.templates[namingConfig.templates.length - 1])
}

const removeNamingTemplate = () => {
  const idx = namingConfig.templates.findIndex(t => t.id === namingEditTemplateId.value)
  if (idx < 0 || namingConfig.templates.length <= 1) return
  namingConfig.templates.splice(idx, 1)
  syncNamingEditTemplate(namingConfig.templates[0])
}

const buildNamingConfigPayload = () => {
  const types = namingRequirementTypesText.value
    .split(/[,，]/)
    .map(s => s.trim())
    .filter(Boolean)
  let exportColumns = []
  try {
    exportColumns = JSON.parse(namingExportColumnsJson.value || '[]')
  } catch {
    throw new Error('导出列映射 JSON 格式不正确')
  }
  const idx = namingConfig.templates.findIndex(t => t.id === namingEditTemplate.id)
  const updated = {
    ...namingEditTemplate,
    requirement_types: types.length ? types : ['*'],
    export_columns: exportColumns
  }
  if (idx >= 0) namingConfig.templates[idx] = updated
  else namingConfig.templates.push(updated)
  if (setActiveOnSave.value) namingConfig.active_template_id = updated.id
  return {
    active_template_id: namingConfig.active_template_id,
    templates: namingConfig.templates
  }
}

const saveNamingConfig = async () => {
  if (!canEditNaming.value || !ensureProject()) return
  savingNamingConfig.value = true
  try {
    const payload = buildNamingConfigPayload()
    const res = await aiRequirementApi.saveCaseNaming(payload, proStore.projectInfo.id)
    if (res.data?.code === 200) {
      ElMessage.success('项目命名配置已保存')
      await loadCaseNaming()
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '保存失败'))
  } finally {
    savingNamingConfig.value = false
  }
}

const runNamingPreview = async () => {
  if (!ensureProject()) return
  namingPreviewLoading.value = true
  try {
    const res = await aiRequirementApi.previewCaseNaming(
      {
        template_id: namingEditTemplateId.value,
        title_template: namingEditTemplate.title_template,
        sample_slots: { ...namingPreviewSample }
      },
      proStore.projectInfo.id,
      currentReq.value?.id
    )
    if (res.data?.code === 200) {
      namingPreviewResult.title = res.data.data?.title || ''
      namingPreviewResult.warnings = res.data.data?.warnings || []
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '预览失败'))
  } finally {
    namingPreviewLoading.value = false
  }
}

const saveReqNamingMeta = async () => {
  if (!currentReq.value || !ensureProject()) return
  savingReqNaming.value = true
  try {
    const res = await aiRequirementApi.saveRequirementNamingMeta(
      currentReq.value.id,
      {
        requirement_type: reqNamingMeta.requirement_type,
        naming_template_id: reqNamingMeta.naming_template_id || null
      },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('需求命名设置已保存')
      await loadCaseNaming()
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '保存失败'))
  } finally {
    savingReqNaming.value = false
  }
}

const handleRecalcTitles = async () => {
  if (!currentReq.value || !ensureProject()) return
  try {
    await ElMessageBox.confirm('将按当前模板重算本需求下全部草稿用例标题，是否继续？', '重算标题', { type: 'warning' })
  } catch {
    return
  }
  recalcTitlesLoading.value = true
  try {
    const res = await aiRequirementApi.recalcCaseTitles(
      currentReq.value.id,
      {},
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '重算完成')
      const ws = res.data.data?.warnings || []
      if (ws.length) ElMessage.warning(`有 ${ws.length} 条槽位告警，请检查生成报告或命名配置`)
      await loadCases(currentReq.value.id)
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '重算失败'))
  } finally {
    recalcTitlesLoading.value = false
  }
}

const saveExportProfile = async () => {
  if (!ensureProject()) return
  savingExportProfile.value = true
  try {
    const res = await aiRequirementApi.saveProjectZentaoBindings(
      { ...projectZentao, export_profile: exportProfile.value },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('导出目标已保存')
      await loadZentaoBindings()
      await loadCaseNaming()
      if (suggestedTemplateId.value && !reqNamingMeta.naming_template_id) {
        ElMessage.info(`当前推荐命名模板：${suggestedTemplateName.value}`)
      }
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '保存失败'))
  } finally {
    savingExportProfile.value = false
  }
}

const saveProjectZentao = async () => {
  if (!ensureProject()) return
  savingProjectZentao.value = true
  try {
    const res = await aiRequirementApi.saveProjectZentaoBindings(
      { ...projectZentao, export_profile: exportProfile.value },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('项目禅道配置已保存')
      await loadZentaoBindings()
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '保存失败'))
  } finally {
    savingProjectZentao.value = false
  }
}

const saveReqZentao = async () => {
  if (!currentReq.value || !ensureProject()) return
  savingReqZentao.value = true
  try {
    const res = await aiRequirementApi.saveRequirementZentaoBindings(
      currentReq.value.id,
      { ...reqZentao },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('本需求禅道配置已保存')
      await loadZentaoBindings()
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '保存失败'))
  } finally {
    savingReqZentao.value = false
  }
}

const handleReapplyBindings = async () => {
  if (!currentReq.value || !ensureProject()) return
  try {
    const res = await aiRequirementApi.reapplyZentaoBindings(
      currentReq.value.id,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '已刷新')
      await loadCases(currentReq.value.id)
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '刷新失败'))
  }
}

const loadConfigs = async () => {
  try {
    const res = await aiConfigApi.getList({ size: 200 })
    if (res.data?.code === 200) {
      configList.value = res.data.data?.list || []
    }
  } catch (e) {
    console.error(e)
  }
}

const loadReqCaseSettings = async () => {
  const pid = proStore.projectInfo?.id
  if (!pid) return
  try {
    const res = await aiConfigApi.getExecutionSettings(pid)
    if (res.data?.code === 200 && res.data.data?.requirement_case) {
      Object.assign(reqCaseSettings, res.data.data.requirement_case)
      // 始终按当前项目默认重置，避免跨项目残留 auto/fixed
      genForm.count_mode = reqCaseSettings.auto_count_enabled_default ? 'auto' : 'fixed'
    } else {
      genForm.count_mode = 'fixed'
    }
  } catch (e) {
    console.error(e)
  }
}

const loadList = async () => {
  if (!ensureProject()) return
  listLoading.value = true
  try {
    const res = await aiRequirementApi.getList({ project_id: proStore.projectInfo.id })
    if (res.data?.code === 200) {
      reqList.value = res.data.data?.list || []
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '加载列表失败'))
  } finally {
    listLoading.value = false
  }
}

const openUpload = () => {
  uploadForm.name = ''
  uploadForm.file = null
  uploadVisible.value = true
}

const onFileChange = (file) => {
  uploadForm.file = file.raw
}

const openArchiveDialog = async (row) => {
  if (isCommunityEdition.value) return
  if (!ensureProject() || !row?.id) return
  archiveDialog.value = {
    visible: true,
    loading: false,
    requirementId: row.id,
    reqName: row.name || `需求#${row.id}`,
    folderId: null,
    title: row.name || '',
    replaceIfExists: false
  }
  try {
    const res = await knowledgeApi.listFolders(proStore.projectInfo.id)
    archiveFolders.value = res.data?.items || []
  } catch {
    archiveFolders.value = []
  }
}

const submitArchive = async () => {
  if (isCommunityEdition.value) return
  if (!ensureProject() || !archiveDialog.value.requirementId) return
  archiveDialog.value.loading = true
  try {
    const res = await knowledgeApi.archiveFromRequirement(
      {
        requirement_id: archiveDialog.value.requirementId,
        folder_id: archiveDialog.value.folderId || undefined,
        title: (archiveDialog.value.title || '').trim() || undefined,
        replace_if_exists: archiveDialog.value.replaceIfExists
      },
      proStore.projectInfo.id
    )
    ElMessage.success(res.message || '归档成功')
    archiveDialog.value.visible = false
    const folderId = res.data?.folder_id
    if (folderId) {
      router.push(`/ai-knowledge/folders/${folderId}`)
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '归档失败'))
  } finally {
    archiveDialog.value.loading = false
  }
}

const handleUpload = async () => {
  if (!ensureProject()) return
  if (!uploadForm.file) {
    ElMessage.warning('请选择文件')
    return
  }
  uploading.value = true
  try {
    const res = await aiRequirementApi.upload(
      uploadForm.file,
      uploadForm.name,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('上传成功')
      uploadVisible.value = false
      await loadList()
      openDetail(res.data.data)
    } else {
      ElMessage.error(res.data?.message || '上传失败')
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '上传失败'))
  } finally {
    uploading.value = false
  }
}

const resetDetailState = () => {
  batchQueue.value = []
  activeBatchKey.value = null
  batchProgress.value = null
  caseFilterSectionId.value = ''
  caseFilterSourceRef.value = ''
  caseFilterLibraryStatus.value = ''
  caseFilterPointId.value = null
  sectionCoverage.value = null
  lastSessionCaseIds.value = []
  sessionFilterOnly.value = false
  generateJobHistory.value = []
  selectedReportJobId.value = null
  // 条数模式由随后的 loadReqCaseSettings 按当前项目默认覆盖；先置 fixed 避免跨项目残留 auto
  genForm.count_mode = 'fixed'
}

const openDetail = async (row) => {
  stopBatchJobPolling()
  batchJobId.value = null
  batchJobProgress.value = null
  currentReq.value = row
  detailVisible.value = true
  resetDetailState()

  const embedCasesOnly = props.embedMode && props.embedSection === 'cases'
  if (embedCasesOnly) {
    await loadCases(row.id)
    loadDocumentStructure({ lightweight: true })
    return
  }

  await loadConfigs()
  await loadReqCaseSettings()
  await loadExportTemplate()
  await loadZentaoBindings()
  await loadCaseNaming()
  await loadDocumentStructure()
  const enabled = enabledConfigs.value
  genForm.vision_config_id =
    enabled.find(c => isLikelyVisionModel(c))?.id
    || enabled.find(c => c.is_default)?.id
    || enabled[0]?.id
    || null
  genForm.case_gen_config_id =
    enabled.find(c => c.is_default && !isLikelyVisionModel(c))?.id
    || enabled.find(c => !isLikelyVisionModel(c))?.id
    || enabled.find(c => c.is_default)?.id
    || enabled[0]?.id
    || null
  await loadCases(row.id)
  refreshSectionCoverage()
  await loadGenerateJobHistory(row.id)
  const resumed = await resumeLatestGenerateJob(row.id)
  if (!resumed) {
    if (generateJobHistory.value.length) {
      applyGenerateJobRecord(generateJobHistory.value[0])
    } else {
      const lg = row.last_generate
      applyGenerateReport(lg?.generate_report || null, {
        time: lg?.time,
        duration_ms: lg?.duration_ms,
        tokens_used: lg?.tokens_used
      })
    }
  } else if (batchJobId.value) {
    selectedReportJobId.value = batchJobId.value
  }
}

const stopBatchJobPolling = () => {
  if (batchJobPollTimer) {
    clearInterval(batchJobPollTimer)
    batchJobPollTimer = null
  }
}

const updateBatchJobProgress = (job) => {
  const total = job.total_batches || 0
  const done = job.done_batches || 0
  const pct = job.progress_percent ?? (total ? Math.round(done / total * 100) : 0)
  let title = `正在执行 ${done}/${total} 批`
  if (job.status === 'running' && job.current_batch_name) {
    title += ` · ${job.current_batch_name}`
  } else if (job.status === 'pending') {
    title = `任务排队中…（共 ${total} 批）`
  }
  batchJobProgress.value = {
    percent: pct,
    title,
    failed: job.status === 'failed'
  }
}

const applyBatchJobFinish = async (job, silent = false) => {
  const br = job.batch_results || []
  const okN = br.filter(x => x.success).length
  const failN = br.length - okN
  const partialFail = job.status === 'completed' && failN > 0

  if (job.status === 'completed') {
    batchProgress.value = {
      title: partialFail
        ? `完成 ${okN}/${br.length} 批（部分失败，见生成报告）`
        : `完成 ${okN}/${br.length} 批`,
      failed: partialFail
    }
    if (!silent) {
      ElMessage.success(partialFail ? batchProgress.value.title : '批量生成完成')
    }
  } else if (job.status === 'failed') {
    const errMsg = job.error || '批量生成失败'
    batchProgress.value = { title: errMsg, failed: true }
    if (!silent) ElMessage.error(errMsg)
  }

  updateBatchJobProgress(job)
  if (currentReq.value) {
    await loadCases(currentReq.value.id)
    refreshSectionCoverage()
    await loadZentaoBindings()
    await loadList()
    const updated = reqList.value.find(r => r.id === currentReq.value.id)
    if (updated) currentReq.value = { ...currentReq.value, ...updated }
  }
  if (job.generate_report) {
    applyGenerateReport(job.generate_report, {
      time: formatJobTime(job),
      duration_ms: job.duration_ms,
      tokens_used: job.tokens_used
    }, caseList.value, { syncSession: true })
    if (currentReq.value) {
      currentReq.value.last_generate = {
        generate_report: job.generate_report,
        created_case_ids: job.generate_report.created_case_ids,
        duration_ms: job.duration_ms,
        tokens_used: job.tokens_used,
        case_count: caseList.value.length,
        time: reportMeta.value.time
      }
      await loadGenerateJobHistory(currentReq.value.id)
      selectedReportJobId.value = job.id
    }
  }
}

const pollBatchGenerateJob = async (jobId) => {
  if (!jobId || !proStore.projectInfo?.id) return
  try {
    const res = await aiRequirementApi.getGenerateJob(jobId, proStore.projectInfo.id)
    if (res.data?.code !== 200 || !res.data.data) return
    const job = res.data.data
    updateBatchJobProgress(job)
    if (job.status === 'pending' || job.status === 'running') {
      syncGenerateReportFromJob(job)
      return
    }
    stopBatchJobPolling()
    batchGenerating.value = false
    generating.value = false
    await applyBatchJobFinish(job)
  } catch (e) {
    stopBatchJobPolling()
    batchGenerating.value = false
    generating.value = false
    const msg = apiErrorMsg(e, '查询生成进度失败')
    batchProgress.value = { title: msg, failed: true }
    ElMessage.error(msg)
  }
}

const startBatchJobPolling = (jobId) => {
  stopBatchJobPolling()
  batchJobId.value = jobId
  batchJobPollTimer = setInterval(() => pollBatchGenerateJob(jobId), 2500)
  pollBatchGenerateJob(jobId)
}

const resumeLatestGenerateJob = async (reqId) => {
  if (!reqId || !proStore.projectInfo?.id) return false
  try {
    const res = await aiRequirementApi.getLatestGenerateJob(reqId, proStore.projectInfo.id)
    const job = res.data?.data
    if (!job || !['pending', 'running'].includes(job.status)) return false
    if ((job.payload || {}).job_kind === 'test_points') return false
    batchGenerating.value = true
    generating.value = true
    batchProgress.value = { title: '恢复进行中的批量生成任务…', failed: false }
    initInProgressBatchReport(job.total_batches || 0, job.id)
    selectedReportJobId.value = job.id
    syncGenerateReportFromJob(job)
    startBatchJobPolling(job.id)
    return true
  } catch {
    return false
  }
}

const loadCases = async (reqId) => {
  casesLoading.value = true
  try {
    const res = await aiRequirementApi.getCases(reqId, proStore.projectInfo.id)
    if (res.data?.code === 200) {
      caseList.value = res.data.data?.list || []
    }
  } finally {
    casesLoading.value = false
  }
}

const handleSupplementBatch = async (row) => {
  if (!currentReq.value || !ensureProject()) return
  const batchName = (row.name || '').trim()
  if (!batchName) {
    ElMessage.warning('请先填写批次名称（须与首次生成时一致）')
    return
  }
  if (!row.scope_section_ids?.length) {
    ElMessage.warning('请先选择本批章节范围')
    return
  }
  if (!exportBindingsReady.value) {
    ElMessage.warning('请先在「禅道导入配置」填写完整')
    return
  }
  const existing = countCasesForBatch(batchName)
  if (existing === 0) {
    try {
      await ElMessageBox.confirm(
        `批次「${batchName}」下尚无已生成用例，补充模式将把本次结果记入该批次名；是否继续？`,
        '补充生成',
        { type: 'info' }
      )
    } catch {
      return
    }
  }
  const scopeIds = row.scope_section_ids
  let imgN = 0
  for (const sid of scopeIds) {
    const sec = docSections.value.find(s => s.id === sid)
    if (sec?.image_indices?.length) imgN += sec.image_indices.length
  }
  if (imgN > 0 && !genForm.vision_config_id) {
    ElMessage.warning('本批范围含图片，请选择 Vision 模型')
    return
  }
  generating.value = true
  try {
    const res = await aiRequirementApi.generateCases(
      currentReq.value.id,
      buildGeneratePayload(row, { supplement: true }),
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || `批次「${batchName}」补充完成`)
      await loadCases(currentReq.value.id)
      refreshSectionCoverage()
      applyGenerateReport(res.data.data?.generate_report, {
        time: new Date().toLocaleString('zh-CN', { hour12: false }),
        duration_ms: res.data.data?.duration_ms,
        tokens_used: res.data.data?.tokens_used
      }, res.data.data?.cases, { syncSession: true })
      await refreshGenerateJobAfterSave(currentReq.value.id, res.data.data?.job_id)
    } else {
      ElMessage.error(res.data?.message || '补充生成失败')
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '补充生成失败'))
  } finally {
    generating.value = false
  }
}

const scopedImageCountForSectionIds = (scopeIds) => {
  if (!scopeIds?.length) return 0
  let n = 0
  for (const sid of scopeIds) {
    const sec = docSections.value.find(s => s.id === sid)
    if (sec?.image_indices?.length) n += sec.image_indices.length
  }
  return n
}

const handleRetryFailedBatch = async (row, batchIndex) => {
  if (!currentReq.value || !ensureProject()) return
  const jobId = selectedReportJobId.value || generateReport.value?.job_id
  if (!jobId) {
    ElMessage.warning('无法定位生成任务，请从生成记录下拉框选择对应任务后重试')
    return
  }
  if (!exportBindingsReady.value) {
    ElMessage.warning('请先在「禅道导入配置」填写完整')
    return
  }
  if (!row.scope_section_ids?.length) {
    ElMessage.warning('该批次缺少章节范围，请手动勾选章节后单批生成')
    return
  }
  if (scopedImageCountForSectionIds(row.scope_section_ids) > 0 && !genForm.vision_config_id) {
    ElMessage.warning('本批范围含图片，请选择 Vision 模型')
    return
  }
  const batchName = (row.name || '').trim() || `批次${batchIndex + 1}`
  const existing = countCasesForBatch(batchName)
  if (existing > 0) {
    let confirmMsg = ''
    if (row.supplement) {
      confirmMsg = `批次「${batchName}」已有 ${existing} 条用例，将按原「补充」语义追加，不会删除已有用例。是否继续？`
    } else if (row.replace) {
      confirmMsg = `批次「${batchName}」已有 ${existing} 条用例，将按原「替换本批」语义先删除再重新生成。是否继续？`
    } else {
      confirmMsg = `批次「${batchName}」已有 ${existing} 条用例，重试将先清空该批再重新生成，避免重复入库。是否继续？`
    }
    try {
      await ElMessageBox.confirm(confirmMsg, '重新生成', { type: 'warning' })
    } catch {
      return
    }
  }
  retryingBatchIndex.value = batchIndex
  try {
    const retryCountMode = row.count_mode === 'auto' ? 'auto' : 'fixed'
    const res = await aiRequirementApi.retryGenerateBatchJob(
      jobId,
      {
        batch_index: batchIndex,
        count_mode: retryCountMode,
        count: retryCountMode === 'fixed'
          ? (row.requested_count ?? genForm.count)
          : undefined,
        vision_config_id: genForm.vision_config_id || undefined,
        case_gen_config_id: genForm.case_gen_config_id || undefined,
        extra_instructions: (genForm.extra_instructions || '').trim() || undefined
      },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '重新生成成功')
      const job = res.data.data?.job
      if (job) {
        const idx = generateJobHistory.value.findIndex(j => j.id === job.id)
        if (idx >= 0) generateJobHistory.value[idx] = job
        else generateJobHistory.value.unshift(job)
        applyGenerateJobRecord(job)
      } else if (res.data.data?.batch_result && generateReport.value?.batch_results) {
        generateReport.value.batch_results[batchIndex] = res.data.data.batch_result
      }
      if (res.data.data?.cases) {
        caseList.value = res.data.data.cases
      } else {
        await loadCases(currentReq.value.id)
      }
      syncSessionFromReport(generateReport.value, caseList.value, { autoFilter: false })
      await refreshSectionCoverage()
      await loadList()
    } else {
      ElMessage.error(res.data?.message || '重新生成失败')
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '重新生成失败'))
    try {
      const jRes = await aiRequirementApi.getGenerateJob(jobId, proStore.projectInfo.id)
      if (jRes.data?.code === 200 && jRes.data.data) {
        const refreshed = jRes.data.data
        const hi = generateJobHistory.value.findIndex(j => j.id === jobId)
        if (hi >= 0) generateJobHistory.value[hi] = refreshed
        applyGenerateJobRecord(refreshed)
      }
    } catch {
      /* 忽略刷新失败 */
    }
  } finally {
    retryingBatchIndex.value = null
  }
}

const handleGenerate = async () => {
  if (!currentReq.value) return
  if (!enabledConfigs.value.length) {
    ElMessage.warning('没有已启用的 AI 配置，请先在 AI 模型配置中创建并启用')
    return
  }
  if (!exportBindingsReady.value) {
    ElMessage.warning('请先在「禅道导入配置」填写所属产品、所属模块、相关研发需求')
    return
  }
  if (!selectedSectionIds.value.length) {
    ElMessage.warning('请至少选择一个生成章节')
    return
  }
  if (scopeEstimate.value?.level === 'block') {
    ElMessage.warning(scopeEstimate.value.message || '选中范围过大，请减少章节')
    return
  }
  if (scopedImageCount.value > 0 && !genForm.vision_config_id) {
    ElMessage.warning('选中范围含图片，请选择读图用的 Vision 模型')
    return
  }
  const batchName = inferBatchName(selectedSectionIds.value) || undefined
  if (genForm.supplement && !batchName) {
    ElMessage.warning('无法推断批次名，请先勾选章节')
    return
  }
  if (genForm.supplement && genForm.replace_existing) {
    ElMessage.warning('「补充本批」与「替换已有」不能同时开启')
    return
  }
  const existing = batchName ? countCasesForBatch(batchName) : 0
  if (genForm.supplement && existing === 0) {
    try {
      await ElMessageBox.confirm(
        `批次「${batchName}」下尚无已生成用例，补充模式将把本次结果记入该批次名；是否继续？`,
        '补充生成',
        { type: 'info' }
      )
    } catch {
      return
    }
  }
  generating.value = true
  try {
    const payload = {
      count_mode: genForm.count_mode || 'fixed',
      count: genForm.count_mode === 'auto' ? undefined : genForm.count,
      replace_existing: genForm.replace_existing && !genForm.supplement,
      supplement_batch_name: genForm.supplement ? batchName : undefined,
      case_gen_config_id: genForm.case_gen_config_id || undefined,
      vision_config_id: genForm.vision_config_id || undefined,
      extra_instructions: (genForm.extra_instructions || '').trim() || undefined,
      export_defaults: {
        product: reqZentao.product,
        module: reqZentao.module,
        related_story: reqZentao.related_story
      },
      scope_section_ids: selectedSectionIds.value,
      batch_name: batchName,
      ...knowledgeRefsPayload()
    }
    const res = await aiRequirementApi.generateCases(
      currentReq.value.id,
      payload,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '生成成功')
      const gr = res.data.data?.generate_report
      if (gr?.case_gen?.partial_truncated) {
        ElMessage.warning(
          `返回用例超过项目绝对上限，已仅保留前 ${gr.case_gen.parsed_count} 条入库（可在 AI 配置中上调上限）`
        )
      }
      caseList.value = res.data.data?.cases || []
      applyGenerateReport(gr, {
        time: new Date().toLocaleString('zh-CN', { hour12: false }),
        duration_ms: res.data.data?.duration_ms,
        tokens_used: res.data.data?.tokens_used
      }, res.data.data?.cases, { syncSession: true })
      if (currentReq.value) {
        currentReq.value.last_generate = {
          generate_report: res.data.data?.generate_report,
          created_case_ids: res.data.data?.generate_report?.created_case_ids,
          duration_ms: res.data.data?.duration_ms,
          tokens_used: res.data.data?.tokens_used,
          case_count: caseList.value.length,
          time: reportMeta.value.time
        }
      }
      await refreshGenerateJobAfterSave(currentReq.value.id, res.data.data?.job_id)
      await loadZentaoBindings()
      await loadList()
      const updated = reqList.value.find(r => r.id === currentReq.value.id)
      if (updated) {
        currentReq.value = { ...currentReq.value, ...updated }
      }
    } else {
      ElMessage.error(res.data?.message || '生成失败')
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '生成失败'))
  } finally {
    generating.value = false
  }
}

const handleBatchGenerate = async () => {
  if (!currentReq.value) return
  if (!batchQueue.value.length) {
    ElMessage.warning('请先将章节加入生成队列')
    return
  }
  if (!enabledConfigs.value.length) {
    ElMessage.warning('没有已启用的 AI 配置')
    return
  }
  if (!exportBindingsReady.value) {
    ElMessage.warning('请先在「禅道导入配置」填写完整')
    return
  }
  for (const item of batchQueue.value) {
    if (!item.scope_section_ids?.length) {
      ElMessage.warning(`批次「${item.name}」未选择章节`)
      return
    }
    if (item.supplement && item.replace) {
      ElMessage.warning(`批次「${item.name}」不能同时开启补充与替换`)
      return
    }
    if (exportProfile.value === 'zentao' && item.useCustomZentao) {
      const ok = item.product?.trim() && item.module?.trim() && item.related_story?.trim()
      if (!ok) {
        ElMessage.warning(`批次「${item.name}」已开启自定义禅道，请填写完整`)
        return
      }
    }
  }
  if (batchQueueImageCount.value > 0 && !genForm.vision_config_id) {
    ElMessage.warning('队列范围内含图片，请选择 Vision 模型')
    return
  }
  batchGenerating.value = true
  batchProgress.value = { title: `正在提交 ${batchQueue.value.length} 批任务…`, failed: false }
  batchJobProgress.value = { percent: 0, title: '正在提交任务…', failed: false }
  generating.value = true
  initInProgressBatchReport(batchQueue.value.length)
  try {
    const batches = batchQueue.value.map(b => {
      const mode = b.count_mode === 'auto' ? 'auto' : 'fixed'
      const row = {
        name: (b.name || '').trim() || '未命名批次',
        scope_section_ids: b.scope_section_ids,
        count_mode: mode,
        count: mode === 'auto' ? undefined : b.count,
        supplement: !!b.supplement,
        replace: !!b.replace
      }
      const hasBatchZentao =
        b.useCustomZentao ||
        (b.product?.trim() && b.module?.trim() && b.related_story?.trim())
      if (hasBatchZentao) {
        row.export_defaults = {
          product: b.product?.trim() || effectiveZentao.product,
          module: b.module?.trim() || effectiveZentao.module,
          related_story: b.related_story?.trim() || effectiveZentao.related_story
        }
      }
      return row
    })
    const res = await aiRequirementApi.generateCasesBatch(
      currentReq.value.id,
      {
        vision_config_id: genForm.vision_config_id || undefined,
        case_gen_config_id: genForm.case_gen_config_id || undefined,
        replace_existing: genForm.replace_existing,
        extra_instructions: (genForm.extra_instructions || '').trim() || undefined,
        batches,
        ...knowledgeRefsPayload()
      },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      const job = res.data.data
      ElMessage.success(res.data.message || '生成任务已提交')
      batchProgress.value = {
        title: res.data.message || `任务已提交，共 ${job?.total_batches || batches.length} 批`,
        failed: false
      }
      if (job?.id) {
        selectedReportJobId.value = job.id
        if (generateReport.value) {
          generateReport.value.job_id = job.id
          generateReport.value.total_batches = job.total_batches || batches.length
        }
        reportMeta.value = { time: `任务 #${job.id} 执行中`, duration_ms: null, tokens_used: 0 }
        await loadGenerateJobHistory(currentReq.value.id)
        startBatchJobPolling(job.id)
      } else {
        batchGenerating.value = false
        generating.value = false
      }
    } else {
      ElMessage.error(res.data?.message || '提交批量生成失败')
      batchGenerating.value = false
      generating.value = false
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '提交批量生成失败'))
    batchProgress.value = { title: apiErrorMsg(e, '提交批量生成失败'), failed: true }
    batchJobProgress.value = { percent: 0, title: batchProgress.value.title, failed: true }
    batchGenerating.value = false
    generating.value = false
  }
}

const onCaseSelect = (rows) => {
  selectedCaseIds.value = [...new Set(rows.filter(r => r._isFirstStep).map(r => r._caseId))]
}

const deleteCasesByIds = async (caseIds, confirmMsg) => {
  await ElMessageBox.confirm(confirmMsg, '提示', { type: 'warning' })
  try {
    const res = await aiRequirementApi.deleteCases(
      currentReq.value.id,
      caseIds,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('删除成功')
      selectedCaseIds.value = []
      await loadCases(currentReq.value.id)
      refreshSectionCoverage()
      await loadList()
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '删除失败'))
  }
}

const handleDeleteCases = () =>
  deleteCasesByIds(
    selectedCaseIds.value,
    `确定删除选中的 ${selectedCaseIds.value.length} 条用例？`
  )

const handleImportToLibrary = async (caseIds) => {
  const ids = Array.isArray(caseIds) ? caseIds : [...selectedCaseIds.value]
  if (!ids.length || !currentReq.value) return
  importingToLibrary.value = true
  try {
    const res = await aiRequirementApi.importToLibrary(
      currentReq.value.id,
      ids,
      proStore.projectInfo.id,
      { duplicateTitleMode: importDuplicateMode.value }
    )
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      const msg = res.data.message || '审核入库成功'
      if (d.copied_count > 0 || d.overwritten_count > 0) {
        ElMessage.success(msg)
      } else if (d.skipped_count > 0) {
        ElMessage.warning(msg)
      } else {
        ElMessage.info(msg)
      }
      await loadCases(currentReq.value.id)
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '审核入库失败'))
  } finally {
    importingToLibrary.value = false
  }
}

const handleImportOneToLibrary = async (caseId) => {
  if (!caseId || !currentReq.value) return
  importingOneId.value = caseId
  try {
    await handleImportToLibrary([caseId])
  } finally {
    importingOneId.value = null
  }
}

const handleSessionImportPending = async () => {
  const pendingIds = sessionCases.value.filter(c => !isCaseInLibrary(c)).map(c => c.id)
  if (!pendingIds.length) {
    ElMessage.info('本次生成的用例均已入库')
    return
  }
  await handleImportToLibrary(pendingIds)
}

const selectSessionPending = () => {
  selectedCaseIds.value = sessionCases.value.filter(c => !isCaseInLibrary(c)).map(c => c.id)
}

const handleDeleteOneCase = (c) =>
  deleteCasesByIds([c.id], `确定删除用例「${c.title}」？`)

const openEditCase = (c) => {
  editForm.value = {
    id: c.id,
    module: c.module,
    title: c.title,
    precondition: c.precondition,
    priority: c.priority,
    type: c.type || '功能测试',
    stage: c.stage || '系统测试阶段',
    keywords: c.keywords,
    test_point_ids: [...(c.test_point_ids || [])],
    steps: normalizeCaseSteps(c.steps)
  }
  editVisible.value = true
}

const saveEditCase = async () => {
  editSaving.value = true
  try {
    const res = await aiRequirementApi.updateCase(
      currentReq.value.id,
      editForm.value.id,
      {
        module: editForm.value.module,
        title: editForm.value.title,
        precondition: editForm.value.precondition,
        priority: editForm.value.priority,
        type: editForm.value.type,
        keywords: editForm.value.keywords,
        steps: editForm.value.steps
      },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('保存成功')
      editVisible.value = false
      await loadCases(currentReq.value.id)
    }
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    editSaving.value = false
  }
}

const handleExport = async () => {
  if (!exportBindingsReady.value) {
    ElMessage.warning(
      exportProfile.value === 'generic'
        ? '暂无用例可导出'
        : '请先在「禅道导入配置」填写完整后再导出'
    )
    return
  }
  const uStore = UserStore()
  const url = aiRequirementApi.exportXlsxUrl(currentReq.value.id, proStore.projectInfo.id)
  try {
    const res = await fetch(url, {
      headers: { Authorization: 'Bearer ' + uStore.token }
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || '导出失败')
    }
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    const suffix = exportProfile.value === 'generic' ? 'cases' : 'zentao_cases'
    a.download = `requirement_${currentReq.value.id}_${suffix}.xlsx`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error(e.message || '导出失败')
  }
}

const handleDeleteReq = async (row) => {
  await ElMessageBox.confirm(`确定删除需求「${row.name}」？`, '提示', { type: 'warning' })
  try {
    const res = await aiRequirementApi.delete(row.id, proStore.projectInfo.id)
    if (res.data?.code === 200) {
      ElMessage.success('删除成功')
      if (currentReq.value?.id === row.id) detailVisible.value = false
      await loadList()
    }
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

const goTestAnalysisPoint = (pointId) => {
  if (!currentReq.value?.id) return
  router.push({
    name: 'aiTestingWorkspace',
    params: { reqId: String(currentReq.value.id) },
    query: { tab: 'points', pointId: String(pointId) }
  })
}

const openDetailById = async (reqId) => {
  if (!reqId) return
  let row = reqList.value.find(r => r.id === reqId)
  if (!row) {
    try {
      const res = await aiRequirementApi.getDetail(reqId, proStore.projectInfo?.id)
      if (res.data?.code === 200) row = res.data.data
    } catch (e) { /* ignore */ }
  }
  if (!row) return
  currentReq.value = row
  detailVisible.value = true
  await openDetail(row)
}

const applyRouteCaseFilters = () => {
  const sourceRef = route.query.sourceRef
  const pointId = route.query.pointId || props.highlightPointId
  if (sourceRef) caseFilterSourceRef.value = String(sourceRef)
  if (pointId) caseFilterPointId.value = Number(pointId)
}

const openDetailFromRoute = async () => {
  const rawId = route.query.reqId
  if (!rawId) return
  const reqId = Number(rawId)
  if (!reqId) return
  let row = reqList.value.find(r => r.id === reqId)
  if (!row) {
    try {
      const res = await aiRequirementApi.getDetail(reqId, proStore.projectInfo?.id)
      if (res.data?.code === 200) row = res.data.data
    } catch (e) { /* ignore */ }
  }
  if (!row) return
  await openDetail(row)
  applyRouteCaseFilters()
}

onMounted(async () => {
  await loadCommunityEdition()
  loadConfigs()
  loadExportTemplate()
  if (props.embedMode && props.embedReqId) {
    await openDetailById(Number(props.embedReqId))
    detailVisible.value = true
    applyRouteCaseFilters()
    return
  }
  await loadList()
  await openDetailFromRoute()
})

watch(() => props.embedReqId, async (id) => {
  if (!props.embedMode || !id) return
  await openDetailById(Number(id))
  detailVisible.value = true
})

onUnmounted(() => {
  stopBatchJobPolling()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
}
.upload-tip {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
.detail-panel {
  padding: 0 4px;
}
.detail-archive-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 10px 0 4px;
}
.detail-archive-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.scope-card {
  margin: 12px 0;
}
.scope-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.scope-main {
  flex: 1;
  min-width: 0;
}
.scope-actions {
  margin-top: 8px;
}
.scope-body {
  max-height: 220px;
  overflow: auto;
}
.batch-sidebar {
  width: 280px;
  flex-shrink: 0;
  border-left: 1px solid #ebeef5;
  padding-left: 12px;
  max-height: 320px;
  display: flex;
  flex-direction: column;
}
.batch-sidebar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 14px;
}
.batch-queue-list {
  flex: 1;
  overflow-y: auto;
}
.batch-queue-item {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.batch-queue-item.active {
  border-color: var(--el-color-primary);
  background: #ecf5ff;
}
.batch-queue-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.batch-idx {
  font-size: 12px;
  color: #909399;
  min-width: 16px;
}
.batch-queue-meta {
  margin: 0 0 6px;
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}
.batch-queue-existing {
  margin: 0 0 4px;
  font-size: 12px;
  color: #e6a23c;
}
.batch-queue-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 4px;
}
.batch-queue-ops {
  text-align: right;
}
.batch-sidebar-footer {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #ebeef5;
}
.batch-table-card {
  margin: 0 0 12px;
}
.batch-config-table :deep(.el-table__cell) {
  vertical-align: middle;
}
.batch-config-table :deep(.batch-count-col .cell) {
  overflow: visible;
}
.batch-count-input {
  width: 96px;
}
.batch-count-input :deep(.el-input) {
  width: 96px;
}
.label-with-tip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.gen-inline-form :deep(.el-form-item__label) {
  display: inline-flex;
  align-items: center;
  padding-right: 10px;
}
.gen-inline-form :deep(.el-form-item) {
  margin-right: 20px;
  margin-bottom: 12px;
}
.extra-instructions-form {
  margin-top: 4px;
  max-width: 960px;
}
.extra-instructions-form :deep(.el-form-item) {
  margin-bottom: 8px;
}
.session-card {
  margin-top: 12px;
}
.session-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.session-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.batch-job-progress {
  margin-bottom: 12px;
}
.batch-job-progress-text {
  margin-top: 6px;
  font-size: 13px;
  color: #606266;
}
.batch-range-btn {
  max-width: 100%;
  white-space: normal;
  line-height: 1.4;
  text-align: left;
  height: auto;
}
.batch-inherit-tip {
  font-size: 12px;
  color: #909399;
}
.batch-zentao-form :deep(.el-textarea__inner) {
  min-height: 56px;
}
.batch-zentao-sync-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.batch-zentao-sync-tip {
  font-size: 12px;
  color: #909399;
}
.coverage-card {
  margin: 0 0 12px;
}
.coverage-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}
.coverage-warn {
  color: #e6a23c;
}
.coverage-projected {
  color: #409eff;
}
.coverage-list {
  margin: 0;
  padding-left: 0;
  list-style: none;
  max-height: 200px;
  overflow-y: auto;
}
.coverage-list li {
  padding: 4px 0;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.coverage-collapse {
  border: none;
}
.cases-filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.scope-meta {
  margin: 8px 0 0;
  font-size: 12px;
  color: #909399;
}
.count-with-recommend {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.count-recommend-tag {
  margin-left: 0;
}
.count-recommend-hint {
  margin: -4px 0 10px 88px;
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}
.count-auto-alert {
  margin: 0 0 12px;
  width: 100%;
}
.gen-card {
  margin: 12px 0;
}
.count-expectation-alert {
  margin-bottom: 12px;
}
.count-expectation-alert :deep(.el-alert__title) {
  font-size: 13px;
  line-height: 1.5;
}
.zentao-card {
  margin: 12px 0;
}
.naming-card {
  margin: 12px 0;
}
.naming-admin-block {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #ebeef5;
}
.naming-preview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(120px, 1fr));
  gap: 8px;
  max-width: 720px;
  align-items: center;
}
.naming-preview-result {
  font-size: 13px;
  color: #303133;
  word-break: break-all;
  line-height: 1.5;
}
.naming-readonly {
  font-size: 13px;
  color: #606266;
}
.naming-template-code {
  display: block;
  margin-top: 6px;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  word-break: break-all;
}
.naming-label-with-help {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
  flex-wrap: nowrap;
}
.naming-help-intro {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}
.naming-help-intro code {
  padding: 1px 4px;
  background: #f5f7fa;
  border-radius: 3px;
  font-size: 12px;
}
.naming-slot-help-table code {
  font-size: 12px;
}
.naming-warn-list {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 12px;
}
.zentao-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin: 8px 0;
}
.effective-preview {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
  line-height: 1.5;
}
.effective-label {
  color: #606266;
}
.export-defaults-form {
  margin-bottom: 4px;
}
.report-card {
  margin-bottom: 12px;
}
.report-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.report-meta {
  font-size: 12px;
  color: #909399;
  font-weight: normal;
}
.report-sub {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
  font-weight: normal;
}
.report-line {
  margin: 0 0 8px;
  font-size: 13px;
  color: #606266;
}
.report-block {
  margin-bottom: 12px;
}
.report-block-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.report-pre {
  margin: 0;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.report-pre-error {
  color: #f56c6c;
  background: #fef0f0;
}
.cases-module-hint {
  margin-bottom: 12px;
}
.cases-filter-hint {
  margin-bottom: 12px;
}
.cases-filter-hint-body {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: #606266;
}
.cases-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.step-row {
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #eee;
}
.step-block-head {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
}
.step-field {
  margin-bottom: 8px;
}
.step-field-label {
  display: block;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.dialog-title-with-tip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 16px;
  font-weight: 600;
}
.drawer-title-with-tip {
  max-width: calc(100% - 48px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.title-tip-icon {
  font-size: 16px;
  color: #909399;
  cursor: help;
  vertical-align: middle;
  flex-shrink: 0;
}
.title-tip-icon:hover {
  color: var(--el-color-primary);
}
.tp-links {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 0 4px;
}
</style>

<style>
/* tooltip 挂载到 body，需非 scoped */
.requirement-usage-tooltip {
  max-width: 420px;
  line-height: 1.55;
  font-size: 13px;
}
.requirement-embed-host :deep(.embed-hidden-card > .el-card__header) {
  display: none;
}
.requirement-embed-host :deep(.embed-hidden-card) {
  border: none;
  box-shadow: none;
  background: transparent;
}
.requirement-embed-host :deep(.embed-hidden-card > .el-card__body) {
  padding: 0;
}
.cases-panel {
  min-height: 280px;
}
.embed-loading-holder {
  min-height: 280px;
}
.naming-template-form :deep(.el-form-item__label) {
  white-space: nowrap;
  line-height: 32px;
  height: auto;
  align-items: flex-start;
  padding-right: 12px;
}
</style>
