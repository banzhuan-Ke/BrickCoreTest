<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">🧭 AI 测试分析</div>
    </template>
    <template #main>
      <div class="toolbar">
        <el-button type="primary" @click="goUpload" icon="Upload">上传需求文档</el-button>
        <el-button @click="loadList" icon="Refresh">刷新</el-button>
      </div>

      <el-table :data="reqList" v-loading="listLoading" stripe border style="margin-top: 12px;">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="需求名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="test_point_count" label="测试点" width="80" align="center" />
        <el-table-column prop="scheme_count" label="方案" width="70" align="center" />
        <el-table-column prop="case_count" label="用例" width="70" align="center" />
        <el-table-column prop="section_count" label="章节" width="70" align="center" />
        <el-table-column prop="update_time" label="更新时间" width="170" />
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">分析</el-button>
            <el-button link type="success" @click="goCases(row)">用例</el-button>
            <el-button
              v-if="canImportLibrary && row.case_count"
              link
              type="warning"
              @click="openCopyToLibraryFromList(row)"
            >复制到库</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-drawer v-model="detailVisible" size="90%" destroy-on-close>
        <template #header>
          <span>{{ currentReq?.name || '测试分析' }}</span>
        </template>
        <div v-if="currentReq" class="detail-panel">
          <el-descriptions :column="5" border size="small" class="req-meta">
            <el-descriptions-item label="测试点">{{ overview.test_point_total || 0 }}</el-descriptions-item>
            <el-descriptions-item label="已确认">{{ overview.test_point_confirmed || 0 }}</el-descriptions-item>
            <el-descriptions-item label="方案版本">{{ overview.scheme_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="功能用例">{{ overview.case_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="图片">{{ currentReq.image_count || 0 }} 张</el-descriptions-item>
          </el-descriptions>

          <el-tabs v-model="activeTab" class="analysis-tabs">
            <el-tab-pane label="思维导图" name="mindmap">
              <div class="gen-bar">
                <el-select v-model="genForm.vision_config_id" placeholder="Vision（有图时必选）" clearable style="width: 200px;">
                  <el-option v-for="c in configList" :key="c.id" :label="c.name" :value="c.id" />
                </el-select>
                <el-select v-model="genForm.text_config_id" placeholder="文本模型" clearable style="width: 200px;">
                  <el-option v-for="c in configList" :key="'t'+c.id" :label="c.name" :value="c.id" />
                </el-select>
                <el-tooltip content="同一需求多次分批生成时用于区分，如「场景一」。导图可按批次筛选；重新生成时勾选「替换本批次」会先删该批次旧数据。" placement="top">
                  <el-input v-model="genForm.batch_name" placeholder="批次名（建议填写）" style="width: 150px;" />
                </el-tooltip>
                <el-input-number v-model="genForm.count" :min="5" :max="100" style="width: 110px;" />
                <el-checkbox v-model="genForm.replace_batch">替换本批次</el-checkbox>
                <el-button type="primary" :loading="generating" @click="handleGeneratePoints">生成测试点</el-button>
                <el-button @click="loadMindmap">刷新导图</el-button>
              </div>
              <div class="gen-bar secondary-bar">
                <el-checkbox v-model="mindmapScopeOnly" @change="loadMindmap">导图仅显示当前勾选章节</el-checkbox>
                <el-tag v-if="mindmapFilteredTotal != null" type="info" size="small">
                  当前导图 {{ mindmapFilteredTotal }} 条
                </el-tag>
              </div>
              <el-alert v-if="scopeHint" :title="scopeHint" type="warning" show-icon :closable="false" style="margin: 8px 0;" />
              <div class="mindmap-layout">
                <div class="section-panel">
                  <div class="panel-head">
                    <b>章节范围</b>
                    <el-button link type="primary" @click="selectAllSections">全选</el-button>
                    <el-button link @click="clearSections">清空</el-button>
                  </div>
                  <el-tree
                    ref="sectionTreeRef"
                    :data="sectionTree"
                    show-checkbox
                    node-key="id"
                    :props="{ label: 'title', children: 'children' }"
                    @check="onSectionCheck"
                    default-expand-all
                    class="section-tree"
                  />
                </div>
                <div class="map-panel">
                  <TestPointMindMap
                    :tree-data="echartsTree"
                    :req-id="currentReq.id"
                    :project-id="proStore.projectInfo?.id"
                    :export-params="mindmapExportParams"
                    :loading="mindmapLoading"
                    @node-click="onPointNodeClick"
                  />
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane label="测试点列表" name="points">
              <div class="point-filter-bar">
                <el-input v-model="pointFilters.keyword" placeholder="关键词（标题/描述/模块）" clearable style="width: 200px;" @keyup.enter="loadTestPoints" />
                <el-select v-model="pointFilters.status" placeholder="状态" clearable style="width: 100px;" @change="loadTestPoints">
                  <el-option label="草稿" value="draft" />
                  <el-option label="已确认" value="confirmed" />
                </el-select>
                <el-select v-model="pointFilters.test_type" placeholder="类型" clearable style="width: 100px;" @change="loadTestPoints">
                  <el-option v-for="t in pointFilterOptions.test_types" :key="t" :label="t" :value="t" />
                </el-select>
                <el-select v-model="pointFilters.priority" placeholder="优先级" clearable style="width: 90px;" @change="loadTestPoints">
                  <el-option v-for="p in pointFilterOptions.priorities" :key="p" :label="p" :value="p" />
                </el-select>
                <el-select v-model="pointFilters.batch_name" placeholder="批次" clearable filterable style="width: 160px;" @change="loadTestPoints">
                  <el-option v-for="b in pointFilterOptions.batches" :key="b" :label="b" :value="b" />
                </el-select>
                <el-select v-model="pointFilters.main_module" placeholder="主模块" clearable filterable style="width: 140px;" @change="loadTestPoints">
                  <el-option v-for="m in pointFilterOptions.main_modules" :key="m" :label="m" :value="m" />
                </el-select>
                <el-button @click="loadTestPoints" icon="Search">筛选</el-button>
                <el-button @click="resetPointFilters">重置</el-button>
              </div>
              <div class="gen-bar">
                <el-tooltip content="将选中测试点标记为「已确认」，生成测试方案时默认只纳入已确认项（除非勾选包含未确认）。" placement="top">
                  <el-button type="success" :disabled="!selectedPointIds.length" @click="confirmSelected">
                    确认选中 ({{ selectedPointIds.length }})
                  </el-button>
                </el-tooltip>
                <el-button type="danger" :disabled="!selectedPointIds.length" @click="deleteSelected">删除选中</el-button>
                <el-button type="primary" plain @click="openCaseGenDialog">从测试点生成用例</el-button>
                <el-button
                  v-if="canImportLibrary"
                  type="success"
                  plain
                  :disabled="!overview.case_count"
                  @click="openCopyToLibraryDialog"
                >复制到用例库</el-button>
                <span class="list-hint">
                  显示 {{ displayTestPoints.length }} / 共 {{ testPointsTotalAll }} 条
                  <el-button
                    v-if="highlightPointId"
                    link
                    type="primary"
                    size="small"
                    @click="highlightPointId = null"
                  >清除测试点筛选</el-button>
                </span>
              </div>
              <el-table
                :data="displayTestPoints"
                v-loading="pointsLoading"
                stripe
                border
                :row-class-name="testPointRowClass"
                @selection-change="rows => selectedPointIds = rows.map(r => r.id)"
              >
                <el-table-column type="selection" width="45" />
                <el-table-column prop="id" label="ID" width="60" />
                <el-table-column prop="main_module" label="模块" width="100" show-overflow-tooltip />
                <el-table-column prop="sub_module" label="子模块" width="100" show-overflow-tooltip />
                <el-table-column prop="title" label="测试点" min-width="180" show-overflow-tooltip />
                <el-table-column prop="test_type" label="类型" width="80" />
                <el-table-column prop="priority" label="优先级" width="70" />
                <el-table-column prop="source_ref" label="批次" width="120" show-overflow-tooltip>
                  <template #default="{ row }">
                    {{ (row.source_ref || '').replace(/^batch:/, '') || '-' }}
                  </template>
                </el-table-column>
                <el-table-column prop="status" label="状态" width="90">
                  <template #default="{ row }">
                    <el-tag :type="row.status === 'confirmed' ? 'success' : 'info'" size="small">
                      {{ row.status === 'confirmed' ? '已确认' : '草稿' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="160" fixed="right">
                  <template #default="{ row }">
                    <el-button link type="primary" @click="editPoint(row)">编辑</el-button>
                    <el-button link type="success" @click="goCasesForPoint(row)">用例</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="测试方案" name="scheme">
              <div class="gen-bar">
                <el-input v-model="schemeForm.title" placeholder="方案标题" style="width: 240px;" />
                <el-select v-model="schemeForm.text_config_id" placeholder="文本模型" clearable style="width: 200px;">
                  <el-option v-for="c in configList" :key="'s'+c.id" :label="c.name" :value="c.id" />
                </el-select>
                <el-checkbox v-model="schemeForm.include_unconfirmed">包含未确认测试点</el-checkbox>
                <el-button type="primary" :loading="schemeGenerating" @click="handleGenerateScheme">生成方案</el-button>
              </div>
              <el-collapse v-model="schemeEnvCollapse" class="scheme-env-collapse">
                <el-collapse-item title="测试环境补充（建议填写，避免 AI 编造环境信息）" name="env">
                  <el-form :inline="true" class="scheme-env-form">
                    <el-form-item label="被测系统"><el-input v-model="schemeEnvHints.system_name" placeholder="如：知识智能平台" style="width: 200px;" /></el-form-item>
                    <el-form-item label="环境"><el-input v-model="schemeEnvHints.test_env" placeholder="SIT / UAT / 预发" style="width: 120px;" /></el-form-item>
                    <el-form-item label="访问入口"><el-input v-model="schemeEnvHints.access_entry" placeholder="URL 或菜单路径" style="width: 280px;" /></el-form-item>
                    <el-form-item label="版本"><el-input v-model="schemeEnvHints.deploy_version" placeholder="构建号/版本" style="width: 140px;" /></el-form-item>
                  </el-form>
                  <el-form label-width="100px" class="scheme-env-form-block">
                    <el-form-item label="客户端要求"><el-input v-model="schemeEnvHints.client_requirements" type="textarea" :rows="2" placeholder="每行一条，如：Chrome 最新版；分辨率 1920×1080" /></el-form-item>
                    <el-form-item label="账号与角色"><el-input v-model="schemeEnvHints.accounts_roles" type="textarea" :rows="2" placeholder="每行一条，如：管理员：配置抽取场景" /></el-form-item>
                    <el-form-item label="测试数据"><el-input v-model="schemeEnvHints.test_data" type="textarea" :rows="2" placeholder="样例文件、配置项、库表准备" /></el-form-item>
                    <el-form-item label="依赖服务"><el-input v-model="schemeEnvHints.dependencies" type="textarea" :rows="2" placeholder="每行一条：MinIO、LLM API、禅道…" /></el-form-item>
                    <el-form-item label="测试工具"><el-input v-model="schemeEnvHints.tools" type="textarea" :rows="1" placeholder="禅道、浏览器开发者工具…" /></el-form-item>
                  </el-form>
                </el-collapse-item>
              </el-collapse>
              <el-row :gutter="16">
                <el-col :span="6">
                  <div class="scheme-list">
                    <div
                      v-for="s in schemes"
                      :key="s.id"
                      :class="['scheme-item', { active: currentScheme?.id === s.id }]"
                      @click="selectScheme(s)"
                    >
                      <div class="scheme-item-title">{{ s.title }}</div>
                      <div class="scheme-item-meta">v{{ s.version }} · {{ statusLabel(s.status) }}</div>
                    </div>
                    <el-empty v-if="!schemes.length" description="暂无方案" :image-size="60" />
                  </div>
                </el-col>
                <el-col :span="18">
                  <div v-if="currentScheme" class="scheme-content">
                    <div class="scheme-actions">
                      <el-radio-group v-model="schemeViewMode" size="small">
                        <el-radio-button value="preview">报告预览</el-radio-button>
                        <el-radio-button value="edit">源码编辑</el-radio-button>
                      </el-radio-group>
                      <el-button size="small" @click="saveSchemeMd" :loading="savingScheme">保存编辑</el-button>
                      <el-button size="small" type="success" @click="confirmScheme">确认方案</el-button>
                      <el-button
                        v-if="canImportLibrary && overview.case_count"
                        size="small"
                        type="success"
                        plain
                        @click="openCopyToLibraryDialog"
                      >复制到用例库</el-button>
                      <el-button size="small" type="primary" @click="exportSchemeDocx">导出 Word</el-button>
                      <el-button size="small" type="danger" plain @click="deleteCurrentScheme">删除方案</el-button>
                    </div>
                    <MarkdownReport
                      v-if="schemeViewMode === 'preview'"
                      :content="schemeMdEdit"
                      max-height="520px"
                    />
                    <el-input
                      v-else
                      v-model="schemeMdEdit"
                      type="textarea"
                      :rows="24"
                      placeholder="Markdown 方案正文"
                      class="scheme-md-editor"
                    />
                  </div>
                  <el-empty v-else description="请选择或生成测试方案" />
                </el-col>
              </el-row>
            </el-tab-pane>

            <el-tab-pane label="整体视图" name="overview">
              <div class="overview-stat-row">
                <div class="overview-stat-card">
                  <div class="stat-value">{{ overview.test_point_total || 0 }}</div>
                  <div class="stat-label">测试点</div>
                </div>
                <div class="overview-stat-card stat-confirmed">
                  <div class="stat-value">{{ overview.test_point_confirmed || 0 }}</div>
                  <div class="stat-label">已确认</div>
                </div>
                <div class="overview-stat-card stat-draft">
                  <div class="stat-value">{{ overview.test_point_draft || 0 }}</div>
                  <div class="stat-label">草稿</div>
                </div>
                <div class="overview-stat-card">
                  <div class="stat-value">{{ overview.scheme_count || 0 }}</div>
                  <div class="stat-label">测试方案</div>
                </div>
                <div class="overview-stat-card">
                  <div class="stat-value">{{ overview.case_count || 0 }}</div>
                  <div class="stat-label">功能用例</div>
                </div>
              </div>
              <el-row :gutter="16" class="overview-charts">
                <el-col :span="12">
                  <el-card shadow="never" class="chart-card">
                    <template #header><span class="card-title">测试点类型分布</span></template>
                    <div ref="typeChartRef" class="mini-chart" />
                  </el-card>
                </el-col>
                <el-col :span="12">
                  <el-card shadow="never" class="chart-card">
                    <template #header><span class="card-title">模块分布 Top</span></template>
                    <div ref="moduleChartRef" class="mini-chart" />
                  </el-card>
                </el-col>
              </el-row>
              <el-card shadow="never" class="scheme-report-card" v-if="overview.latest_scheme">
                <template #header>
                  <div class="report-card-header">
                    <div>
                      <span class="card-title">最新测试方案</span>
                      <span class="report-subtitle">{{ overview.latest_scheme.title }}</span>
                    </div>
                    <div class="report-actions">
                      <el-tag size="small" type="info">v{{ overview.latest_scheme.version }}</el-tag>
                      <el-tag size="small" :type="overview.latest_scheme.status === 'confirmed' ? 'success' : 'warning'">
                        {{ statusLabel(overview.latest_scheme.status) }}
                      </el-tag>
                      <el-button size="small" link type="primary" @click="openSchemeFromOverview">查看完整</el-button>
                      <el-button size="small" link type="primary" @click="exportOverviewScheme">导出 Word</el-button>
                    </div>
                  </div>
                </template>
                <MarkdownReport
                  :content="overview.latest_scheme.content_md || ''"
                  max-height="420px"
                />
              </el-card>
              <el-card v-else shadow="never" class="scheme-report-card empty-report">
                <el-empty description="暂无测试方案，请先在「测试方案」页生成" />
              </el-card>
              <div class="overview-footer">
                <el-button type="primary" plain @click="openCaseGenDialog">从测试点生成用例</el-button>
                <el-button
                  v-if="canImportLibrary"
                  type="success"
                  plain
                  :disabled="!overview.case_count"
                  @click="openCopyToLibraryDialog"
                >复制到用例库</el-button>
                <el-button type="primary" @click="goCases(currentReq)">查看/编辑功能用例 →</el-button>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </el-drawer>

      <el-dialog v-model="caseGenVisible" title="从测试点生成功能用例" width="560px" destroy-on-close>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="将已确认（或下方指定）的测试点展开为禅道格式功能用例，写入「AI 需求用例」同一需求下，可在需求用例页编辑与导出。"
          style="margin-bottom: 12px;"
        />
        <el-form label-width="120px">
          <el-form-item label="用例生成模型">
            <el-select v-model="caseGenForm.case_gen_config_id" placeholder="文本模型" style="width: 100%;">
              <el-option v-for="c in configList" :key="'cg'+c.id" :label="c.name" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="目标条数">
            <el-input-number v-model="caseGenForm.count" :min="1" :max="50" />
          </el-form-item>
          <el-form-item label="用例批次名">
            <el-input v-model="caseGenForm.batch_name" placeholder="如：测试点-v1，用于区分多批用例" />
          </el-form-item>
          <el-form-item label="测试点范围">
            <el-radio-group v-model="caseGenForm.scope_mode">
              <el-radio value="selected">仅当前勾选（{{ selectedPointIds.length }} 条）</el-radio>
              <el-radio value="confirmed">全部已确认</el-radio>
              <el-radio value="all">当前列表全部（含草稿）</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="需求摘录">
            <el-checkbox v-model="caseGenForm.include_requirement_excerpt">附带需求正文摘录（步骤更有依据）</el-checkbox>
          </el-form-item>
          <el-form-item label="写入策略">
            <el-checkbox v-model="caseGenForm.replace_existing">替换同批次已有用例</el-checkbox>
            <el-checkbox v-model="caseGenForm.supplement" style="margin-left: 12px;">补充生成（不删旧用例）</el-checkbox>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="caseGenVisible = false">取消</el-button>
          <el-button type="primary" :loading="caseGenLoading" @click="handleGenerateCasesFromPoints">开始生成</el-button>
        </template>
      </el-dialog>

      <el-dialog
        v-model="copyToLibraryVisible"
        title="复制到功能用例库"
        width="760px"
        destroy-on-close
        @closed="resetCopyToLibrary"
      >
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="将当前需求下工作区用例复制到「功能用例库」，原工作区数据保留；默认仅展示测试分析来源（含测试点关联）的用例。"
          style="margin-bottom: 12px;"
        />
        <div class="copy-lib-toolbar">
          <el-select
            v-model="libraryCaseSourceRef"
            clearable
            placeholder="按来源批次筛选"
            style="width: 220px;"
          >
            <el-option
              v-for="o in libraryCaseSourceOptions"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </el-select>
          <el-checkbox v-model="libraryOnlyTestPoints">仅测试点来源</el-checkbox>
          <el-button link type="primary" @click="selectAllLibraryCases">全选当前列表</el-button>
          <span class="list-hint">共 {{ filteredLibraryCases.length }} 条</span>
        </div>
        <el-table
          ref="libraryCaseTableRef"
          :data="filteredLibraryCases"
          v-loading="copyToLibraryLoading"
          stripe
          border
          max-height="360"
          row-key="id"
          @selection-change="rows => selectedLibraryCaseIds = rows.map(r => r.id)"
        >
          <el-table-column type="selection" width="45" />
          <el-table-column prop="title" label="用例标题" min-width="220" show-overflow-tooltip />
          <el-table-column label="来源" width="160" show-overflow-tooltip>
            <template #default="{ row }">
              {{ formatCaseSourceRefLabel(row.source_ref) }}
            </template>
          </el-table-column>
          <el-table-column prop="priority" label="优先级" width="72" align="center" />
          <el-table-column label="入库" width="88" align="center">
            <template #default="{ row }">
              <el-tag v-if="libraryCopyCount(row)" size="small" type="success">
                已入库×{{ libraryCopyCount(row) }}
              </el-tag>
              <span v-else class="muted-text">—</span>
            </template>
          </el-table-column>
        </el-table>
        <template #footer>
          <el-button @click="copyToLibraryVisible = false">取消</el-button>
          <el-button
            type="primary"
            :loading="importingToLibrary"
            :disabled="!selectedLibraryCaseIds.length"
            @click="handleImportToLibrary"
          >复制到用例库 ({{ selectedLibraryCaseIds.length }})</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="pointEditVisible" title="编辑测试点" width="520px" destroy-on-close>
        <el-form :model="pointEditForm" label-width="90px">
          <el-form-item label="标题"><el-input v-model="pointEditForm.title" /></el-form-item>
          <el-form-item label="类型">
            <el-select v-model="pointEditForm.test_type" style="width: 100%;">
              <el-option v-for="t in testTypes" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="优先级">
            <el-select v-model="pointEditForm.priority" style="width: 100%;">
              <el-option v-for="p in ['P0','P1','P2','P3']" :key="p" :label="p" :value="p" />
            </el-select>
          </el-form-item>
          <el-form-item label="主模块"><el-input v-model="pointEditForm.main_module" /></el-form-item>
          <el-form-item label="子模块"><el-input v-model="pointEditForm.sub_module" /></el-form-item>
          <el-form-item label="说明"><el-input v-model="pointEditForm.description" type="textarea" :rows="4" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="pointEditVisible = false">取消</el-button>
          <el-button type="primary" :loading="savingPoint" @click="savePoint">保存</el-button>
        </template>
      </el-dialog>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { testPointsCasesSourceRef, formatCaseSourceRefLabel, buildCaseSourceRefOptions, isTestPointsSourceRef } from '@/utils/aiCaseSource.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import PageCard from '@/components/PageCard.vue'
import TestPointMindMap from '@/components/TestPointMindMap.vue'
import MarkdownReport from '@/components/MarkdownReport.vue'
import { aiTestAnalysisApi, aiConfigApi, aiRequirementApi, aiFunctionalCaseApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'

const router = useRouter()
const route = useRoute()
const proStore = ProjectStore()
const uStore = UserStore()
const highlightPointId = ref(null)

const canImportLibrary = computed(() => uStore.hasPermission('ai_test:execute'))

const testTypes = ['正向', '异常', '边界', '权限', '状态', '兼容', '性能', 'API', '其他']

const listLoading = ref(false)
const reqList = ref([])
const detailVisible = ref(false)
const currentReq = ref(null)
const activeTab = ref('mindmap')

const configList = ref([])
const docSections = ref([])
const sectionTree = ref([])
const selectedSectionIds = ref([])
const sectionTreeRef = ref(null)
const scopeHint = ref('')

const genForm = reactive({
  vision_config_id: null,
  text_config_id: null,
  batch_name: '',
  count: 30,
  replace_batch: true
})
const mindmapScopeOnly = ref(true)
const mindmapFilteredTotal = ref(null)
const generating = ref(false)
const mindmapLoading = ref(false)
const echartsTree = ref(null)

const testPoints = ref([])
const testPointsTotalAll = ref(0)
const pointsLoading = ref(false)
const selectedPointIds = ref([])
const pointFilters = reactive({
  keyword: '',
  status: '',
  test_type: '',
  priority: '',
  batch_name: '',
  main_module: ''
})
const pointFilterOptions = ref({
  batches: [],
  test_types: [],
  priorities: [],
  main_modules: []
})

const schemes = ref([])
const currentScheme = ref(null)
const schemeMdEdit = ref('')
const schemeForm = reactive({
  title: '',
  text_config_id: null,
  include_unconfirmed: false
})
const schemeViewMode = ref('preview')
const schemeEnvCollapse = ref(['env'])
const schemeEnvHints = reactive({
  system_name: '',
  test_env: '',
  access_entry: '',
  deploy_version: '',
  client_requirements: '',
  accounts_roles: '',
  test_data: '',
  dependencies: '',
  tools: ''
})
const schemeGenerating = ref(false)
const savingScheme = ref(false)

const caseGenVisible = ref(false)
const caseGenLoading = ref(false)
const caseGenForm = reactive({
  case_gen_config_id: null,
  count: 20,
  batch_name: '',
  scope_mode: 'confirmed',
  include_requirement_excerpt: true,
  replace_existing: false,
  supplement: false
})

const copyToLibraryVisible = ref(false)
const copyToLibraryLoading = ref(false)
const importingToLibrary = ref(false)
const workspaceCases = ref([])
const selectedLibraryCaseIds = ref([])
const libraryCaseSourceRef = ref('')
const libraryOnlyTestPoints = ref(true)
const libraryCaseTableRef = ref(null)

const overview = reactive({
  test_point_total: 0,
  test_point_confirmed: 0,
  scheme_count: 0,
  case_count: 0,
  type_distribution: {},
  module_distribution: {},
  latest_scheme: null
})

const pointEditVisible = ref(false)
const pointEditForm = reactive({ id: null, title: '', description: '', test_type: '正向', priority: 'P2', main_module: '', sub_module: '' })
const savingPoint = ref(false)

const typeChartRef = ref(null)
const moduleChartRef = ref(null)
let typeChart = null
let moduleChart = null

const ensureProject = () => {
  if (!proStore.projectInfo?.id) {
    ElMessage.warning('请先在顶部导航栏选择项目')
    return false
  }
  return true
}

const apiErrorMsg = (e, fallback = '操作失败') =>
  e?.response?.data?.detail || e?.data?.detail || e?.data?.message || e.message || fallback

const statusLabel = (s) => ({ draft: '草案', confirmed: '已确认' }[s] || s)

const mindmapQueryParams = computed(() => {
  const params = { layout: 'section' }
  if (mindmapScopeOnly.value && selectedSectionIds.value.length) {
    params.section_ids = selectedSectionIds.value.join(',')
  }
  const batch = (genForm.batch_name || '').trim()
  if (batch) params.batch_name = batch
  return params
})

const mindmapExportParams = computed(() => {
  const p = { ...mindmapQueryParams.value }
  delete p.layout
  return p
})

function inferBatchName() {
  if (genForm.batch_name?.trim()) return
  const idSet = new Set(selectedSectionIds.value)
  const selected = docSections.value.filter(s => idSet.has(s.id))
  if (!selected.length) return
  const byId = Object.fromEntries(docSections.value.map(s => [s.id, s]))
  let top = selected[0]
  let cur = top
  while (cur?.parent_id && byId[cur.parent_id]) {
    cur = byId[cur.parent_id]
    if (idSet.has(cur.id)) top = cur
  }
  const title = (top?.title || '').trim()
  if (title) genForm.batch_name = title.slice(0, 40)
}

function buildSectionTree(sections) {
  const map = {}
  const roots = []
  for (const s of sections || []) {
    map[s.id] = { ...s, children: [] }
  }
  for (const s of sections || []) {
    const node = map[s.id]
    const pid = s.parent_id
    if (pid && map[pid]) map[pid].children.push(node)
    else roots.push(node)
  }
  return roots
}

const loadConfigs = async () => {
  try {
    const res = await aiConfigApi.getList({ size: 200 })
    if (res.data?.code === 200) configList.value = res.data.data?.list || []
  } catch (e) { console.error(e) }
}

const loadList = async () => {
  if (!ensureProject()) return
  listLoading.value = true
  try {
    const res = await aiTestAnalysisApi.getRequirements({ project_id: proStore.projectInfo.id })
    if (res.data?.code === 200) reqList.value = res.data.data?.list || []
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '加载失败'))
  } finally {
    listLoading.value = false
  }
}

const loadDocumentStructure = async () => {
  if (!currentReq.value?.id) return
  try {
    const res = await aiRequirementApi.getDocumentStructure(currentReq.value.id, proStore.projectInfo.id)
    if (res.data?.code === 200) {
      docSections.value = res.data.data?.sections || []
      sectionTree.value = buildSectionTree(docSections.value)
      selectedSectionIds.value = docSections.value.map(s => s.id)
      await nextTick()
      sectionTreeRef.value?.setCheckedKeys(selectedSectionIds.value)
    }
  } catch (e) { console.error(e) }
}

const onSectionCheck = () => {
  selectedSectionIds.value = sectionTreeRef.value?.getCheckedKeys(false) || []
  inferBatchName()
  estimateScopeHint()
  if (mindmapScopeOnly.value) loadMindmap()
}

const selectAllSections = () => {
  selectedSectionIds.value = docSections.value.map(s => s.id)
  sectionTreeRef.value?.setCheckedKeys(selectedSectionIds.value)
  estimateScopeHint()
}

const clearSections = () => {
  selectedSectionIds.value = []
  sectionTreeRef.value?.setCheckedKeys([])
  scopeHint.value = ''
}

const estimateScopeHint = async () => {
  if (!currentReq.value?.id || !selectedSectionIds.value.length) {
    scopeHint.value = ''
    return
  }
  try {
    const res = await aiRequirementApi.estimateScope(
      currentReq.value.id,
      { scope_section_ids: selectedSectionIds.value },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      const est = res.data.data || {}
      if (est.level === 'warn' || est.level === 'block') scopeHint.value = est.message || ''
      else scopeHint.value = ''
    }
  } catch (e) { /* ignore */ }
}

const loadMindmap = async () => {
  if (!currentReq.value?.id) return
  mindmapLoading.value = true
  try {
    const res = await aiTestAnalysisApi.getMindmap(
      currentReq.value.id,
      proStore.projectInfo.id,
      mindmapQueryParams.value
    )
    if (res.data?.code === 200) {
      echartsTree.value = res.data.data?.echarts_tree || { name: currentReq.value.name, children: [] }
      mindmapFilteredTotal.value = res.data.data?.total ?? null
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '加载导图失败'))
  } finally {
    mindmapLoading.value = false
  }
}

const buildPointFilterParams = () => {
  const p = {}
  if (pointFilters.keyword?.trim()) p.keyword = pointFilters.keyword.trim()
  if (pointFilters.status) p.status = pointFilters.status
  if (pointFilters.test_type) p.test_type = pointFilters.test_type
  if (pointFilters.priority) p.priority = pointFilters.priority
  if (pointFilters.batch_name) p.batch_name = pointFilters.batch_name
  if (pointFilters.main_module) p.main_module = pointFilters.main_module
  if (mindmapScopeOnly.value && selectedSectionIds.value.length) {
    p.section_ids = selectedSectionIds.value.join(',')
  }
  return p
}

const loadTestPoints = async () => {
  if (!currentReq.value?.id) return
  pointsLoading.value = true
  try {
    const res = await aiTestAnalysisApi.getTestPoints(
      currentReq.value.id,
      proStore.projectInfo.id,
      buildPointFilterParams()
    )
    if (res.data?.code === 200) {
      testPoints.value = res.data.data?.list || []
      testPointsTotalAll.value = res.data.data?.total_all ?? testPoints.value.length
      pointFilterOptions.value = res.data.data?.filter_options || pointFilterOptions.value
    }
  } finally {
    pointsLoading.value = false
  }
}

const resetPointFilters = () => {
  pointFilters.keyword = ''
  pointFilters.status = ''
  pointFilters.test_type = ''
  pointFilters.priority = ''
  pointFilters.batch_name = ''
  pointFilters.main_module = ''
  loadTestPoints()
}

const loadSchemes = async () => {
  if (!currentReq.value?.id) return
  const res = await aiTestAnalysisApi.getSchemes(currentReq.value.id, proStore.projectInfo.id)
  if (res.data?.code === 200) {
    schemes.value = res.data.data?.list || []
    if (schemes.value.length && !currentScheme.value) selectScheme(schemes.value[0])
  }
}

const loadOverview = async () => {
  if (!currentReq.value?.id) return
  const res = await aiTestAnalysisApi.getOverview(currentReq.value.id, proStore.projectInfo.id)
  if (res.data?.code === 200) {
    const d = res.data.data || {}
    Object.assign(overview, d.overview || {})
    if (activeTab.value === 'overview') renderOverviewCharts()
  }
}

const openDetail = async (row) => {
  currentReq.value = { ...row }
  detailVisible.value = true
  activeTab.value = 'mindmap'
  currentScheme.value = null
  schemeMdEdit.value = ''
  if (!schemeEnvHints.system_name) schemeEnvHints.system_name = row.name || ''
  if (!schemeForm.title) schemeForm.title = `${row.name || ''} 测试方案`
  await loadDocumentStructure()
  await loadMindmap()
  await loadTestPoints()
  await loadSchemes()
  await loadOverview()
  estimateScopeHint()
}

const handleGeneratePoints = async () => {
  if (!currentReq.value?.id || !ensureProject()) return
  if (!selectedSectionIds.value.length) {
    ElMessage.warning('请勾选章节范围')
    return
  }
  inferBatchName()
  generating.value = true
  try {
    const res = await aiTestAnalysisApi.generateTestPoints(
      currentReq.value.id,
      {
        vision_config_id: genForm.vision_config_id,
        text_config_id: genForm.text_config_id,
        scope_section_ids: selectedSectionIds.value,
        count: genForm.count,
        batch_name: genForm.batch_name,
        replace_existing: genForm.replace_batch,
        supplement: false
      },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '生成成功')
      await loadMindmap()
      await loadTestPoints()
      await loadOverview()
      await loadList()
    } else {
      ElMessage.error(res.data?.message || '生成失败')
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '生成失败'))
  } finally {
    generating.value = false
  }
}

const handleGenerateScheme = async () => {
  if (!currentReq.value?.id) return
  schemeGenerating.value = true
  try {
    const res = await aiTestAnalysisApi.generateScheme(
      currentReq.value.id,
      {
        title: schemeForm.title || `${currentReq.value.name} 测试方案`,
        text_config_id: schemeForm.text_config_id,
        include_unconfirmed_points: schemeForm.include_unconfirmed,
        scope_section_ids: selectedSectionIds.value,
        environment_hints: { ...schemeEnvHints }
      },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '方案已生成')
      schemes.value.unshift(res.data.data)
      selectScheme(res.data.data)
      await loadOverview()
      await loadList()
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '生成方案失败'))
  } finally {
    schemeGenerating.value = false
  }
}

