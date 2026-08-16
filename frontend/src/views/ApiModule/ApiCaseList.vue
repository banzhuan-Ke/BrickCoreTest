<template>
  <PageCard>
    <template #title>
      <el-button type="primary" size="small" @click="handleAdd" icon="Plus">用例</el-button>
    </template>
    
    <template #main>
      <div class="case-list-layout">
        <div class="case-sidebar">
          <CatalogTree
            :project-id="proStore.projectInfo.id"
            v-model="searchForm.catalog_id"
            all-node-label="全部用例"
            :show-manage="true"
            @change="handleCatalogFilter"
          />
        </div>
        <div class="case-list">
          <el-input
            v-model="searchForm.api_keyword"
            placeholder="筛选接口名称/路径"
            clearable
            style="width: 180px;"
          />
          <el-select v-model="searchForm.priority" placeholder="优先级" clearable style="width: 120px;">
            <el-option label="P0 - 核心" value="P0"/>
            <el-option label="P1 - 高" value="P1"/>
            <el-option label="P2 - 中" value="P2"/>
            <el-option label="P3 - 低" value="P3"/>
          </el-select>
          <el-select
            v-model="searchForm.tag"
            placeholder="业务标签"
            clearable
            filterable
            allow-create
            default-first-option
            style="width: 140px;"
          >
            <el-option label="压测" value="perf"/>
            <el-option label="业务链路" value="journey"/>
            <el-option label="登录" value="login"/>
          </el-select>
          <el-input
            v-model="searchForm.keyword"
            placeholder="搜索用例名称"
            clearable
            style="width: 180px;"
          />
          <el-button type="primary" @click="getCaseList" icon="Search">搜索</el-button>
          <el-button @click="resetSearch" icon="RefreshRight">重置</el-button>
          <TableColumnPicker
            :items="pickerItems"
            @toggle="setColumnVisible"
            @reorder="setPickerOrder"
            @reset="resetColumns"
          />
          <el-button
            v-if="selectedCases.length > 0"
            type="success"
            @click="handleBatchRun"
            icon="VideoPlay"
          >批量执行({{ selectedCases.length }})</el-button>
          <el-button
            v-if="selectedCases.length > 0"
            type="warning"
            plain
            @click="batchCatalogDialog.visible = true"
            icon="FolderOpened"
          >修改目录({{ selectedCases.length }})</el-button>
          <el-button
            v-if="selectedCases.length > 0"
            type="danger"
            @click="handleBatchDelete"
            icon="Delete"
          >批量删除({{ selectedCases.length }})</el-button>
          <el-button
            v-if="selectedCases.length > 0"
            type="primary"
            plain
            icon="Download"
            @click="handleBatchExport"
          >导出选中({{ selectedCases.length }})</el-button>
          <el-upload
            accept=".json"
            :show-file-list="false"
            :before-upload="handleImport"
            style="display:inline-block; margin-left:4px"
          >
            <el-button type="success" plain icon="Upload">导入用例</el-button>
          </el-upload>

        <!-- 用例列表 -->
        <el-table
          ref="caseTableRef"
          :key="tableRenderKey"
          :data="caseList"
          stripe
          v-loading="loading"
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="50" align="center" />
          <template v-for="col in activeColumns" :key="col.key">
            <el-table-column
              v-if="col.key === 'index'"
              type="index"
              label="序号"
              :index="tableRowIndex"
              :width="col.width"
            />
            <el-table-column
              v-else-if="col.key === 'name'"
              label="用例名称"
              :min-width="col.minWidth || 170"
            >
              <template #default="{ row }">
                <div class="case-name">
                  <el-tooltip
                    v-if="row.is_expired"
                    :content="`接口已更新 v${row.api_version_snapshot} → v${row.api_current_version}，请确认用例是否需要同步`"
                    placement="top"
                  >
                    <el-tag type="warning" size="small" style="margin-right:5px;cursor:default">已过期</el-tag>
                  </el-tooltip>
                  {{ row.name }}
                </div>
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.key === 'priority'"
              label="优先级"
              :width="col.width"
            >
              <template #default="{ row }">
                <el-tag :type="getPriorityType(row.priority)" size="small">{{ row.priority }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.key === 'api_info'"
              label="关联接口"
              :min-width="col.minWidth || 220"
            >
              <template #default="{ row }">
                <div class="api-info">
                  <div class="api-name-row">{{ row.api_name }}</div>
                  <div class="api-path-row">
                    <el-tag :type="getMethodType(row.api_method)" size="small">{{ row.api_method }}</el-tag>
                    <span class="api-path-text">{{ row.api_path }}</span>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.key === 'assertions'"
              label="断言数"
              :width="col.width"
            >
              <template #default="{ row }">
                {{ row.assertions?.length || 0 }}
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.key === 'request_override'"
              label="请求覆盖"
              :width="col.width"
            >
              <template #default="{ row }">
                <div class="override-tags">
                  <el-tooltip v-if="hasHeaderOverride(row)" placement="top">
                    <template #content>
                      <div class="override-tooltip">
                        <div class="tooltip-title">Header 覆盖</div>
                        <div v-for="(v, k) in getHeaderOverrides(row)" :key="k" class="tooltip-item">
                          <code>{{ k }}</code>: {{ v }}
                        </div>
                      </div>
                    </template>
                    <el-tag type="warning" size="small">Header</el-tag>
                  </el-tooltip>
                  <el-tooltip v-if="hasParamOverride(row)" placement="top">
                    <template #content>
                      <div class="override-tooltip">
                        <div class="tooltip-title">参数覆盖</div>
                        <div v-for="p in getParamOverrides(row)" :key="p.name" class="tooltip-item">
                          <code>{{ p.name }}</code>: {{ p.value }}
                        </div>
                      </div>
                    </template>
                    <el-tag type="success" size="small">Param</el-tag>
                  </el-tooltip>
                  <el-tooltip v-if="hasBodyOverride(row)" placement="top">
                    <template #content>
                      <div class="override-tooltip">
                        <div class="tooltip-title">Body 覆盖</div>
                        <pre>{{ JSON.stringify(row.request_body, null, 2) }}</pre>
                      </div>
                    </template>
                    <el-tag type="primary" size="small">Body</el-tag>
                  </el-tooltip>
                  <span v-if="!hasAnyOverride(row)" style="color: #999; font-size: 12px;">-</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.key === 'catalog_name'"
              label="所属目录"
              :width="col.width"
            >
              <template #default="{ row }">
                <el-tag v-if="row.catalog_name || row.category_name" type="info" size="small">
                  {{ row.catalog_name || row.category_name }}
                </el-tag>
                <span v-else style="color: #999;">-</span>
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.key === 'create_by'"
              label="创建人"
              :width="col.width"
            >
              <template #default="{ row }">
                {{ row.create_by || '—' }}
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.key === 'update_by'"
              label="修改人"
              :width="col.width"
            >
              <template #default="{ row }">
                {{ row.update_by || row.create_by || '—' }}
              </template>
            </el-table-column>
            <el-table-column
              v-else-if="col.key === 'update_time'"
              label="更新时间"
              :width="col.width"
            >
              <template #default="{ row }">
                {{ formatTime(row.update_time) }}
              </template>
            </el-table-column>
          </template>
          <el-table-column label="操作" width="340" fixed="right">
            <template #default="{ row }">
              <el-button-group>
                <el-button size="small" type="success" @click="handleRun(row)" icon="VideoPlay" title="执行"/>
                <el-button size="small" type="info" @click="handleCopy(row)" icon="CopyDocument" title="复制到本项目"/>
                <el-button size="small" type="warning" @click="openCopyDialog(row)" icon="FolderOpened" title="复制到其他项目"/>
                <el-button size="small" type="primary" @click="handleEdit(row)" icon="Edit" title="编辑"/>
                <el-button size="small" type="danger" @click="handleDelete(row)" icon="Delete" title="删除"/>
              </el-button-group>
            </template>
          </el-table-column>
        </el-table>
        
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="getCaseList"
          @current-change="getCaseList"
          class="pagination"
        />
        </div>
      </div>
    </template>
  </PageCard>
  
  <!-- 用例编辑弹窗 -->
  <CaseEdit
    v-model="editDialog.visible"
    :data="editDialog.data"
    :apis="apiList"
    @success="getCaseList"
  />
  
  <!-- AI 生成用例弹窗 -->
  <ApiCaseGenerator
    v-model="aiDialog.visible"
    :api-data="aiDialog.data"
    @success="getCaseList"
  />
  
  <!-- 环境选择弹窗 -->
  <el-dialog v-model="envDialog.visible" title="选择执行环境" width="640px" top="6vh" destroy-on-close class="env-select-dialog">
    <el-form :model="envDialog" label-width="100px">
      <el-form-item label="执行环境" required>
        <el-select v-model="envDialog.env_id" placeholder="选择执行环境" style="width: 100%">
          <el-option
            v-for="env in proStore.envList"
            :key="env.id"
            :label="envAuthLabel(env)"
            :value="env.id"
          />
        </el-select>
        <div class="env-auth-hint">
          Token 授权按<strong>环境</strong>绑定。用例 Header 里的
          <code v-pre>${{token1}}</code>
          只有选中授权所在环境时才会注入；调试授权成功不等于已写入缓存（编辑态调试会写入）。
        </div>
        <el-alert
          v-if="envAuthHint"
          :type="envAuthHint.type"
          :closable="false"
          show-icon
          style="margin-top: 8px;"
          :title="envAuthHint.title"
        />
      </el-form-item>
      <el-form-item label="Schema 校验">
        <el-checkbox v-model="envDialog.auto_validate_schema">自动校验响应 Schema</el-checkbox>
      </el-form-item>
      <el-form-item v-if="!envDialog.isBatch" label="数据驱动">
        <el-checkbox v-model="envDialog.propagate_extracted">行间传递提取变量</el-checkbox>
        <div class="field-hint-sm">数据驱动多轮执行时，上一行 extract 结果传入下一行</div>
      </el-form-item>
    </el-form>
    <VariablePreviewPanel
      v-if="envDialog.env_id"
      :env-id="envDialog.env_id"
    />
    <div v-if="envDialog.env_id" class="env-dialog-actions">
      <VarInsertButton
        :env-id="envDialog.env_id"
        label="插入变量"
      />
      <el-button type="primary" link size="small" @click="varEditVisible = true" icon="Edit">编辑环境变量</el-button>
    </div>
    <template #footer>
      <el-button @click="envDialog.visible = false">取消</el-button>
      <el-button type="primary" @click="confirmRun" :loading="envLoading">执行</el-button>
    </template>
  </el-dialog>
  
  <EnvVarQuickEdit v-model="varEditVisible" :env-id="envDialog.env_id" />

  <BatchCatalogDialog
    v-model="batchCatalogDialog.visible"
    :case-ids="selectedCases.map((item) => item.id)"
    :project-id="proStore.projectInfo.id"
    :submit-fn="httpCaseApi.batchUpdateCatalog"
    @success="handleBatchCatalogSuccess"
  />

  <!-- 批量执行结果弹窗 -->
  <BatchRunResultDialog v-model="batchRunDialog.visible" :result-data="batchRunDialog.result" />

  <!-- 执行结果弹窗 -->
  <el-dialog
    v-model="runDialog.visible"
    title="执行结果"
    width="1180px"
    top="4vh"
    class="run-result-dialog"
    destroy-on-close
    @closed="runDialog.result = null; runDialog.activeTab = 'request'; runDialog.isDataDriven = false; runDialog.ddDetailIndex = null; runDialog.responseHighlight = ''"
  >
    <div v-if="runDialog.result">

      <!-- ===== 数据驱动多轮视图 ===== -->
      <template v-if="runDialog.isDataDriven">

        <!-- 单轮详情（点击"详情"后展开） -->
        <template v-if="runDialog.ddDetailIndex !== null">
          <div class="dd-back-row">
            <el-button size="small" @click="runDialog.ddDetailIndex = null; runDialog.activeTab = 'request'" icon="ArrowLeft">返回汇总</el-button>
            <span class="dd-round-label">
              第 {{ runDialog.ddDetailIndex + 1 }} 轮
              <span v-if="runDialog.result.results[runDialog.ddDetailIndex]?.data_row_label" style="color:#909399;">
                &nbsp;·&nbsp;{{ runDialog.result.results[runDialog.ddDetailIndex].data_row_label }}
              </span>
            </span>
          </div>
          <div class="run-result">
            <div class="result-header">
              <el-tag :type="runDialog.result.results[runDialog.ddDetailIndex]?.status === 'success' ? 'success' : 'danger'" size="large">
                {{ runDialog.result.results[runDialog.ddDetailIndex]?.status === 'success' ? '执行成功' : '执行失败' }}
              </el-tag>
              <RunTimingBadges :result="runDialog.result.results[runDialog.ddDetailIndex]" />
              <span v-if="runDialog.result.results[runDialog.ddDetailIndex]?.response_status" class="response-status">
                状态码: {{ runDialog.result.results[runDialog.ddDetailIndex].response_status }}
              </span>
            </div>
            <div
              v-if="runDialog.result.results[runDialog.ddDetailIndex]?.request_detail?.stage_timings"
              class="run-stage-timings-wrap"
            >
              <CaseStageTimings
                :timings="runDialog.result.results[runDialog.ddDetailIndex].request_detail.stage_timings"
                :result="runDialog.result.results[runDialog.ddDetailIndex]"
              />
            </div>
            <el-tabs v-model="runDialog.activeTab" class="result-tabs">
              <el-tab-pane label="请求详情" name="request">
                <div class="run-tab-panel" v-if="runDialog.result.results[runDialog.ddDetailIndex]?.request_detail">
                  <div class="detail-block">
                    <div class="detail-title">请求 URL</div>
                    <div class="detail-content">
                      <div class="compare-row">
                        <span class="label">原始:</span>
                        <code class="original">{{ runDialog.result.results[runDialog.ddDetailIndex].request_detail.url?.original || '-' }}</code>
                      </div>
                      <div class="compare-row">
                        <span class="label">最终:</span>
                        <code class="final">{{ runDialog.result.results[runDialog.ddDetailIndex].request_detail.url?.final || '-' }}</code>
                      </div>
                    </div>
                  </div>
                  <div class="detail-block" v-if="runDialog.result.results[runDialog.ddDetailIndex].request_detail.script_logs?.length > 0">
                    <div class="detail-title">脚本日志</div>
                    <div class="detail-content">
                      <pre style="color:#67c23a; white-space: pre-wrap;">{{ runDialog.result.results[runDialog.ddDetailIndex].request_detail.script_logs.join('\n') }}</pre>
                    </div>
                  </div>
                </div>
                <el-empty v-else description="暂无请求详情"/>
              </el-tab-pane>
              <el-tab-pane label="断言结果" name="assertions">
                <div class="assertions-section" v-if="runDialog.result.results[runDialog.ddDetailIndex]?.assertions?.length > 0">
                  <el-table :data="runDialog.result.results[runDialog.ddDetailIndex].assertions" size="small" border>
                    <el-table-column label="结果" width="70">
                      <template #default="{ row }">
                        <el-tag :type="row.passed ? 'success' : 'danger'" size="small">{{ row.passed ? '通过' : '失败' }}</el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column label="类型" width="100" prop="type"/>
                    <el-table-column label="目标" prop="target"/>
                    <el-table-column label="期望" prop="expected"/>
                    <el-table-column label="实际" min-width="180">
                      <template #default="{ row }">
                        <AssertionActualCell :row="row" />
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
                <el-empty v-else description="无断言"/>
              </el-tab-pane>
              <el-tab-pane v-if="runResponseDetail" label="响应详情" name="response">
                <div class="run-tab-panel run-tab-panel--response">
                  <div class="detail-block">
                    <div class="detail-title">响应信息</div>
                    <el-descriptions border size="small">
                      <el-descriptions-item label="状态码">
                        {{ runResponseDetail.status_code ?? runDialog.result.results[runDialog.ddDetailIndex]?.response_status ?? '-' }}
                      </el-descriptions-item>
                      <el-descriptions-item label="接口耗时">
                        {{ formatTimingMs(getHttpResponseMs(runDialog.result.results[runDialog.ddDetailIndex])) }}
                      </el-descriptions-item>
                      <el-descriptions-item label="用例总耗时">
                        {{ formatTimingMs(getCaseTotalMs(runDialog.result.results[runDialog.ddDetailIndex])) }}
                      </el-descriptions-item>
                    </el-descriptions>
                  </div>
                  <div class="detail-block" v-if="hasRunResponseHeaders">
                    <div class="detail-title">响应 Headers</div>
                    <CopyablePre :text="runResponseDetail.headers" max-height="280px" wrap />
                  </div>
                  <div class="detail-block">
                    <div class="detail-title">响应 Body</div>
                    <ResponseBodyViewer
                      :body="runResponseDetail.body"
                      :highlight-text="runDialog.responseHighlight"
                      fill
                      min-height="360px"
                      max-height="72vh"
                    />
                  </div>
                </div>
              </el-tab-pane>
              <el-tab-pane v-if="runDialog.result.results[runDialog.ddDetailIndex]?.error" label="错误信息" name="error">
                <el-alert :title="runDialog.result.results[runDialog.ddDetailIndex].error" type="error" show-icon :closable="false"/>
              </el-tab-pane>
            </el-tabs>
          </div>
        </template>

        <!-- 多轮汇总表格 -->
        <template v-else>
          <el-row :gutter="12" style="margin-bottom: 16px;">
            <el-col :span="8">
              <el-card shadow="never" class="dd-stat-card">
                <div class="dd-stat-label">总轮次</div>
                <div class="dd-stat-value">{{ runDialog.result.total_rows }}</div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never" class="dd-stat-card">
                <div class="dd-stat-label" style="color: var(--el-color-success);">成功</div>
                <div class="dd-stat-value" style="color: var(--el-color-success);">{{ runDialog.result.success }}</div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never" class="dd-stat-card">
                <div class="dd-stat-label" style="color: var(--el-color-danger);">失败</div>
                <div class="dd-stat-value" style="color: var(--el-color-danger);">{{ runDialog.result.failed }}</div>
              </el-card>
            </el-col>
          </el-row>
          <el-table :data="runDialog.result.results" border size="small">
            <el-table-column label="轮次" width="60" align="center">
              <template #default="{ row }">{{ (row.data_run_index ?? 0) + 1 }}</template>
            </el-table-column>
            <el-table-column label="数据摘要" min-width="220">
              <template #default="{ row }">
                <span style="color:#606266; font-size:12px;">{{ row.data_row_label || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.status === 'success' ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="响应码" width="80" align="center" prop="response_status"/>
            <el-table-column label="耗时(ms)" width="120" align="center">
              <template #default="{ row }">
                <div v-if="getHttpResponseMs(row) != null" class="timing-cell timing-cell--http">
                  接口 {{ getHttpResponseMs(row).toFixed(0) }}
                </div>
                <div v-if="getCaseTotalMs(row) != null" class="timing-cell timing-cell--total">
                  总 {{ getCaseTotalMs(row).toFixed(0) }}
                </div>
                <span v-if="getHttpResponseMs(row) == null && getCaseTotalMs(row) == null">-</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center">
              <template #default="{ $index }">
                <el-button link type="primary" size="small" @click="runDialog.ddDetailIndex = $index; runDialog.activeTab = 'request'">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </template>

      <!-- ===== 普通单次执行视图（原有内容保持不变）===== -->
      <template v-else>
        <div class="run-result">
          <!-- 基本信息 -->
          <div class="result-header">
            <el-tag :type="runDialog.result.status === 'success' ? 'success' : 'danger'" size="large">
              {{ runDialog.result.status === 'success' ? '执行成功' : '执行失败' }}
            </el-tag>
            <RunTimingBadges :result="runDialog.result" />
            <span v-if="runDialog.result.response_status" class="response-status">
              状态码: {{ runDialog.result.response_status }}
            </span>
          </div>

          <div
            v-if="runDialog.result.request_detail?.stage_timings"
            class="run-stage-timings-wrap"
          >
            <CaseStageTimings
              :timings="runDialog.result.request_detail.stage_timings"
              :result="runDialog.result"
            />
          </div>

          <!-- 详情标签页 -->
          <el-tabs v-model="runDialog.activeTab" class="result-tabs">
            <!-- 请求详情 -->
            <el-tab-pane label="请求详情" name="request">
              <div class="run-tab-panel" v-if="runDialog.result?.request_detail">
                <!-- URL -->
                <div class="detail-block">
                  <div class="detail-title-row">
                    <div class="detail-title">请求 URL</div>
                    <CopyTextButton :text="runDialog.result.request_detail.url?.final || runDialog.result.request_detail.url?.original || ''" />
                  </div>
                  <div class="detail-content">
                    <div class="compare-row">
                      <span class="label">原始:</span>
                      <code class="original">{{ runDialog.result.request_detail.url?.original || '-' }}</code>
                    </div>
                    <div class="compare-row">
                      <span class="label">最终:</span>
                      <code class="final">{{ runDialog.result.request_detail.url?.final || '-' }}</code>
                    </div>
                  </div>
                </div>

                <!-- Headers -->
                <div class="detail-block" v-if="Object.keys(runDialog.result.request_detail.headers?.final || {}).length > 0">
                  <div class="detail-title">请求 Headers</div>
                  <CopyablePre
                    :text="runDialog.result.request_detail.headers?.final || {}"
                    max-height="320px"
                    wrap
                  />
                </div>

                <!-- Params -->
                <div class="detail-block" v-if="Object.keys(runDialog.result.request_detail.params?.final || {}).length > 0">
                  <div class="detail-title">请求参数</div>
                  <CopyablePre
                    :text="runDialog.result.request_detail.params?.final || {}"
                    max-height="320px"
                    wrap
                  />
                </div>

                <!-- Body -->
                <div class="detail-block" v-if="runDialog.result.request_detail.body_type === 'form-data' && runDialog.result.request_detail.body_fields?.final?.length">
                  <div class="detail-title">Form Data 字段</div>
                  <CopyablePre
                    :text="runDialog.result.request_detail.body_fields.final"
                    max-height="320px"
                    wrap
                  />
                </div>
                <div class="detail-block" v-else-if="runDialog.result.request_detail.body?.final">
                  <div class="detail-title">请求 Body</div>
                  <CopyablePre
                    :text="runDialog.result.request_detail.body?.final"
                    max-height="360px"
                    wrap
                  />
                </div>

                <!-- 脚本日志 -->
                <div class="detail-block" v-if="runDialog.result.request_detail.script_logs?.length > 0">
                  <div class="detail-title">脚本日志</div>
                  <CopyablePre
                    :text="runDialog.result.request_detail.script_logs.join('\n')"
                    max-height="240px"
                    wrap
                  />
                </div>
              </div>
              <el-empty v-else description="暂无请求详情"/>
            </el-tab-pane>

            <!-- 变量替换 -->
            <el-tab-pane label="变量替换" name="variables">
              <div class="run-tab-panel" v-if="runDialog.result?.request_detail">
                <div class="detail-block" v-if="runVariablesUsedRows.length > 0">
                  <div class="detail-title">环境变量</div>
                  <el-table :data="runVariablesUsedRows" size="small" border class="run-kv-table">
                    <el-table-column label="变量名" prop="key" width="160" show-overflow-tooltip />
                    <el-table-column label="值" prop="value" min-width="200" show-overflow-tooltip />
                  </el-table>
                </div>
                <el-empty v-else description="没有使用环境变量"/>

                <div class="detail-block">
                  <div class="detail-title">替换详情</div>
                  <el-empty v-if="!runDialog.result.request_detail.replacements?.length" description="没有变量替换"/>
                  <el-table
                    v-else
                    :data="runDialog.result.request_detail.replacements"
                    size="small"
                    border
                    class="run-kv-table"
                  >
                    <el-table-column label="变量名" prop="key" width="120" show-overflow-tooltip />
                    <el-table-column label="原始值" prop="original" min-width="140" show-overflow-tooltip />
                    <el-table-column label="替换后" prop="replaced" min-width="140" show-overflow-tooltip />
                    <el-table-column label="位置" prop="path" width="100" show-overflow-tooltip />
                  </el-table>
                </div>
              </div>
              <el-empty v-else description="暂无变量替换信息"/>
            </el-tab-pane>
        
        <!-- 响应详情 -->
        <el-tab-pane label="响应详情" name="response">
          <div v-if="runResponseDetail" class="run-tab-panel run-tab-panel--response">
            <div class="detail-block">
              <div class="detail-title">响应信息</div>
              <el-descriptions border size="small">
                <el-descriptions-item label="状态码">{{ runResponseDetail.status_code }}</el-descriptions-item>
                <el-descriptions-item label="接口耗时">
                  {{ formatTimingMs(getHttpResponseMs(runDialog.result)) }}
                </el-descriptions-item>
                <el-descriptions-item label="用例总耗时">
                  {{ formatTimingMs(getCaseTotalMs(runDialog.result)) }}
                </el-descriptions-item>
              </el-descriptions>
            </div>
            <div class="detail-block" v-if="hasRunResponseHeaders">
              <div class="detail-title">响应 Headers</div>
              <CopyablePre :text="runResponseDetail.headers" max-height="280px" wrap />
            </div>
            <div class="detail-block">
              <div class="detail-title">响应 Body</div>
              <ResponseBodyViewer
                :body="runResponseDetail.body"
                :highlight-text="runDialog.responseHighlight"
                fill
                min-height="360px"
                max-height="72vh"
              />
            </div>
          </div>
          <el-empty v-else description="暂无响应详情"/>
        </el-tab-pane>
        
        <!-- 断言结果 -->
        <el-tab-pane label="断言结果" name="assertions">
          <div class="run-tab-panel">
          <div class="assertions-section" v-if="runDialog.result.assertions?.length > 0">
            <el-table :data="runDialog.result.assertions" size="small" border class="run-kv-table">
              <el-table-column label="类型" width="100" prop="type"/>
              <el-table-column label="目标" width="150" prop="target"/>
              <el-table-column label="操作符" width="80" prop="operator"/>
              <el-table-column label="期望值" width="120" prop="expected"/>
              <el-table-column label="实际值" min-width="200">
                <template #default="{ row }">
                  <AssertionActualCell :row="row" />
                </template>
              </el-table-column>
              <el-table-column label="结果" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.passed ? 'success' : 'danger'" size="small">
                    {{ row.passed ? '通过' : '失败' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <el-empty v-else description="没有配置断言"/>
          </div>
        </el-tab-pane>
        
        <!-- 提取变量 -->
        <el-tab-pane label="提取变量" name="extracted">
          <div class="run-tab-panel">
          <div class="extracted-section" v-if="runExtractorResultRows.length > 0">
            <el-table :data="runExtractorResultRows" size="small" border class="run-kv-table">
              <el-table-column label="变量名" prop="name" width="120" show-overflow-tooltip />
              <el-table-column label="来源" prop="source" width="80" />
              <el-table-column label="路径" prop="path" min-width="140" show-overflow-tooltip />
              <el-table-column label="状态" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                    {{ row.success ? '成功' : '失败' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="值" min-width="120" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.success ? formatActual(row.value) : '—' }}
                </template>
              </el-table-column>
              <el-table-column label="说明" prop="error" min-width="140" show-overflow-tooltip />
            </el-table>
          </div>
          <div class="extracted-section" v-else-if="runExtractedVarRows.length > 0">
            <el-table :data="runExtractedVarRows" size="small" border class="run-kv-table">
              <el-table-column label="变量名" prop="key" width="160" show-overflow-tooltip />
              <el-table-column label="值" prop="value" min-width="200" show-overflow-tooltip />
            </el-table>
          </div>
          <el-empty v-else description="没有提取到变量"/>
          </div>
        </el-tab-pane>
        
        <!-- 重试信息 -->
        <el-tab-pane v-if="runDialog.result?.request_detail?.retry_info?.retry_count > 0" label="重试信息" name="retry">
          <div class="run-tab-panel retry-section">
            <div class="retry-summary">
              共重试 {{ runDialog.result.request_detail.retry_info.retry_count }} 次，共 {{ runDialog.result.request_detail.retry_info.total_attempts }} 次尝试
            </div>
            <div class="retry-timeline">
              <div
                v-for="(attempt, idx) in runDialog.result.request_detail.retry_info.attempts"
                :key="idx"
                class="retry-item"
                :class="attempt.status"
              >
                <div class="retry-dot" :class="attempt.status"></div>
                <div class="retry-content">
                  <div class="retry-title">
                    第 {{ idx + 1 }} 次尝试
                    <el-tag :type="attempt.status === 'success' ? 'success' : (attempt.status === 'error' ? 'danger' : 'warning')" size="small">
                      {{ attempt.status === 'success' ? '成功' : (attempt.status === 'error' ? '异常' : '失败') }}
                    </el-tag>
                    <span v-if="attempt.response_status" class="retry-status-code">HTTP {{ attempt.response_status }}</span>
                    <span v-if="attempt.response_time != null" class="retry-time">{{ attempt.response_time.toFixed ? attempt.response_time.toFixed(0) : attempt.response_time }}ms</span>
                  </div>
                  <div v-if="attempt.error" class="retry-error">{{ attempt.error }}</div>
                  <div v-if="attempt.assertion_total > 0" class="retry-assertions">
                    断言: {{ attempt.assertion_passed }}/{{ attempt.assertion_total }} 通过
                    <span
                      v-for="(a, ai) in (attempt.assertions || [])"
                      :key="ai"
                      class="retry-assert-badge"
                      :class="a.passed ? 'passed' : 'failed'"
                    >
                      {{ a.target || a.type }}
                      <span class="assert-op">{{ a.operator }}</span>
                      <span class="assert-expected">{{ a.expected }}</span>
                      <span v-if="!a.passed" class="assert-actual">实际: {{ a.actual }}</span>
                    </span>
                  </div>
                  <div v-if="attempt.response_body !== undefined && attempt.response_body !== null" class="retry-body">
                    <details>
                      <summary style="cursor:pointer;font-size:12px;color:#909399;">响应 Body</summary>
                      <div class="code-viewer" style="margin-top:6px;">
                        <pre class="code-viewer-pre">{{ formatRunResponseBody(attempt.response_body) }}</pre>
                      </div>
                    </details>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- 错误信息 -->
        <el-tab-pane v-if="runDialog.result.error" label="错误信息" name="error">
          <div class="run-tab-panel">
            <el-alert :title="runDialog.result.error" type="error" show-icon :closable="false"/>
          </div>
        </el-tab-pane>
      </el-tabs>
        </div><!-- /run-result -->
      </template><!-- /v-else 普通单次执行 -->
    </div><!-- /v-if runDialog.result -->
    <template #footer>
      <el-button @click="runDialog.visible = false">关闭</el-button>
    </template>
  </el-dialog>

  <!-- 导入结果弹窗 -->
  <el-dialog v-model="importResultDlg.visible" title="导入结果" width="500px" destroy-on-close>
    <div v-if="importResultDlg.result">
      <el-descriptions :column="2" border size="small" style="margin-bottom: 16px;">
        <el-descriptions-item label="成功">
          <el-tag type="success">{{ importResultDlg.result.success }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="失败">
          <el-tag type="danger">{{ importResultDlg.result.failed }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <div v-if="importResultDlg.result.created_names?.length">
        <div style="font-size:13px; font-weight:500; margin-bottom:6px;">已创建用例：</div>
        <el-tag
          v-for="name in importResultDlg.result.created_names"
          :key="name"
          size="small"
          style="margin: 2px 4px 2px 0;"
        >{{ name }}</el-tag>
      </div>
      <div v-if="importResultDlg.result.warnings?.length" style="margin-top:12px;">
        <div style="font-size:13px; font-weight:500; color:#e6a23c; margin-bottom:6px;">警告：</div>
        <div v-for="(w, i) in importResultDlg.result.warnings" :key="i" style="font-size:12px; color:#e6a23c; margin-bottom:4px;">· {{ w }}</div>
      </div>
      <div v-if="importResultDlg.result.errors?.length" style="margin-top:12px;">
        <div style="font-size:13px; font-weight:500; color:#f56c6c; margin-bottom:6px;">错误：</div>
        <div v-for="(e, i) in importResultDlg.result.errors" :key="i" style="font-size:12px; color:#f56c6c; margin-bottom:4px;">· {{ e }}</div>
      </div>
    </div>
    <template #footer>
      <el-button type="primary" @click="importResultDlg.visible = false">确定</el-button>
    </template>
  </el-dialog>

  <CopyToProjectDialog
    v-model="copyDialog.visible"
    title="复制接口用例到其他项目"
    :asset-name="copyDialog.row?.name"
    :submit-fn="submitCopyCase"
    @success="getCaseList"
  />
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'
import { httpCaseApi } from '@/api/modules/http'
import dateTools from '@/tools/dateTools'
import PageCard from '@/components/PageCard.vue'
import TableColumnPicker from '@/components/TableColumnPicker.vue'
import CatalogTree from '@/components/CatalogTree.vue'
import { useTableColumns } from '@/composables/useTableColumns.js'
import { makeTableRowIndex } from '@/utils/tableIndex'
import CaseEdit from './components/CaseEdit.vue'
import ApiCaseGenerator from '@/views/AI/components/ApiCaseGenerator.vue'
import EnvVarQuickEdit from '@/components/EnvVarQuickEdit.vue'
import VarInsertButton from '@/components/VarInsertButton.vue'
import VariablePreviewPanel from '@/components/VariablePreviewPanel.vue'
import BatchRunResultDialog from './components/BatchRunResultDialog.vue'
import BatchCatalogDialog from '@/components/BatchCatalogDialog.vue'
import CopyToProjectDialog from '@/components/CopyToProjectDialog.vue'
import CopyTextButton from '@/components/CopyTextButton.vue'
import CopyablePre from '@/components/CopyablePre.vue'
import ResponseBodyViewer from '@/components/ResponseBodyViewer.vue'
import AssertionActualCell from '@/components/AssertionActualCell.vue'
import { formatResponseJson } from './utils/formatResponse'
import RunTimingBadges from './components/RunTimingBadges.vue'
import CaseStageTimings from './components/CaseStageTimings.vue'
import { getHttpResponseMs, getCaseTotalMs, formatTimingMs } from './utils/runTiming'
import { provideAssertionResponseLocate } from '@/composables/assertionResponseLocate.js'
import { httpAuthConfigApi } from '@/api/modules/httpAuth.js'

const {
  activeColumns,
  pickerItems,
  tableRenderKey,
  setColumnVisible,
  setPickerOrder,
  resetColumns
} = useTableColumns('api.cases')

const proStore = ProjectStore()
const route = useRoute()

const searchForm = reactive({
  api_id: null,
  api_keyword: '',
  catalog_id: null,
  priority: null,
  tag: null,
  keyword: ''
})

const pagination = reactive({
  page: 1,
  size: 20,
  total: 0
})

const tableRowIndex = makeTableRowIndex(pagination)

const caseList = ref([])
const apiList = ref([])
const loading = ref(false)
const envLoading = ref(false)
const selectedCases = ref([])

const caseTableRef = ref(null)
const editDialog = reactive({ visible: false, data: null })

/** 兼容旧执行结果：response_detail 为空时从 retry_info 最后一次尝试取响应 */
const pickNonEmptyHeaders = (...candidates) => {
  for (const headers of candidates) {
    if (!headers) continue
    if (Array.isArray(headers) && headers.length) return headers
    if (typeof headers === 'object' && Object.keys(headers).length) return headers
    if (typeof headers === 'string' && headers.trim()) return headers
  }
  return null
}

const getEffectiveResponseDetail = (result) => {
  if (!result) return null
  const attempts =
    result.request_detail?.retry_info?.attempts
    || result.retry_info?.attempts
  const last = attempts?.length ? attempts[attempts.length - 1] : null
  const lastHeaders = last
    ? pickNonEmptyHeaders(last.response_headers, last.headers)
    : null

  if (result.response_detail) {
    const detail = { ...result.response_detail }
    const headers = pickNonEmptyHeaders(detail.headers, result.response_headers, lastHeaders)
    if (headers) detail.headers = headers
    if (detail.status_code == null && result.response_status != null) {
      detail.status_code = result.response_status
    }
    return detail
  }
  if (result.response_headers || result.response_body != null || result.response_status != null) {
    return {
      status_code: result.response_status,
      http_time: getHttpResponseMs(result),
      total_time: getCaseTotalMs(result),
      time: getHttpResponseMs(result),
      body: result.response_body,
      headers: pickNonEmptyHeaders(result.response_headers, lastHeaders) || {},
    }
  }
  if (attempts?.length) {
    if (
      last.response_body !== undefined && last.response_body !== null
      || lastHeaders
      || last.response_status != null
    ) {
      return {
        status_code: last.response_status ?? result.response_status,
        http_time: getHttpResponseMs(result),
        total_time: getCaseTotalMs(result),
        time: getHttpResponseMs(result),
        body: last.response_body,
        headers: pickNonEmptyHeaders(last.response_headers, last.headers) || {},
      }
    }
  }
  return null
}

const hasRunResponseHeaders = computed(() => {
  const headers = runResponseDetail.value?.headers
  if (!headers) return false
  if (Array.isArray(headers)) return headers.length > 0
  if (typeof headers === 'object') return Object.keys(headers).length > 0
  return String(headers).trim().length > 0
})

const runDialog = reactive({
  visible: false,
  result: null,
  activeTab: 'request',
  isDataDriven: false,
  ddDetailIndex: null,
  responseHighlight: '',
})
const runResponseDetail = computed(() => {
  const result = runDialog.result
  if (!result) return null
  if (runDialog.isDataDriven && runDialog.ddDetailIndex !== null) {
    return getEffectiveResponseDetail(result.results?.[runDialog.ddDetailIndex])
  }
  return getEffectiveResponseDetail(result)
})

function locateExpectedInRunResponse(expected) {
  const term = String(expected ?? '').trim()
  if (!term || !runResponseDetail.value) return false
  runDialog.responseHighlight = term
  runDialog.activeTab = 'response'
  return true
}

provideAssertionResponseLocate(locateExpectedInRunResponse)
const formatRunResponseBody = (body) => formatResponseJson(body)

const runVariablesUsedRows = computed(() => {
  const vars = runDialog.result?.request_detail?.variables_used
  if (!vars || typeof vars !== 'object') return []
  return Object.entries(vars).map(([key, value]) => ({
    key,
    value: value === null || value === undefined ? '' : String(value)
  }))
})

const runExtractedVarRows = computed(() => {
  const vars = runDialog.result?.extracted_vars
  if (!vars || typeof vars !== 'object') return []
  return Object.entries(vars).map(([key, value]) => ({
    key,
    value: value === null || value === undefined ? '' : String(value)
  }))
})

const runExtractorResultRows = computed(() => {
  const result = runDialog.result
  if (!result) return []
  if (runDialog.isDataDriven && runDialog.ddDetailIndex !== null) {
    const row = result.results?.[runDialog.ddDetailIndex]
    return row?.extractor_results || row?.request_detail?.extractor_results || []
  }
  const rows = result.extractor_results || result.request_detail?.extractor_results
  return Array.isArray(rows) ? rows : []
})
const batchRunDialog = reactive({ visible: false, result: null })
const batchCatalogDialog = reactive({ visible: false })
const copyDialog = reactive({ visible: false, row: null })
const envDialog = reactive({
  visible: false,
  env_id: null,
  case: null,
  isBatch: false,
  auto_validate_schema: false,
  propagate_extracted: true,
})
const authConfigsByEnv = ref({}) // environment_id -> { name, is_enabled, vars }
const envAuthHint = computed(() => {
  const envId = envDialog.env_id
  if (!envId) return null
  const cfg = authConfigsByEnv.value[envId]
  if (!cfg) {
    return {
      type: 'warning',
      title: '当前环境未配置/未启用 Token 授权；若 Header 使用了授权变量将无法替换',
    }
  }
  if (!cfg.is_enabled) {
    return {
      type: 'warning',
      title: `授权「${cfg.name}」未启用`,
    }
  }
  const vars = (cfg.var_names || []).join('、') || '（见提取规则）'
  return {
    type: 'success',
    title: `将注入授权「${cfg.name}」变量：${vars}`,
  }
})

const envAuthLabel = (env) => {
  const cfg = authConfigsByEnv.value[env.id]
  if (cfg?.is_enabled) return `${env.name}（Token 授权）`
  return env.name
}

const loadAuthConfigsForRun = async () => {
  authConfigsByEnv.value = {}
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  try {
    const res = await httpAuthConfigApi.getList({ project_id: projectId, page: 1, size: 100 })
    const list = res.data?.data?.list || res.data?.list || []
    const map = {}
    for (const row of list) {
      if (!row?.environment_id) continue
      const names = (row.extractors || []).map(e => e?.name).filter(Boolean)
      // 同环境多条时优先已启用且更新较新的（接口已按 update_time 排）
      if (!map[row.environment_id] || (row.is_enabled && !map[row.environment_id].is_enabled)) {
        map[row.environment_id] = {
          name: row.name,
          is_enabled: !!row.is_enabled,
          var_names: names,
        }
      }
    }
    authConfigsByEnv.value = map
  } catch {
    authConfigsByEnv.value = {}
  }
}

const pickDefaultRunEnvId = () => {
  const envs = proStore.envList || []
  if (!envs.length) return null
  const enabledEnvId = Object.keys(authConfigsByEnv.value)
    .map(Number)
    .find((id) => authConfigsByEnv.value[id]?.is_enabled && envs.some((e) => e.id === id))
  if (enabledEnvId) return enabledEnvId
  return envs[0]?.id || null
}
const aiDialog = reactive({ visible: false, data: null })
const varEditVisible = ref(false)
const importResultDlg = reactive({ visible: false, result: null })

const formatTime = (time) => {
  return time ? dateTools.rTime(time) : '-'
}

const formatActual = (val, truncate = false) => {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'object') {
    const str = JSON.stringify(val)
    if (truncate && str.length > 40) return str.slice(0, 40) + '...'
    return str
  }
  return String(val)
}

const getApiList = async () => {
  try {
    const res = await http.apiModuleApi.getApiList({
      project_id: proStore.projectInfo.id,
      page: 1,
      size: 1000
    })
    if (res.status === 200) {
      apiList.value = res.data.data
    }
  } catch (error) {
    console.error('获取接口列表失败:', error)
  }
}

const getCaseList = async () => {
  loading.value = true
  try {
    const params = {
      project_id: proStore.projectInfo.id,
      page: pagination.page,
      size: pagination.size,
      keyword: searchForm.keyword || undefined
    }
    if (searchForm.catalog_id) {
      params.catalog_id = searchForm.catalog_id
    }
    if (searchForm.api_id) {
      params.api_id = searchForm.api_id
    }
    if (searchForm.priority) {
      params.priority = searchForm.priority
    }
    if (searchForm.tag) {
      params.tag = searchForm.tag
    }
    const res = await http.apiModuleApi.getTestCaseList(params)
    if (res.status === 200) {
      let data = res.data.data || []
      // 前端过滤接口关键字
      if (searchForm.api_keyword) {
        const keyword = searchForm.api_keyword.toLowerCase()
        data = data.filter(item => 
          (item.api_name && item.api_name.toLowerCase().includes(keyword)) ||
          (item.api_path && item.api_path.toLowerCase().includes(keyword))
        )
      }
      caseList.value = data
      pagination.total = res.data.total
    }
  } catch (error) {
    ElMessage.error('获取用例列表失败')
  } finally {
    loading.value = false
  }
}

const getMethodType = (method) => {
  const map = { 'GET': 'success', 'POST': 'primary', 'PUT': 'warning', 'DELETE': 'danger', 'PATCH': 'info' }
  return map[method] || undefined
}

const getPriorityType = (priority) => {
  const map = { 'P0': 'danger', 'P1': 'warning', 'P2': '', 'P3': 'info' }
  return map[priority] || ''
}

// ===== 请求覆盖标识辅助函数 =====

const hasHeaderOverride = (row) => {
  if (!row.request_headers) return false
  if (Array.isArray(row.request_headers)) return row.request_headers.length > 0
  if (typeof row.request_headers === 'object') return Object.keys(row.request_headers).length > 0
  return false
}

const getHeaderOverrides = (row) => {
  if (!row.request_headers) return {}
  if (Array.isArray(row.request_headers)) {
    const result = {}
    for (const h of row.request_headers) {
      if (h.key) result[h.key] = h.value
    }
    return result
  }
  return row.request_headers
}

const hasParamOverride = (row) => {
  if (!row.request_params) return false
  if (Array.isArray(row.request_params)) return row.request_params.length > 0
  if (typeof row.request_params === 'object') return Object.keys(row.request_params).length > 0
  return false
}

const getParamOverrides = (row) => {
  if (!row.request_params) return []
  if (Array.isArray(row.request_params)) {
    return row.request_params.filter(p => p.name)
  }
  return Object.entries(row.request_params).map(([name, value]) => ({ name, value: String(value) }))
}

const hasBodyOverride = (row) => {
  if (!row.request_body) return false
  if (typeof row.request_body === 'object') return Object.keys(row.request_body).length > 0
  if (typeof row.request_body === 'string') return row.request_body.trim().length > 0
  return true
}

const hasAnyOverride = (row) => {
  return hasHeaderOverride(row) || hasParamOverride(row) || hasBodyOverride(row)
}

const resetSearch = () => {
  searchForm.api_keyword = ''
  searchForm.catalog_id = null
  searchForm.priority = null
  searchForm.tag = null
  searchForm.keyword = ''
  getCaseList()
}

const handleCatalogFilter = () => {
  pagination.page = 1
  getCaseList()
}

const handleAdd = () => {
  editDialog.data = null
  editDialog.visible = true
}

const handleEdit = (row) => {
  editDialog.data = row
  editDialog.visible = true
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该测试用例吗？', '提示', { type: 'warning' })
    const res = await http.apiModuleApi.deleteTestCase(row.id)
    if (res.status === 200 || res.status === 204) {
      ElMessage.success('删除成功')
      getCaseList()
    }
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    const detail = error?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '删除失败')
  }
}

const handleSelectionChange = (selection) => {
  selectedCases.value = selection
}

const handleBatchCatalogSuccess = () => {
  selectedCases.value = []
  getCaseList()
}

const handleBatchDelete = async () => {
  if (selectedCases.value.length === 0) {
    ElMessage.warning('请选择要删除的用例')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedCases.value.length} 条用例吗？`,
      '警告',
      { type: 'warning' }
    )
    const ids = selectedCases.value.map(r => r.id)
    await http.apiModuleApi.batchDeleteTestCases(ids)
    ElMessage.success('批量删除成功')
    selectedCases.value = []
    getCaseList()
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    const detail = err?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '批量删除失败')
  }
}

const handleBatchExport = async () => {
  const ids = selectedCases.value.map(r => r.id)
  try {
    const res = await httpCaseApi.exportCases({ case_ids: ids })
    const url = URL.createObjectURL(new Blob([res.data], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `api_cases_${Date.now()}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success(`已导出 ${ids.length} 条用例`)
  } catch (err) {
    ElMessage.error('导出失败: ' + (err.response?.data?.detail || err.message))
  }
}

const handleImport = async (file) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('project_id', proStore.projectInfo.id)
  if (searchForm.catalog_id) {
    formData.append('catalog_id', String(searchForm.catalog_id))
  }
  try {
    const res = await httpCaseApi.importCases(formData)
    if (res.status === 200) {
      importResultDlg.result = res.data
      importResultDlg.visible = true
      if (res.data.success > 0) {
        getCaseList()
      }
    }
  } catch (err) {
    ElMessage.error('导入失败: ' + (err.response?.data?.detail || err.message))
  }
  return false
}

const handleCopy = async (row) => {
  try {
    await http.apiModuleApi.copy(row.id)
    ElMessage.success('复制成功')
    getCaseList()
  } catch (error) {
    ElMessage.error('复制失败')
  }
}

const openCopyDialog = (row) => {
  copyDialog.row = row
  copyDialog.visible = true
}

const submitCopyCase = (payload) => httpCaseApi.copy(copyDialog.row.id, payload)

const handleBatchRun = async () => {
  if (!proStore.envList || proStore.envList.length === 0) {
    ElMessage.warning('请先创建测试环境')
    return
  }
  await loadAuthConfigsForRun()
  envDialog.case = null
  envDialog.isBatch = true
  envDialog.env_id = pickDefaultRunEnvId()
  envDialog.auto_validate_schema = false
  envDialog.propagate_extracted = true
  envDialog.visible = true
}

const handleRun = async (row) => {
  // 检查是否有可用环境
  if (!proStore.envList || proStore.envList.length === 0) {
    ElMessage.warning('请先创建测试环境')
    return
  }

  await loadAuthConfigsForRun()
  // 打开环境选择弹窗：优先选中已启用 Token 授权的环境
  envDialog.case = row
  envDialog.isBatch = false
  envDialog.env_id = pickDefaultRunEnvId()
  envDialog.auto_validate_schema = false
  envDialog.propagate_extracted = true
  envDialog.visible = true
}

// AI 生成用例（需要查询接口定义）
const handleAiGenerate = async (row) => {
  try {
    const res = await http.apiModuleApi.getApiDetail(row.api_id)
    if (res.status === 200 && res.data) {
      aiDialog.data = res.data
      aiDialog.visible = true
    } else {
      ElMessage.error('获取接口信息失败')
    }
  } catch (error) {
    console.error('获取接口信息失败:', error)
    ElMessage.error('获取接口信息失败')
  }
}

const confirmRun = async () => {
  if (!envDialog.env_id) {
    ElMessage.warning('请选择执行环境')
    return
  }
  
  envLoading.value = true
  try {
    if (envDialog.isBatch) {
      // 批量执行
      const caseIds = selectedCases.value.map(r => r.id)
      const res = await http.apiModuleApi.runBatch({
        case_ids: caseIds,
        env_id: envDialog.env_id,
        auto_validate_schema: envDialog.auto_validate_schema
      })
      if (res.status >= 200 && res.status < 300) {
        envDialog.visible = false
        const data = res.data
        batchRunDialog.result = data
        batchRunDialog.visible = true
        ElMessage.success(`批量执行完成：成功 ${data.success || 0} 条，失败 ${data.failed || 0} 条`)
        selectedCases.value = []
        caseTableRef.value?.clearSelection()
      } else {
        ElMessage.error('批量执行失败: 服务器返回状态码 ' + res.status)
      }
    } else {
      // 单条执行
      const res = await http.apiModuleApi.runTestCase(envDialog.case.id, {
        env_id: envDialog.env_id,
        auto_validate_schema: envDialog.auto_validate_schema,
        propagate_extracted: envDialog.propagate_extracted,
      })
      if (res.status >= 200 && res.status < 300) {
        envDialog.visible = false
        runDialog.result = res.data
        runDialog.activeTab = 'request'
        runDialog.ddDetailIndex = null
        // 判断是否为数据驱动结果（有 total_rows 字段）
        runDialog.isDataDriven = typeof res.data.total_rows === 'number'
        runDialog.visible = true
        ElMessage.success('执行完成')
      } else {
        ElMessage.error('执行失败: 服务器返回状态码 ' + res.status)
      }
    }
  } catch (error) {
    ElMessage.error('执行失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    envLoading.value = false
    envDialog.isBatch = false
  }
}

const applyRouteQuery = async () => {
  const apiId = route.query.api_id
  if (apiId) {
    searchForm.api_id = Number(apiId) || null
  }
  const qKeyword = route.query.keyword
  if (qKeyword && typeof qKeyword === 'string') {
    searchForm.keyword = qKeyword
  }
  await getCaseList()
  const editId = route.query.edit_case_id
  if (editId) {
    const row = caseList.value.find((c) => String(c.id) === String(editId))
    if (row) {
      editDialog.data = row
      editDialog.visible = true
    } else {
      try {
        const res = await http.apiModuleApi.getTestCaseDetail(Number(editId))
        const detail = res.data?.data ?? res.data
        if (detail) {
          editDialog.data = detail
          editDialog.visible = true
        }
      } catch {
        /* ignore */
      }
    }
  }
}

onMounted(() => {
  getApiList()
  applyRouteQuery()
})

watch(
  () => [route.query.api_id, route.query.edit_case_id, route.query.keyword],
  () => {
    applyRouteQuery()
  },
)
</script>

<style scoped lang="scss">
.env-dialog-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 0 20px 10px;
}

.field-hint-sm {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.case-list-layout {
  display: flex;
  gap: 20px;
  min-height: calc(100vh - 250px);
}

.case-sidebar {
  width: 260px;
  min-width: 260px;
}

.case-list {
  .search-bar {
    display: flex;
    gap: 10px;
    margin-bottom: 15px;
  }
  
  .case-name {
    font-weight: 500;
  }
  
  .case-priority {
    margin-top: 5px;
  }
  
  .api-info {
    .api-name-row {
      font-weight: 500;
      color: var(--el-text-color-primary);
      margin-bottom: 4px;
    }
    
    .api-path-row {
      display: flex;
      align-items: center;
      gap: 8px;
      
      .api-path-text {
        color: var(--el-text-color-secondary);
        font-size: 12px;
        font-family: 'Consolas', monospace;
      }
    }
  }
  
  .pagination {
    margin-top: 15px;
    display: flex;
    justify-content: flex-end;
  }
}

.run-result {
  .result-header {
    display: flex;
    align-items: center;
    gap: 20px;
    margin-bottom: 20px;
    padding-bottom: 15px;
    border-bottom: 1px solid var(--el-border-color-lighter);
    
    .response-status {
      color: var(--el-text-color-secondary);
    }
  }

  .run-stage-timings-wrap {
    margin: -8px 0 16px;
    padding: 12px;
    background: var(--el-fill-color-lighter);
    border-radius: 6px;
  }

  .timing-cell {
    font-size: 12px;
    line-height: 1.4;

    &--http {
      color: #67c23a;
      font-weight: 600;
    }

    &--total {
      color: #909399;
    }
  }
  
  h4 {
    margin: 15px 0 10px;
    color: var(--el-text-color-primary);
  }
}

// 执行结果弹窗（scoped 部分，teleport 样式见文件末尾非 scoped 块）
:deep(.run-result-dialog) {
  .el-dialog__body {
    padding-top: 10px;
  }

  .result-tabs {
    .detail-block {
      margin-bottom: 20px;
      
      .detail-title {
        font-weight: 600;
        font-size: 14px;
        color: var(--el-text-color-primary);
        margin-bottom: 10px;
        padding-left: 8px;
        border-left: 3px solid var(--el-color-primary);
      }
      
      .detail-content {
        background: var(--el-fill-color-light);
        border-radius: 4px;
        padding: 12px;
        
        pre {
          margin: 0;
          font-family: 'Consolas', 'Monaco', monospace;
          font-size: 13px;
          line-height: 1.5;
          white-space: pre-wrap;
          word-wrap: break-word;
          max-height: 300px;
          overflow: auto;
        }
        
        .compare-row {
          display: flex;
          align-items: center;
          margin-bottom: 8px;
          
          &:last-child {
            margin-bottom: 0;
          }
          
          .label {
            width: 50px;
            color: var(--el-text-color-secondary);
            font-size: 13px;
          }
          
          code {
            flex: 1;
            padding: 4px 8px;
            border-radius: 4px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 13px;
            word-break: break-all;
            
            &.original {
              background: #f5f5f5;
              color: #999;
              text-decoration: line-through;
            }
            
            &.final {
              background: #e6f7ff;
              color: #1890ff;
            }
          }
        }
      }
    }
  }
}

// 请求覆盖标签样式
.override-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  
  .el-tag {
    cursor: pointer;
  }
}

// 覆盖详情 tooltip 样式
.override-tooltip {
  max-width: 300px;
  
  .tooltip-title {
    font-weight: 600;
    margin-bottom: 6px;
    padding-bottom: 4px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.2);
  }
  
  .tooltip-item {
    margin: 3px 0;
    font-size: 12px;
    
    code {
      background: rgba(255, 255, 255, 0.15);
      padding: 1px 4px;
      border-radius: 3px;
      font-family: 'Consolas', monospace;
    }
  }
  
  pre {
    margin: 0;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 11px;
    max-height: 200px;
    overflow-y: auto;
    background: rgba(0, 0, 0, 0.2);
    padding: 6px;
    border-radius: 4px;
    white-space: pre-wrap;
    word-break: break-all;
  }

  .retry-section {
    padding: 10px;

    .retry-summary {
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 12px;
      color: #E6A23C;
    }

    .retry-timeline {
      padding-left: 8px;

      .retry-item {
        display: flex;
        gap: 12px;
        padding: 10px 0;
        border-left: 2px solid #dcdfe6;
        padding-left: 16px;
        position: relative;

        &.success { border-left-color: #67C23A; }
        &.failed { border-left-color: #F56C6C; }
        &.error { border-left-color: #F56C6C; }

        .retry-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: #dcdfe6;
          position: absolute;
          left: -6px;
          top: 14px;

          &.success { background: #67C23A; }
          &.failed { background: #F56C6C; }
          &.error { background: #F56C6C; }
        }

        .retry-content {
          .retry-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;

            .retry-status-code {
              color: #909399;
              font-size: 12px;
            }

            .retry-time {
              color: #67c23a;
              font-size: 12px;
            }
          }

          .retry-error {
            margin-top: 4px;
            font-size: 12px;
            color: #F56C6C;
          }

          .retry-assertions {
            margin-top: 4px;
            font-size: 12px;
            color: #606266;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 6px;
          }

          .retry-assert-badge {
            display: inline-flex;
            align-items: center;
            gap: 3px;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
            border: 1px solid;

            &.passed {
              background: #f0f9eb;
              border-color: #b3e19d;
              color: #67c23a;
            }

            &.failed {
              background: #fef0f0;
              border-color: #fbc4c4;
              color: #f56c6c;
            }

            .assert-op { color: #909399; margin: 0 2px; }
            .assert-expected { font-weight: 600; }
            .assert-actual { color: #f56c6c; margin-left: 4px; }
          }

          .retry-body {
            margin-top: 6px;

            .json-viewer {
              max-height: 200px;
              overflow: auto;
            }
          }
        }
      }
    }
  }
}

// 数据驱动多轮结果样式
.dd-back-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);

  .dd-round-label {
    font-size: 14px;
    font-weight: 500;
    color: var(--el-text-color-primary);
  }
}

.dd-stat-card {
  text-align: center;
  padding: 8px 0;

  .dd-stat-label {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    margin-bottom: 4px;
  }

  .dd-stat-value {
    font-size: 24px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }
}
</style>

<!-- 执行结果弹窗 teleport 到 body，需非 scoped 样式 -->
<style lang="scss">
.run-result-dialog.el-dialog {
  display: flex;
  flex-direction: column;
  max-height: 92vh;
  overflow: hidden;
}

.env-select-dialog.el-dialog {
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.env-select-dialog .el-dialog__body {
  overflow: auto;
  max-height: calc(90vh - 120px);
}

.env-auth-hint {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.env-auth-hint code {
  font-size: 12px;
}

.run-result-dialog .el-dialog__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-top: 10px;
}

.run-result-dialog .run-result {
  width: 100%;
  max-width: 100%;
  overflow: hidden;
}

.run-result-dialog .result-tabs {
  width: 100%;
  max-width: 100%;
}

.run-result-dialog .result-tabs > .el-tabs__content {
  overflow: hidden;
  max-height: min(720px, calc(92vh - 180px));
}

.run-result-dialog .result-tabs .el-tab-pane {
  overflow: hidden;
}

/* 各 Tab 内容区：限制在弹窗内滚动 */
.run-result-dialog .run-tab-panel {
  width: 100%;
  max-width: 100%;
  max-height: min(680px, calc(92vh - 200px));
  overflow: auto;
  box-sizing: border-box;
}

.run-result-dialog .run-tab-panel--response {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 0;
  max-height: min(720px, calc(92vh - 180px));
}

.run-result-dialog .detail-block {
  margin-bottom: 16px;
}

.run-result-dialog .detail-block:last-child {
  margin-bottom: 0;
}

.run-result-dialog .detail-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.run-result-dialog .detail-title-row .detail-title {
  margin-bottom: 0;
}

.run-result-dialog .detail-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid var(--el-color-primary, #409eff);
}

/* 请求详情等：自动换行 + 区域滚动 */
.run-result-dialog .detail-pre-scroll {
  width: 100%;
  max-width: 100%;
  max-height: 280px;
  overflow: auto;
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  box-sizing: border-box;
}

.run-result-dialog .detail-pre {
  margin: 0;
  padding: 12px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
}

/* 变量/替换表格：不撑破弹窗 */
.run-result-dialog .run-kv-table {
  width: 100% !important;
  max-width: 100%;
}

.run-result-dialog .run-kv-table .el-table__body-wrapper {
  overflow-x: auto;
}

/* 响应 Body：独立横向滚动（仅此处允许长行不换行） */
.run-result-dialog .code-viewer {
  width: 100%;
  max-width: 100%;
  max-height: min(460px, calc(88vh - 320px));
  overflow: auto;
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  box-sizing: border-box;
}

.run-result-dialog .code-viewer-pre {
  display: block;
  margin: 0;
  padding: 12px 16px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre;
  word-break: normal;
  overflow-wrap: normal;
  width: max-content;
  min-width: 100%;
  box-sizing: border-box;
}

.run-result-dialog .compare-row code {
  word-break: break-all;
  overflow-wrap: anywhere;
}
</style>