const selectScheme = (s) => {
  currentScheme.value = s
  schemeMdEdit.value = s.content_md || ''
  schemeViewMode.value = 'preview'
}

const saveSchemeMd = async () => {
  if (!currentScheme.value) return
  savingScheme.value = true
  try {
    const res = await aiTestAnalysisApi.updateScheme(
      currentReq.value.id,
      currentScheme.value.id,
      { content_md: schemeMdEdit.value },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('已保存')
      Object.assign(currentScheme.value, res.data.data)
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '保存失败'))
  } finally {
    savingScheme.value = false
  }
}

const confirmScheme = async () => {
  if (!currentScheme.value) return
  try {
    const res = await aiTestAnalysisApi.updateScheme(
      currentReq.value.id,
      currentScheme.value.id,
      { status: 'confirmed' },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('方案已确认')
      currentScheme.value.status = 'confirmed'
      const idx = schemes.value.findIndex(s => s.id === currentScheme.value.id)
      if (idx >= 0) schemes.value[idx].status = 'confirmed'
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '确认失败'))
  }
}

const deleteCurrentScheme = async () => {
  if (!currentScheme.value) return
  const target = currentScheme.value
  try {
    await ElMessageBox.confirm(
      `确定删除方案「${target.title}」v${target.version}？删除后不可恢复。`,
      '删除确认',
      { type: 'warning' }
    )
    const res = await aiTestAnalysisApi.deleteScheme(
      currentReq.value.id,
      target.id,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('方案已删除')
      schemes.value = schemes.value.filter(s => s.id !== target.id)
      const next = schemes.value[0] || null
      currentScheme.value = next
      schemeMdEdit.value = next?.content_md || ''
      if (activeTab.value === 'overview') {
        await loadOverview()
        renderOverviewCharts()
      }
      await loadList()
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(apiErrorMsg(e, '删除失败'))
  }
}

const confirmSelected = async () => {
  if (!selectedPointIds.value.length) {
    ElMessage.warning('请先勾选测试点')
    return
  }
  try {
    const res = await aiTestAnalysisApi.batchConfirmPoints(
      currentReq.value.id,
      selectedPointIds.value,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || `已确认 ${res.data.data?.updated || selectedPointIds.value.length} 条`)
      selectedPointIds.value = []
      await loadTestPoints()
      await loadOverview()
    } else {
      ElMessage.error(res.data?.message || '确认失败')
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '确认失败'))
  }
}

const exportSchemeDocx = async () => {
  if (!currentScheme.value?.id) return
  await downloadSchemeDocx(currentScheme.value.id, currentScheme.value.title)
}

const downloadSchemeDocx = async (schemeId, title) => {
  try {
    const blob = await aiTestAnalysisApi.exportSchemeDocxBlob(
      currentReq.value.id,
      schemeId,
      proStore.projectInfo.id
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${title || '测试方案'}.docx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('Word 已下载')
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '导出失败'))
  }
}

const exportOverviewScheme = () => {
  const s = overview.latest_scheme
  if (!s?.id) return
  downloadSchemeDocx(s.id, s.title)
}

const openSchemeFromOverview = async () => {
  activeTab.value = 'scheme'
  if (!schemes.value.length) await loadSchemes()
  const s = overview.latest_scheme
  if (s?.id) {
    const found = schemes.value.find(x => x.id === s.id)
    if (found) selectScheme(found)
    else selectScheme(s)
  }
  schemeViewMode.value = 'preview'
}

const deleteSelected = async () => {
  await ElMessageBox.confirm(`确定删除 ${selectedPointIds.value.length} 条测试点？`, '确认')
  const res = await aiTestAnalysisApi.deleteTestPoints(
    currentReq.value.id,
    selectedPointIds.value,
    proStore.projectInfo.id
  )
  if (res.data?.code === 200) {
    ElMessage.success('已删除')
    selectedPointIds.value = []
    await loadMindmap()
    await loadTestPoints()
    await loadOverview()
    await loadList()
  }
}

const editPoint = (row) => {
  Object.assign(pointEditForm, {
    id: row.id,
    title: row.title,
    description: row.description,
    test_type: row.test_type,
    priority: row.priority,
    main_module: row.main_module,
    sub_module: row.sub_module
  })
  pointEditVisible.value = true
}

const savePoint = async () => {
  savingPoint.value = true
  try {
    const res = await aiTestAnalysisApi.updateTestPoint(
      currentReq.value.id,
      pointEditForm.id,
      { ...pointEditForm },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('已保存')
      pointEditVisible.value = false
      await loadMindmap()
      await loadTestPoints()
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '保存失败'))
  } finally {
    savingPoint.value = false
  }
}

const onPointNodeClick = (meta) => {
  const pt = testPoints.value.find(p => p.id === meta.point_id)
  if (pt) editPoint(pt)
}

function renderOverviewCharts() {
  nextTick(() => {
    const typeData = Object.entries(overview.type_distribution || {}).map(([name, value]) => ({ name, value }))
    const modData = Object.entries(overview.module_distribution || {}).map(([name, value]) => ({ name, value }))
    if (typeChartRef.value) {
      if (!typeChart) typeChart = echarts.init(typeChartRef.value)
      typeChart.setOption({
        tooltip: { trigger: 'item' },
        series: [{ type: 'pie', radius: '65%', data: typeData.length ? typeData : [{ name: '暂无', value: 0 }] }]
      })
    }
    if (moduleChartRef.value) {
      if (!moduleChart) moduleChart = echarts.init(moduleChartRef.value)
      moduleChart.setOption({
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: modData.map(d => d.name), axisLabel: { rotate: 30 } },
        yAxis: { type: 'value' },
        series: [{ type: 'bar', data: modData.map(d => d.value) }]
      })
    }
  })
}

watch(activeTab, (tab) => {
  if (tab === 'overview') loadOverview().then(() => renderOverviewCharts())
  if (tab === 'mindmap') loadMindmap()
  if (tab === 'points') loadTestPoints()
  if (tab === 'scheme') loadSchemes()
})

const goUpload = () => router.push('/ai-requirements')

const goCases = (row, opts = {}) => {
  const reqId = row?.id || currentReq.value?.id
  if (!reqId) return
  const query = { reqId: String(reqId) }
  if (opts.sourceRef) query.sourceRef = opts.sourceRef
  if (opts.pointId) query.pointId = String(opts.pointId)
  router.push({ path: '/ai-requirements', query })
}

const goCasesForPoint = (pointRow) => {
  goCases(currentReq.value, { pointId: pointRow.id })
}

const displayTestPoints = computed(() => {
  if (!highlightPointId.value) return testPoints.value
  return testPoints.value.filter(p => p.id === highlightPointId.value)
})

const testPointRowClass = ({ row }) =>
  highlightPointId.value && row.id === highlightPointId.value ? 'tp-row-highlight' : ''

const openCaseGenDialog = () => {
  if (!currentReq.value) return
  caseGenForm.batch_name = pointFilters.batch_name || genForm.batch_name || '测试点用例'
  caseGenForm.case_gen_config_id = caseGenForm.case_gen_config_id || genForm.text_config_id
  if (selectedPointIds.value.length) {
    caseGenForm.scope_mode = 'selected'
  } else if (overview.test_point_confirmed > 0) {
    caseGenForm.scope_mode = 'confirmed'
  } else {
    caseGenForm.scope_mode = 'all'
  }
  caseGenVisible.value = true
}

const libraryCaseSourceOptions = computed(() => buildCaseSourceRefOptions(workspaceCases.value))

const filteredLibraryCases = computed(() => {
  let rows = workspaceCases.value
  if (libraryOnlyTestPoints.value) {
    rows = rows.filter(c => isTestPointsSourceRef(c.source_ref) || (c.test_point_ids?.length > 0))
  }
  if (libraryCaseSourceRef.value) {
    rows = rows.filter(c => (c.source_ref || '') === libraryCaseSourceRef.value)
  }
  if (highlightPointId.value) {
    rows = rows.filter(c => (c.test_point_ids || []).includes(highlightPointId.value))
  }
  return rows
})

const libraryCopyCount = (row) => {
  const extra = row.extra && typeof row.extra === 'object' ? row.extra : {}
  const copies = extra.library_copies
  return Array.isArray(copies) ? copies.length : 0
}

const resetCopyToLibrary = () => {
  workspaceCases.value = []
  selectedLibraryCaseIds.value = []
  libraryCaseSourceRef.value = ''
  libraryOnlyTestPoints.value = true
}

const openCopyToLibraryFromList = async (row) => {
  currentReq.value = row
  await openCopyToLibraryDialog()
}

const openCopyToLibraryDialog = async () => {
  if (!currentReq.value || !ensureProject()) return
  copyToLibraryVisible.value = true
  copyToLibraryLoading.value = true
  selectedLibraryCaseIds.value = []
  try {
    const res = await aiRequirementApi.getCases(currentReq.value.id, proStore.projectInfo.id)
    if (res.data?.code === 200) {
      workspaceCases.value = res.data.data?.list || []
      const batch = (pointFilters.batch_name || caseGenForm.batch_name || '').trim()
      if (batch) {
        libraryCaseSourceRef.value = testPointsCasesSourceRef(batch)
      } else {
        const opts = buildCaseSourceRefOptions(workspaceCases.value).filter(
          o => isTestPointsSourceRef(o.value)
        )
        if (opts.length === 1) libraryCaseSourceRef.value = opts[0].value
      }
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '加载用例失败'))
    copyToLibraryVisible.value = false
  } finally {
    copyToLibraryLoading.value = false
  }
}

const selectAllLibraryCases = () => {
  const table = libraryCaseTableRef.value
  if (!table) return
  table.clearSelection()
  filteredLibraryCases.value.forEach(row => table.toggleRowSelection(row, true))
}

const handleImportToLibrary = async () => {
  if (!currentReq.value || !selectedLibraryCaseIds.value.length) return
  await ElMessageBox.confirm(
    `将复制选中的 ${selectedLibraryCaseIds.value.length} 条用例到「功能用例库」（工作区原数据保留）`,
    '复制到用例库',
    { type: 'info' }
  )
  importingToLibrary.value = true
  try {
    const res = await aiFunctionalCaseApi.importToLibrary(
      currentReq.value.id,
      selectedLibraryCaseIds.value,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '复制成功')
      copyToLibraryVisible.value = false
      await loadOverview()
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '复制失败'))
  } finally {
    importingToLibrary.value = false
  }
}

const handleGenerateCasesFromPoints = async () => {
  if (!currentReq.value) return
  if (!caseGenForm.case_gen_config_id) {
    ElMessage.warning('请选择用例生成模型')
    return
  }
  const payload = {
    case_gen_config_id: caseGenForm.case_gen_config_id,
    count: caseGenForm.count,
    batch_name: caseGenForm.batch_name,
    include_requirement_excerpt: caseGenForm.include_requirement_excerpt,
    replace_existing: caseGenForm.replace_existing,
    supplement: caseGenForm.supplement,
    include_unconfirmed_points: caseGenForm.scope_mode === 'all',
    test_point_ids: caseGenForm.scope_mode === 'selected' ? [...selectedPointIds.value] : []
  }
  if (caseGenForm.scope_mode === 'selected' && !payload.test_point_ids.length) {
    ElMessage.warning('请先勾选测试点，或改为「全部已确认」')
    return
  }
  caseGenLoading.value = true
  try {
    const res = await aiTestAnalysisApi.generateCasesFromTestPoints(
      currentReq.value.id,
      payload,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      const n = res.data.data?.created_count ?? 0
      ElMessage.success(`已生成 ${n} 条功能用例`)
      caseGenVisible.value = false
      await loadOverview()
      await loadList()
      try {
        await ElMessageBox.confirm(
          `已写入需求「${currentReq.value.name}」的功能用例（来源：测试点）。是否前往查看？`,
          '生成完成',
          { confirmButtonText: '前往用例', cancelButtonText: '留在此页', type: 'success' }
        )
        goCases(currentReq.value, {
          sourceRef: testPointsCasesSourceRef(caseGenForm.batch_name)
        })
      } catch {
        /* 用户选择留在此页 */
      }
    }
  } catch (e) {
    ElMessage.error(apiErrorMsg(e, '生成用例失败'))
  } finally {
    caseGenLoading.value = false
  }
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
  if (route.query.pointId) {
    highlightPointId.value = Number(route.query.pointId)
    activeTab.value = 'points'
    await loadTestPoints()
  }
}

onMounted(async () => {
  loadConfigs()
  await loadList()
  await openDetailFromRoute()
})

onBeforeUnmount(() => {
  typeChart?.dispose()
  moduleChart?.dispose()
})
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; }
.detail-panel { padding: 0 4px; }
.req-meta { margin-bottom: 12px; }
.analysis-tabs { margin-top: 8px; }
.gen-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.secondary-bar {
  margin-top: -4px;
  margin-bottom: 8px;
}
.point-filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 6px;
}
.scheme-env-collapse {
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
}
.scheme-env-form { flex-wrap: wrap; }
.scheme-env-form-block { max-width: 900px; }
.mindmap-layout {
  display: flex;
  gap: 12px;
  min-height: 480px;
}
.section-panel {
  width: 260px;
  flex-shrink: 0;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px;
  overflow: auto;
  max-height: 520px;
}
.panel-head {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
}
.map-panel { flex: 1; min-width: 0; }
.section-tree { font-size: 13px; }
.scheme-list { border: 1px solid #ebeef5; border-radius: 6px; max-height: 520px; overflow: auto; }
.scheme-item {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
}
.scheme-item.active { background: #ecf5ff; }
.scheme-item-title { font-weight: 500; font-size: 13px; }
.scheme-item-meta { font-size: 12px; color: #909399; margin-top: 4px; }
.scheme-content { border: 1px solid #ebeef5; border-radius: 6px; padding: 12px; }
.scheme-actions {
  margin-bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.mini-chart { height: 260px; }
.chart-card :deep(.el-card__header) { padding: 12px 16px; }
.card-title { font-weight: 600; font-size: 14px; color: #303133; }
.overview-stat-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.overview-stat-card {
  flex: 1;
  min-width: 100px;
  padding: 16px 20px;
  background: linear-gradient(135deg, #f5f9ff 0%, #fff 100%);
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  text-align: center;
}
.overview-stat-card.stat-confirmed {
  background: linear-gradient(135deg, #f0f9eb 0%, #fff 100%);
  border-color: #c2e7b0;
}
.overview-stat-card.stat-draft {
  background: linear-gradient(135deg, #fdf6ec 0%, #fff 100%);
  border-color: #f5dab1;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 6px;
}
.overview-charts { margin-bottom: 16px; }
.scheme-report-card {
  border-radius: 8px;
}
.scheme-report-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.report-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.report-subtitle {
  margin-left: 12px;
  font-size: 13px;
  color: #909399;
  font-weight: normal;
}
.report-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.overview-footer {
  margin-top: 16px;
  text-align: right;
}
.empty-report { padding: 24px; }
.scheme-md-editor :deep(textarea) {
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
}
.list-hint {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}
.copy-lib-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.muted-text {
  color: #c0c4cc;
}
:deep(.tp-row-highlight) {
  background-color: #ecf5ff !important;
}
</style>
