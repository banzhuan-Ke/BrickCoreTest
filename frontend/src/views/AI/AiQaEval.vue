<template>
  <PageCard>
    <template #title>
      <b>问答准确性评测</b>
      <span class="page-sub">标准问答集 → 可选调被测 API → LLM 评判（通过线 ≥80 分且无胡编）</span>
    </template>
    <template #main>
      <el-alert
        v-if="!projectId"
        type="warning"
        :closable="false"
        show-icon
        title="请先在顶部导航栏选择项目"
        style="margin-bottom: 12px;"
      />

      <el-card v-show="guideVisible" shadow="never" class="guide-card">
        <template #header>
          <div class="guide-head">
            <span class="guide-title">使用说明 · 快速上手</span>
            <el-button link type="primary" size="small" @click="guideVisible = false">收起</el-button>
          </div>
        </template>

        <ol class="guide-steps">
          <li><strong>新建评测集</strong>：左侧点「新建」，填写名称（如「标准问答集 v1」）。</li>
          <li>
            <strong>导入或维护用例</strong>：每题<strong>必填</strong>「问题」「标准答案」；「标准要点」可选（一般可不填）。
          </li>
          <li>
            <strong>配置被测 API（不是你的 LLM）</strong>：填写<strong>待测知识库/问答系统</strong>的 HTTP 接口——评测时平台把「问题」发给它，拿回「模型回答」。
            Body 里用 <code v-text="'{{question}}'"></code> 占位，Answer JSONPath 取回复文本（如 <code>$.data.answer</code>）。
          </li>
          <li>
            <strong>配置评判 LLM（打分用）</strong>：
            <el-button link type="primary" size="small" @click="goAiConfig('scene')">AI 模型配置 → 场景绑定</el-button>
            绑定「问答准确性评判」场景；它接收：问题 + 标准答案 + 被测系统回答，按 RAG v2 公式打分（与被测 API 不是同一个）。
          </li>
          <li>
            <strong>执行评测</strong>：填写<strong>评测名称</strong>便于在执行记录中识别；可选三种模式——
            <strong>自动</strong>（调 API + LLM 评判）、
            <strong>仅评判</strong>（用 Excel 里的「实际回答」，不调 API）、
            <strong>仅拉取</strong>（批量调 API 写回答并导出 Excel，不调 LLM）。
            提交后后台执行，可关闭页面。
          </li>
        </ol>

        <div class="guide-section">
          <div class="guide-section-title">Excel 导入格式（.xlsx，首行为表头）</div>
          <el-table :data="excelFormatRows" size="small" border class="guide-table">
            <el-table-column prop="col" label="列名（表头）" width="120" />
            <el-table-column prop="required" label="必填" width="56" align="center" />
            <el-table-column prop="desc" label="说明" min-width="200" />
            <el-table-column prop="example" label="示例" min-width="160" show-overflow-tooltip />
          </el-table>
          <div class="guide-actions">
            <el-button size="small" type="primary" @click="downloadImportTemplate">问答模板</el-button>
            <el-button size="small" @click="openTargetDialog">配置被测 API</el-button>
            <span class="hint">必填：问题、标准答案；列结构与 RAG 批量问答 Excel 一致</span>
          </div>
        </div>

        <div class="guide-section">
          <div class="guide-section-title">被测 API 配置示例</div>
          <pre class="guide-code">{{ apiConfigExample }}</pre>
        </div>

        <div class="guide-section guide-footer">
          <span>通过线：<strong>换算后 ≥80 分</strong> 且无明显胡编；评判 Prompt 为 RAG 评测 v2 长公式（可在「AI 模型配置 → 提示词模板 → 问答准确性评判」查看/重置）。</span>
        </div>
      </el-card>

      <div v-if="!guideVisible" class="guide-collapsed-bar">
        <el-button link type="primary" size="small" @click="guideVisible = true">展开使用说明</el-button>
      </div>

      <el-alert
        v-if="activeRun"
        type="info"
        :closable="false"
        show-icon
        class="run-progress-alert"
      >
        <template #title>
          评测进行中 · {{ activeRun.display_name || activeRun.run_name || `任务 #${activeRun.id}` }}
          <span v-if="activeRun.run_mode_label">（{{ activeRun.run_mode_label }}）</span>
        </template>
        <div class="run-progress-body">
          <el-progress
            :percentage="activeRun.progress_percent || 0"
            :stroke-width="10"
            style="max-width: 360px;"
          />
          <span class="run-progress-text">
            {{ activeRun.done_count || 0 }} / {{ activeRun.total_count || '?' }} 题
            <template v-if="activeRun.passed_count != null">
              · 已通过 {{ activeRun.passed_count }}
            </template>
          </span>
          <p v-if="activeRun.current_question" class="run-current-q">
            当前：{{ activeRun.current_question }}
          </p>
          <span class="hint">可关闭本页，稍后回到「问答准确性评测」会自动恢复进度</span>
        </div>
      </el-alert>

      <el-row :gutter="16" class="main-row">
        <el-col :xs="24" :md="8">
          <el-card shadow="never" class="panel-card">
            <template #header>
              <div class="card-head">
                <span>评测集</span>
                <el-button
                  v-if="canExecute"
                  type="primary"
                  size="small"
                  @click="openSetDialog()"
                >新建</el-button>
              </div>
            </template>
            <el-table
              :data="sets"
              v-loading="setsLoading"
              highlight-current-row
              size="small"
              max-height="420"
              @current-change="onSelectSet"
            >
              <el-table-column prop="name" label="名称" min-width="100" show-overflow-tooltip />
              <el-table-column label="题数" width="72" align="center">
                <template #default="{ row }">
                  <span>{{ row.case_count }}</span>
                  <el-tooltip
                    v-if="row.max_seq_no && row.max_seq_no !== row.case_count"
                    :content="`实际 ${row.case_count} 条，Excel 最大序号 ${row.max_seq_no}（序号与条数不一致，可能有跳过或重复序号）`"
                    placement="top"
                  >
                    <span class="seq-count-warn">!</span>
                  </el-tooltip>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!setsLoading && !sets.length" description="暂无评测集，请先新建或按上方说明导入" :image-size="48" />
          </el-card>
        </el-col>

        <el-col :xs="24" :md="16">
          <el-card v-if="currentSet" shadow="never" class="panel-card" v-loading="detailLoading">
            <template #header>
              <div class="card-head">
                <span>{{ currentSet.name }}</span>
                <div class="head-actions">
                  <el-button
                    v-if="canExecute"
                    type="success"
                    size="small"
                    :loading="running"
                    :disabled="!!activeRun"
                    @click="openRunDialog"
                  >执行评测</el-button>
                  <el-button size="small" @click="openTargetDialog">被测 API</el-button>
                  <el-button v-if="canExecute" size="small" @click="openSetDialog(currentSet)">编辑</el-button>
                  <el-button v-if="canExecute" size="small" type="danger" link @click="removeSet">删除</el-button>
                </div>
              </div>
            </template>

            <el-tabs v-model="activeTab">
              <el-tab-pane label="评测用例" name="cases">
                <div class="toolbar" v-if="canExecute">
                  <el-button type="primary" size="small" @click="openCaseDialog()">新增用例</el-button>
                  <el-upload
                    :show-file-list="false"
                    accept=".xlsx"
                    :before-upload="onImportFile"
                  >
                    <el-button size="small">Excel 导入</el-button>
                  </el-upload>
                  <el-button size="small" @click="downloadImportTemplate">问答模板</el-button>
                  <el-button size="small" @click="exportCurrentSet">导出用例</el-button>
                  <span class="hint">表头：问题、标准答案（必填）；序号、问答目录、多轮、问题类型等见上方说明</span>
                </div>
                <el-table :data="cases" size="small" max-height="360" stripe>
                  <el-table-column prop="seq_no" label="序号" width="56" align="center" />
                  <el-table-column prop="question" label="问题" min-width="140" show-overflow-tooltip />
                  <el-table-column label="标准答案" width="72" align="center">
                    <template #default="{ row }">
                      <el-tag size="small" :type="row.expected_answer ? 'success' : 'info'">
                        {{ row.expected_answer ? '有' : '无' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="实际回答" width="72" align="center">
                    <template #default="{ row }">
                      <el-tag size="small" :type="row.has_preset_answer ? 'success' : 'info'">
                        {{ row.has_preset_answer ? '有' : '无' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="scenario_type" label="问题类型" width="100" show-overflow-tooltip />
                  <el-table-column label="多轮" width="48" align="center">
                    <template #default="{ row }">{{ row.multi_turn ? '是' : '—' }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="100" fixed="right" v-if="canExecute">
                    <template #default="{ row }">
                      <el-button link type="primary" size="small" @click="openCaseDialog(row)">编辑</el-button>
                      <el-button link type="danger" size="small" @click="removeCase(row)">删</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>

              <el-tab-pane label="执行记录" name="runs">
                <div class="toolbar runs-toolbar">
                  <el-select
                    v-if="batchGroupOptions.length"
                    v-model="mergeExportBatchId"
                    placeholder="选择自动分批任务"
                    size="small"
                    clearable
                    style="width: 220px;"
                  >
                    <el-option
                      v-for="g in batchGroupOptions"
                      :key="g.id"
                      :label="g.label"
                      :value="g.id"
                    />
                  </el-select>
                  <span class="inline-hint">或勾选下方已完成跑批（合并按题目序号去重，非条数相加）</span>
                  <el-button size="small" type="success" :loading="mergeExporting" @click="downloadMergedExport">合并导出</el-button>
                  <el-button size="small" type="primary" @click="openMergedStatsReport">合并统计</el-button>
                  <el-button size="small" type="warning" @click="openCompareDialog">迭代对比</el-button>
                </div>
                <el-table
                  :data="runs"
                  size="small"
                  max-height="360"
                  stripe
                  @selection-change="onRunSelectionChange"
                >
                  <el-table-column
                    type="selection"
                    width="40"
                    :selectable="(row) => row.status === 'completed'"
                  />
                  <el-table-column prop="create_time" label="时间" width="150" />
                  <el-table-column prop="display_name" label="评测名称" min-width="120" show-overflow-tooltip />
                  <el-table-column prop="run_mode_label" label="模式" width="110" show-overflow-tooltip />
                  <el-table-column prop="case_scope_label" label="范围" width="100" show-overflow-tooltip />
                  <el-table-column prop="batch_label" label="分批" width="88" show-overflow-tooltip />
                  <el-table-column prop="target_name" label="被测 API" width="100" show-overflow-tooltip />
                  <el-table-column label="进度" width="120">
                    <template #default="{ row }">
                      <template v-if="row.status === 'running' || row.status === 'pending'">
                        <el-progress :percentage="row.progress_percent || 0" :stroke-width="6" />
                      </template>
                      <span v-else>—</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="自动校验率" width="96" align="center">
                    <template #default="{ row }">
                      <template v-if="row.status === 'completed'">
                        {{ row.run_mode === 'fetch_only' ? `${row.pass_rate}% 成功` : `${row.pass_rate}%` }}
                      </template>
                      <span v-else>—</span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="avg_score" label="均分" width="64" align="center" />
                  <el-table-column prop="status" label="状态" width="88">
                    <template #default="{ row }">
                      <el-tag size="small" :type="runStatusType(row.status)">
                        {{ row.status_label || runStatusLabel(row.status) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" min-width="300" fixed="right">
                    <template #default="{ row }">
                      <div class="run-actions">
                        <el-button
                          v-if="row.status === 'completed' && (row.run_mode === 'fetch_only' || row.export_ready)"
                          link
                          type="success"
                          size="small"
                          @click="downloadRunExport(row)"
                        >导出</el-button>
                        <el-button
                          v-if="canExecute && row.status === 'completed' && row.run_mode !== 'judge_only'"
                          link
                          type="warning"
                          size="small"
                          @click="retryFailedRun(row)"
                        >重跑失败</el-button>
                        <el-button
                          v-if="row.status === 'completed' && row.run_mode !== 'fetch_only'"
                          link
                          type="primary"
                          size="small"
                          @click="openStatsReport(row)"
                        >统计</el-button>
                        <el-button
                          v-if="row.run_mode !== 'fetch_only'"
                          link
                          type="primary"
                          size="small"
                          @click="openReport(row)"
                        >报告</el-button>
                        <el-button
                          v-if="canExecute && row.status !== 'pending' && row.status !== 'running'"
                          link
                          type="danger"
                          size="small"
                          @click="removeRun(row)"
                        >删除</el-button>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
            </el-tabs>
          </el-card>
          <el-empty v-else description="请选择左侧评测集" :image-size="80" />
        </el-col>
      </el-row>

      <!-- 评测集 -->
      <el-dialog v-model="setDialog.visible" :title="setDialog.id ? '编辑评测集' : '新建评测集'" width="480px">
        <el-form label-width="80px">
          <el-form-item label="名称" required>
            <el-input v-model="setDialog.name" maxlength="200" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="setDialog.description" type="textarea" :rows="3" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="setDialog.visible = false">取消</el-button>
          <el-button type="primary" :loading="setDialog.saving" @click="saveSet">保存</el-button>
        </template>
      </el-dialog>

      <!-- 用例 -->
      <el-dialog v-model="caseDialog.visible" :title="caseDialog.id ? '编辑用例' : '新增用例'" width="640px">
        <p class="case-dialog-hint">
          评测时 LLM 对照：<strong>问题</strong> + <strong>标准答案</strong> + 被测 API 返回的<strong>实际回答</strong>。标准要点可不填。
        </p>
        <el-form label-width="96px">
          <el-form-item label="序号">
            <el-input-number v-model="caseDialog.seq_no" :min="1" :max="99999" controls-position="right" />
          </el-form-item>
          <el-form-item label="问题" required>
            <el-input v-model="caseDialog.question" type="textarea" :rows="2" placeholder="发给被测问答系统的问题" />
          </el-form-item>
          <el-form-item label="标准答案" required>
            <el-input
              v-model="caseDialog.expected_answer"
              type="textarea"
              :rows="6"
              placeholder="参考答案全文，作为 LLM 打分的 ground_truth"
            />
          </el-form-item>
          <el-form-item label="标准要点">
            <el-input
              v-model="caseDialog.pointsText"
              type="textarea"
              :rows="2"
              placeholder="可选；多条用分号或换行分隔，会附在标准答案后供 Judge 参考"
            />
          </el-form-item>
          <el-form-item label="实际回答">
            <el-input
              v-model="caseDialog.preset_answer"
              type="textarea"
              :rows="4"
              placeholder="可选；外部 API 已跑批时可导入/填写，用于「仅 LLM 评判」模式（变量 answer）"
            />
          </el-form-item>
          <el-form-item label="问答目录">
            <el-input
              v-model="caseDialog.chatPathText"
              placeholder='目录 ID，多个用逗号分隔，或 JSON 如 ["id1"]'
            />
          </el-form-item>
          <el-form-item label="多轮会话">
            <el-switch v-model="caseDialog.multi_turn" />
          </el-form-item>
          <el-form-item label="问题类型">
            <el-select
              v-model="caseDialog.scenario_type"
              filterable
              allow-create
              default-first-option
              clearable
              placeholder="选择或输入问题类型"
              style="width: 100%;"
              @change="onQuestionTypeChange"
            >
              <el-option v-for="t in questionTypeOptions" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="文件">
            <el-input v-model="caseDialog.source_file" />
          </el-form-item>
          <el-form-item label="文件类型">
            <el-input v-model="caseDialog.file_type" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="caseDialog.visible = false">取消</el-button>
          <el-button type="primary" :loading="caseDialog.saving" @click="saveCase">保存</el-button>
        </template>
      </el-dialog>

      <!-- 被测 API -->
      <el-dialog v-model="targetDialog.visible" title="被测问答 API" width="820px">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 12px;"
          title="这是待评测的知识库/问答服务接口，不是打分用的 LLM。平台把每道「问题」POST 过去，取回回答后再交给「问答准确性评判」模型打分。"
        />
        <div class="target-toolbar">
          <el-button v-if="canExecute" type="primary" size="small" @click="openTargetForm()">新增配置</el-button>
          <el-button v-if="canExecute" size="small" @click="applyQaSsePreset">SSE 流式模板</el-button>
          <el-button v-if="canExecute" size="small" type="success" @click="createQaSseTargetFromPreset">一键创建流式配置</el-button>
        </div>
        <el-table :data="targets" size="small" max-height="200">
          <el-table-column prop="name" label="名称" width="120" />
          <el-table-column label="URL" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.config?.url }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" v-if="canExecute">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openTargetForm(row)">编辑</el-button>
              <el-button link type="success" size="small" @click="openTargetForm(row, true)">调试</el-button>
              <el-button link type="danger" size="small" @click="removeTarget(row)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-divider v-if="targetForm.visible" />
        <el-form v-if="targetForm.visible" label-width="110px" class="target-form">
          <el-form-item label="名称" required>
            <el-input v-model="targetForm.name" />
          </el-form-item>
          <el-form-item label="URL" required>
            <el-input v-model="targetForm.url" placeholder="https://api.example.com/chat" />
          </el-form-item>
          <el-form-item label="方法">
            <el-select v-model="targetForm.method" style="width: 120px;">
              <el-option label="POST" value="POST" />
              <el-option label="GET" value="GET" />
            </el-select>
          </el-form-item>
          <el-form-item label="响应类型">
            <el-select v-model="targetForm.response_type" style="width: 160px;">
              <el-option label="JSON" value="json" />
              <el-option label="SSE 流式" value="sse" />
            </el-select>
            <span v-if="targetForm.response_type === 'sse'" class="inline-hint">流式问答接口选此项</span>
          </el-form-item>
          <el-form-item v-if="targetForm.response_type === 'json'" label="Answer JSONPath">
            <el-input v-model="targetForm.answer_jsonpath" placeholder="$.data.answer" />
          </el-form-item>
          <el-form-item v-if="targetForm.response_type === 'sse'" label="SSE 解析器">
            <el-select v-model="targetForm.sse_parser" style="width: 200px;">
              <el-option label="问答流式 v1" value="qa_sse_v1" />
            </el-select>
          </el-form-item>
          <el-form-item label="default_body">
            <el-input
              v-model="targetForm.defaultBodyText"
              type="textarea"
              :rows="5"
              placeholder='复杂接口：固定 JSON 字段；跑批时会自动填入 question/chatPath/sessionId 等'
            />
          </el-form-item>
          <el-form-item label="请求体模板">
            <el-input
              v-model="targetForm.body_template"
              type="textarea"
              :rows="3"
              placeholder='简单接口：{"query":"{{question}}"}；若已填 default_body 可留空'
            />
          </el-form-item>
          <el-form-item label="超时(秒)">
            <el-input-number v-model="targetForm.read_timeout_sec" :min="10" :max="600" />
            <span class="inline-hint">连接 {{ targetForm.connect_timeout_sec }}s · 读取 {{ targetForm.read_timeout_sec }}s</span>
          </el-form-item>
          <el-form-item label="Headers (JSON)">
            <el-input v-model="targetForm.headersText" type="textarea" :rows="4" placeholder='{"Content-Type":"application/json","token":"...","digi-middleware-auth-app":"..."}' />
            <p v-if="targetForm.response_type === 'sse'" class="inline-hint header-hint">
              流式问答接口需填写 token、digi-middleware-auth-app（从浏览器开发者工具复制）；部分环境还需 signature、signature-data。
            </p>
          </el-form-item>

          <el-divider content-position="left">接口调试</el-divider>
          <el-form-item label="测试问题">
            <el-input v-model="targetForm.debugQuestion" type="textarea" :rows="2" placeholder="输入一道测试问题" />
          </el-form-item>
          <el-form-item label="chatPath">
            <el-input v-model="targetForm.debugChatPathText" placeholder='[] 或 ["问答测试"]' />
            <span class="inline-hint">调试与跑批默认目录；Excel「问答目录」有值时以 Excel 为准</span>
          </el-form-item>
          <el-form-item label="多轮会话">
            <el-switch v-model="targetForm.debugHistoryFlag" />
            <el-input
              v-model="targetForm.debugSessionId"
              placeholder="sessionId（多轮时填写，可留空自动生成）"
              style="width: 280px; margin-left: 12px;"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="success" :loading="targetForm.testing" @click="runTargetTest">发送调试请求</el-button>
            <el-button type="primary" :loading="targetForm.saving" @click="saveTarget">保存配置</el-button>
          </el-form-item>
          <div v-if="targetForm.debugResult" class="target-debug-result">
            <p>
              <el-tag :type="targetForm.debugResult.success ? 'success' : 'danger'" size="small">
                {{ targetForm.debugResult.success ? '成功' : '失败' }}
              </el-tag>
              <span class="inline-hint">耗时 {{ targetForm.debugResult.api_latency_ms }} ms</span>
            </p>
            <p v-if="targetForm.debugResult.api_error" class="err">{{ targetForm.debugResult.api_error }}</p>
            <template v-if="targetForm.debugResult.parsed_fields?.thinking">
              <p><b>意图识别：</b></p>
              <pre class="answer-pre">{{ targetForm.debugResult.parsed_fields.thinking }}</pre>
            </template>
            <p><b>实际回答：</b></p>
            <pre class="answer-pre">{{ targetForm.debugResult.actual_answer || '—' }}</pre>
            <template v-if="targetForm.debugResult.parsed_fields?.references_all">
              <p><b>参考文件：</b>{{ targetForm.debugResult.parsed_fields.references_all }}</p>
            </template>
            <p><b>原始响应（末尾）：</b></p>
            <pre class="answer-pre debug-raw">{{ targetForm.debugResult.raw_preview || '—' }}</pre>
          </div>
        </el-form>
      </el-dialog>

      <!-- 执行 -->
      <el-dialog v-model="runDialog.visible" title="执行评测" width="520px">
        <el-form label-width="110px">
          <el-form-item label="评测名称">
            <el-input
              v-model="runDialog.run_name"
              maxlength="100"
              show-word-limit
              clearable
              placeholder="便于执行记录识别，默认为评测集名称"
            />
          </el-form-item>
          <el-form-item label="运行模式" required>
            <el-radio-group v-model="runDialog.run_mode" class="run-mode-group">
              <el-radio v-for="m in runModes" :key="m.value" :value="m.value">
                {{ m.label }}
              </el-radio>
            </el-radio-group>
            <p class="run-mode-desc">{{ currentRunModeDesc }}</p>
          </el-form-item>
          <el-form-item v-if="runDialog.run_mode !== 'judge_only'" label="被测 API" required>
            <el-select v-model="runDialog.target_id" placeholder="请选择" style="width: 100%;">
              <el-option v-for="t in targets" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="runDialog.run_mode !== 'fetch_only'" label="评判模型">
            <el-select v-model="runDialog.judge_config_id" clearable placeholder="默认（场景绑定 qa_judge）" style="width: 100%;">
              <el-option
                v-for="c in configOptions"
                :key="c.id"
                :label="`${c.name} (${c.model})`"
                :value="c.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="用例范围">
            <el-radio-group v-model="runDialog.case_scope" :disabled="runDialog.use_auto_batch">
              <el-radio value="all">全部</el-radio>
              <el-radio value="range">序号范围</el-radio>
              <el-radio value="retry_failed">仅重跑失败</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="runDialog.case_scope === 'range' && !runDialog.use_auto_batch" label="序号范围">
            <el-input-number v-model="runDialog.range_start" :min="1" :max="99999" controls-position="right" />
            <span style="margin: 0 8px;">至</span>
            <el-input-number v-model="runDialog.range_end" :min="1" :max="99999" controls-position="right" />
          </el-form-item>
          <el-form-item v-if="runDialog.case_scope === 'retry_failed'" label="来源任务">
            <el-select v-model="runDialog.retry_source_run_id" placeholder="选择已完成跑批" style="width: 100%;">
              <el-option
                v-for="r in completedRunsForRetry"
                :key="r.id"
                :label="`#${r.id} ${r.run_mode_label || ''} ${r.create_time || ''}`"
                :value="r.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="自动分批">
            <el-switch v-model="runDialog.use_auto_batch" :disabled="runDialog.case_scope !== 'all'" />
            <span class="inline-hint">题量 &gt;500 时按批顺序跑（每批最多 500 题）</span>
          </el-form-item>
          <el-form-item v-if="runDialog.use_auto_batch" label="每批题数">
            <el-input-number v-model="runDialog.chunk_size" :min="10" :max="500" :step="10" />
          </el-form-item>
          <el-form-item v-if="runDialog.run_mode !== 'judge_only'" label="请求间隔 (ms)">
            <el-input-number v-model="runDialog.request_interval_ms" :min="0" :max="60000" :step="100" />
            <span class="inline-hint">0 表示不等待；多轮会话建议 &gt;0</span>
          </el-form-item>
          <p class="run-hint">提交后在后台执行，可关闭页面；分批任务完成后可用「合并导出」汇总 Excel。</p>
        </el-form>
        <template #footer>
          <el-button @click="runDialog.visible = false">取消</el-button>
          <el-button type="primary" :loading="running" @click="doRun">{{ runSubmitLabel }}</el-button>
        </template>
      </el-dialog>

      <!-- 报告 -->
      <el-drawer v-model="reportDrawer.visible" title="评测报告" size="72%">
        <div v-if="reportDrawer.run" class="report-summary">
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="评测名称">
              {{ reportDrawer.run.display_name || reportDrawer.run.run_name || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="模式">{{ reportDrawer.run.run_mode_label || '—' }}</el-descriptions-item>
            <el-descriptions-item v-if="reportDrawer.run.run_mode !== 'fetch_only'" label="自动校验率">
              {{ reportDrawer.run.pass_rate }}%
            </el-descriptions-item>
            <el-descriptions-item v-else label="拉取成功">
              {{ reportDrawer.run.passed_count }} / {{ reportDrawer.run.total_count }}
            </el-descriptions-item>
            <el-descriptions-item v-if="reportDrawer.run.run_mode !== 'fetch_only'" label="均分">
              {{ reportDrawer.run.avg_score }}
            </el-descriptions-item>
            <el-descriptions-item v-if="reportDrawer.run.run_mode !== 'fetch_only'" label="自动校验/总数">
              {{ reportDrawer.run.passed_count }} / {{ reportDrawer.run.total_count }}
            </el-descriptions-item>
          </el-descriptions>
          <el-button
            v-if="reportDrawer.run.export_ready || reportDrawer.run.run_mode === 'fetch_only'"
            size="small"
            style="margin-top: 8px;"
            @click="downloadRunExport(reportDrawer.run)"
          >下载问答结果 Excel</el-button>
          <el-button
            v-if="canExecute && reportDrawer.run.status === 'completed' && reportDrawer.run.run_mode !== 'fetch_only'"
            size="small"
            type="warning"
            style="margin-top: 8px; margin-left: 8px;"
            @click="bulkApproveFailed"
          >批量人工通过（自动校验否）</el-button>
        </div>
        <el-table :data="reportDrawer.results" size="small" max-height="calc(100vh - 240px)" v-loading="reportDrawer.loading">
          <el-table-column prop="seq_no" label="序号" width="52" align="center" />
          <el-table-column prop="question" label="问题" min-width="120" show-overflow-tooltip />
          <el-table-column prop="expected_answer" label="标准答案" min-width="140" show-overflow-tooltip />
          <el-table-column label="返回答案" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.actual_answer">{{ row.actual_answer }}</span>
              <span v-else-if="row.api_error" class="err">{{ row.api_error }}</span>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column prop="score" label="得分" width="56" align="center" />
          <el-table-column prop="level" label="等级" width="72" />
          <el-table-column width="72" align="center">
            <template #header>
              <el-tooltip content="自动检测幻觉/API 异常，不以分数划线" placement="top">
                <span class="col-tip">自动校验</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tag :type="row.passed ? 'success' : 'danger'" size="small">{{ row.passed ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="manual_status_label" label="人工审核" width="88" />
          <el-table-column label="操作" width="168" fixed="right" v-if="canExecute">
            <template #default="{ row }">
              <div class="run-actions">
                <el-button
                  v-if="reportDrawer.run?.run_mode !== 'judge_only'"
                  link
                  type="warning"
                  size="small"
                  :loading="row._regenerating"
                  @click="regenerateResult(row)"
                >重生成</el-button>
                <el-button link type="success" size="small" @click="reviewOne(row, 'approved')">通过</el-button>
                <el-button link type="danger" size="small" @click="reviewOne(row, 'rejected')">驳回</el-button>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="详情" width="56" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="showResultDetail(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-drawer>

      <!-- 统计报告（对齐 RAG 测试总结 docx） -->
      <el-drawer v-model="statsDrawer.visible" title="统计报告" size="60%">
        <div v-loading="statsDrawer.loading">
          <template v-if="statsDrawer.report">
            <template v-if="statsDrawer.report.merged">
              <p class="inline-hint stats-merge-hint">
                合并统计：{{ statsDrawer.report.merge_label || '多批合并' }}，去重后共
                {{ statsDrawer.report.overview?.total_count }} 题
              </p>
              <p
                v-if="statsDrawer.report.merge_info"
                class="inline-hint stats-merge-detail"
              >
                各跑批结果条数合计 {{ statsDrawer.report.merge_info.raw_result_count }} 条，按题目序号合并后
                {{ statsDrawer.report.merge_info.merged_unique_count }} 题
                <template v-if="statsDrawer.report.merge_info.overwritten_count">
                  （{{ statsDrawer.report.merge_info.overwritten_count }} 条被后一次跑批覆盖）
                </template>
                <template v-if="statsDrawer.report.merge_info.set_case_count">
                  ；评测集共 {{ statsDrawer.report.merge_info.set_case_count }} 题
                </template>
              </p>
              <p
                v-if="statsDrawer.report.merge_info?.runs_detail?.length"
                class="inline-hint stats-merge-detail"
              >
                <span
                  v-for="rd in statsDrawer.report.merge_info.runs_detail"
                  :key="rd.run_id"
                  class="merge-run-chip"
                >跑批 #{{ rd.run_id }}：{{ rd.result_count }} 条</span>
              </p>
            </template>
            <el-descriptions :column="2" border size="small" class="stats-block">
              <el-descriptions-item label="评测集">{{ statsDrawer.report.set_name }}</el-descriptions-item>
              <el-descriptions-item label="被测 API">{{ statsDrawer.report.target_name || '—' }}</el-descriptions-item>
              <el-descriptions-item label="评测题数">{{ statsDrawer.report.overview?.judged_count }} / {{ statsDrawer.report.overview?.total_count }}</el-descriptions-item>
              <el-descriptions-item label="平均得分">{{ statsDrawer.report.overview?.avg_score }}（0~1）</el-descriptions-item>
              <el-descriptions-item label="优秀率（≥0.90）">{{ statsDrawer.report.overview?.excellent_rate }}%</el-descriptions-item>
              <el-descriptions-item label="良好率（≥0.75）">{{ statsDrawer.report.overview?.good_or_above_rate }}%</el-descriptions-item>
              <el-descriptions-item label="不合格率（&lt;0.50）">{{ statsDrawer.report.overview?.unqualified_rate }}%</el-descriptions-item>
              <el-descriptions-item label="平台通过率">{{ statsDrawer.report.overview?.platform_pass_rate }}%（自动校验）</el-descriptions-item>
              <el-descriptions-item label="幻觉条数">{{ statsDrawer.report.overview?.hallucination_count }}</el-descriptions-item>
              <el-descriptions-item label="人工待审">{{ statsDrawer.report.manual_review?.pending }}</el-descriptions-item>
            </el-descriptions>

            <h4 class="stats-h4">等级分布</h4>
            <el-table :data="statsDrawer.report.overview?.level_distribution || []" size="small" border>
              <el-table-column prop="level" label="等级" width="100" />
              <el-table-column prop="score_range" label="分数区间(0~1)" width="120" />
              <el-table-column prop="count" label="题数" width="72" align="center" />
              <el-table-column prop="rate" label="占比%" width="80" align="center" />
            </el-table>

            <h4 class="stats-h4">问题类型分析</h4>
            <el-table :data="statsDrawer.report.by_scenario_type || []" size="small" border max-height="200">
              <el-table-column prop="name" label="问题类型" min-width="120" />
              <el-table-column prop="count" label="题数" width="64" align="center" />
              <el-table-column prop="avg_score" label="平均分(0~1)" width="100" align="center" />
              <el-table-column prop="excellent_rate" label="优秀率%" width="88" align="center" />
              <el-table-column prop="good_or_above_rate" label="良好率%" width="88" align="center" />
            </el-table>

            <h4 class="stats-h4">文件类型分析</h4>
            <el-table :data="statsDrawer.report.by_file_type || []" size="small" border max-height="200">
              <el-table-column prop="name" label="文件类型" min-width="120" />
              <el-table-column prop="count" label="题数" width="64" align="center" />
              <el-table-column prop="avg_score" label="平均分(0~1)" width="100" align="center" />
              <el-table-column prop="excellent_rate" label="优秀率%" width="88" align="center" />
              <el-table-column prop="good_or_above_rate" label="良好率%" width="88" align="center" />
            </el-table>

            <h4 class="stats-h4">失败样例（得分最低）</h4>
            <el-table :data="statsDrawer.report.failed_samples || []" size="small" border max-height="220">
              <el-table-column prop="seq_no" label="序号" width="56" />
              <el-table-column prop="scenario_type" label="问题类型" width="100" show-overflow-tooltip />
              <el-table-column prop="score" label="得分" width="56" align="center" />
              <el-table-column prop="level" label="等级" width="72" />
              <el-table-column prop="question" label="问题" min-width="140" show-overflow-tooltip />
            </el-table>
          </template>
        </div>
      </el-drawer>

      <!-- 迭代对比报告 -->
      <el-drawer v-model="compareDrawer.visible" title="迭代对比报告" size="78%">
        <div v-loading="compareDrawer.loading">
          <template v-if="compareDrawer.report">
            <p class="inline-hint stats-merge-hint">
              评测集：{{ compareDrawer.report.set_name }} · 共 {{ compareDrawer.report.group_count }} 组对比
            </p>

            <h4 class="stats-h4">总体指标对比</h4>
            <el-table :data="compareDrawer.report.overview_compare || []" size="small" border>
              <el-table-column prop="metric" label="指标" width="128" fixed />
              <el-table-column
                v-for="g in compareDrawer.report.groups"
                :key="g.label"
                :label="g.label"
                min-width="100"
                align="center"
              >
                <template #default="{ row }">
                  {{ compareMetricValue(row, g.label) }}
                </template>
              </el-table-column>
            </el-table>

            <h4 class="stats-h4">等级分布对比</h4>
            <el-table :data="compareDrawer.report.level_compare || []" size="small" border max-height="220">
              <el-table-column prop="level" label="等级" width="100" fixed />
              <el-table-column
                v-for="g in compareDrawer.report.groups"
                :key="'lv-' + g.label"
                :label="g.label"
                min-width="100"
                align="center"
              >
                <template #default="{ row }">
                  {{ compareLevelCell(row, g.label) }}
                </template>
              </el-table-column>
            </el-table>

            <h4 class="stats-h4">问题类型对比</h4>
            <el-table :data="compareDrawer.report.scenario_compare || []" size="small" border max-height="220">
              <el-table-column prop="name" label="问题类型" min-width="120" fixed />
              <el-table-column
                v-for="g in compareDrawer.report.groups"
                :key="'sc-' + g.label"
                :label="g.label"
                min-width="100"
                align="center"
              >
                <template #default="{ row }">
                  {{ compareScenarioCell(row, g.label) }}
                </template>
              </el-table-column>
            </el-table>

            <h4 class="stats-h4">逐题得分对比</h4>
            <el-table :data="compareDrawer.report.question_compare || []" size="small" border max-height="420">
              <el-table-column prop="seq_no" label="序号" width="52" align="center" fixed />
              <el-table-column prop="question" label="问题" min-width="140" show-overflow-tooltip fixed />
              <el-table-column
                v-for="g in compareDrawer.report.groups"
                :key="'q-' + g.label"
                :label="g.label"
                width="96"
                align="center"
              >
                <template #default="{ row }">
                  <template v-if="compareQuestionCell(row, g.label)?.missing">—</template>
                  <template v-else>
                    <div>{{ compareQuestionCell(row, g.label)?.score ?? '—' }}</div>
                    <div class="inline-hint">{{ compareQuestionCell(row, g.label)?.level || '' }}</div>
                  </template>
                </template>
              </el-table-column>
              <el-table-column prop="best_label" label="最高" width="88" show-overflow-tooltip />
              <el-table-column prop="score_spread" label="分差" width="56" align="center" />
            </el-table>
          </template>
        </div>
      </el-drawer>

      <!-- 配置迭代对比 -->
      <el-dialog v-model="compareDialog.visible" title="配置迭代对比" width="640px">
        <p class="run-hint">
          添加 2～10 个对比组，用于比较不同迭代/模型的问答效果。每组可合并多条已完成跑批（同序号后者覆盖）。
        </p>
        <div v-for="(g, idx) in compareDialog.groups" :key="idx" class="compare-group-card">
          <div class="compare-group-head">
            <span>对比组 {{ idx + 1 }}</span>
            <el-button
              v-if="compareDialog.groups.length > 2"
              link
              type="danger"
              size="small"
              @click="removeCompareGroup(idx)"
            >删除</el-button>
          </div>
          <el-form label-width="88px" size="small">
            <el-form-item label="名称" required>
              <el-input v-model="g.label" placeholder="如 v1-模型A、v2-模型B" maxlength="100" />
            </el-form-item>
            <el-form-item label="数据来源">
              <el-radio-group v-model="g.sourceType">
                <el-radio value="runs">勾选跑批</el-radio>
                <el-radio value="batch">自动分批</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="g.sourceType === 'runs'" label="跑批记录">
              <el-select
                v-model="g.run_ids"
                multiple
                collapse-tags
                collapse-tags-tooltip
                placeholder="选择一条或多条已完成跑批"
                style="width: 100%;"
              >
                <el-option
                  v-for="r in completedRunsForRetry"
                  :key="r.id"
                  :label="runOptionLabel(r)"
                  :value="r.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item v-else label="分批任务">
              <el-select v-model="g.batch_group_id" placeholder="选择自动分批任务" style="width: 100%;" clearable>
                <el-option v-for="bg in batchGroupOptions" :key="bg.id" :label="bg.label" :value="bg.id" />
              </el-select>
            </el-form-item>
          </el-form>
        </div>
        <div class="compare-group-actions">
          <el-button size="small" @click="addCompareGroup">添加对比组</el-button>
          <el-button size="small" type="primary" plain @click="addCompareGroupFromSelection">当前勾选作为新组</el-button>
        </div>
        <template #footer>
          <el-button @click="compareDialog.visible = false">取消</el-button>
          <el-button type="primary" :loading="compareDrawer.loading" @click="runCompareReport">开始对比</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="resultDetail.visible" title="单题详情" width="720px">
        <p><b>问题：</b>{{ resultDetail.row?.question }}</p>
        <p><b>标准答案：</b></p>
        <pre class="answer-pre">{{ resultDetail.row?.expected_answer || '—' }}</pre>
        <p><b>返回答案：</b></p>
        <pre class="answer-pre">{{ resultDetail.row?.actual_answer || '—' }}</pre>
        <template v-if="resultDetail.row?.thinking">
          <p><b>意图识别：</b></p>
          <pre class="answer-pre">{{ resultDetail.row.thinking }}</pre>
        </template>
        <template v-if="resultDetail.row?.references_all">
          <p><b>参考文件：</b></p>
          <pre class="answer-pre">{{ resultDetail.row.references_all }}</pre>
        </template>
        <p><b>评判理由：</b>{{ resultDetail.row?.reason || '—' }}</p>
        <p v-if="resultDetail.row?.missed_points?.length">
          <b>遗漏要点：</b>{{ resultDetail.row.missed_points.join('；') }}
        </p>
        <p v-if="resultDetail.row?.api_error" class="err">{{ resultDetail.row.api_error }}</p>
      </el-dialog>
    </template>
  </PageCard>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { qaEvalApi, aiConfigApi } from '@/api/modules/ai'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'

const proStore = ProjectStore()
const uStore = UserStore()
const router = useRouter()
const projectId = computed(() => proStore.projectInfo?.id)
const canExecute = computed(() => uStore.hasPermission('ai_test:execute'))
const guideVisible = ref(true)

const excelFormatRows = [
  { col: '序号', required: '否', desc: 'Excel 行序号，用于范围跑批与合并导出', example: '1' },
  { col: '问题', required: '是', desc: '发给被测问答系统的测试问题', example: '概括 SOP-5000 项目团队人员配置' },
  { col: '问答目录', required: '否', desc: 'chatPath，逗号分隔或 JSON 数组', example: '["dir-id"]' },
  { col: '是否开启多轮', required: '否', desc: '是/否，多轮时同 session 连续提问', example: '否' },
  { col: '问题类型', required: '否', desc: '事实性问答类 / 归纳总结类 / 对比分析类等，可自定义', example: '事实性问答类' },
  { col: '标准答案', required: '是', desc: '参考答案全文 → ground_truth', example: '项目团队由…组成' },
  { col: '文件', required: '否', desc: '附件/源文件标识', example: '' },
  { col: '文件类型', required: '否', desc: '如 pdf、docx', example: 'pdf' },
  { col: '实际回答', required: '否', desc: '仅评判模式必填；可先留空再批量拉取', example: '' },
  { col: '标准要点', required: '否', desc: '可选补充，附在标准答案后供 Judge 参考', example: '' }
]

const runModes = [
  { value: 'auto', label: '自动：API + LLM 评判', desc: '调用被测 API 获取回答，再交给 qa_judge 打分' },
  { value: 'judge_only', label: '仅 LLM 评判', desc: '不调被测 API，使用 Excel/表单中的「实际回答」列' },
  { value: 'fetch_only', label: '仅批量拉取并导出', desc: '调用被测 API 收集回答，写回用例并导出 Excel，不调 LLM' }
]

const apiConfigExample = `URL: https://your-qa-api.example.com/chat
方法: POST
Answer JSONPath: $.data.answer
Headers: {"Content-Type": "application/json"}
Body 模板:
{"query": "{{question}}", "session_id": "eval-batch"}`

async function downloadImportTemplate() {
  try {
    const res = await qaEvalApi.downloadImportTemplate(projectId.value)
    saveBlob(extractBlob(res), 'qa_eval_template.xlsx')
    ElMessage.success('已下载问答模板')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '下载失败')
  }
}

function goAiConfig(tab) {
  router.push({ path: '/ai-config', query: tab ? { tab } : {} })
}

/** StandardResponse: axios res.data = { code, message, data } */
function apiPayload(res) {
  const w = res?.data
  if (w && typeof w === 'object' && 'data' in w && w.code === 200) return w.data
  return w?.data ?? w
}

const DEFAULT_QUESTION_TYPES = [
  '事实性问答类',
  '归纳总结类',
  '对比分析类',
  '逻辑推理类',
  '多轮对话类'
]
const questionTypeOptions = ref([...DEFAULT_QUESTION_TYPES])

function questionTypesStorageKey() {
  return `qa_eval_question_types_${projectId.value || 'default'}`
}

function loadQuestionTypeOptions() {
  let custom = []
  try {
    custom = JSON.parse(localStorage.getItem(questionTypesStorageKey()) || '[]')
  } catch {
    custom = []
  }
  const fromCases = (cases.value || []).map((c) => (c.scenario_type || '').trim()).filter(Boolean)
  questionTypeOptions.value = [...new Set([...DEFAULT_QUESTION_TYPES, ...custom, ...fromCases])]
}

function onQuestionTypeChange(val) {
  const v = (val || '').trim()
  if (!v) return
  if (!questionTypeOptions.value.includes(v)) {
    questionTypeOptions.value = [...questionTypeOptions.value, v]
  }
  try {
    const key = questionTypesStorageKey()
    const custom = JSON.parse(localStorage.getItem(key) || '[]')
    if (!custom.includes(v)) {
      custom.push(v)
      localStorage.setItem(key, JSON.stringify(custom))
    }
  } catch {
    /* ignore */
  }
}

async function fetchQuestionTypePresets() {
  try {
    const res = await qaEvalApi.listQuestionTypes(projectId.value)
    const list = apiPayload(res)
    if (Array.isArray(list) && list.length) {
      questionTypeOptions.value = [...new Set([...list, ...questionTypeOptions.value])]
    }
  } catch {
    /* use defaults */
  }
}

const sets = ref([])
const setsLoading = ref(false)
const currentSet = ref(null)
const cases = ref([])
const runs = ref([])
const targets = ref([])
const configOptions = ref([])
const detailLoading = ref(false)
const running = ref(false)
const activeTab = ref('cases')
const activeRun = ref(null)
let pollTimer = null
const POLL_INTERVAL_MS = 2500

const setDialog = reactive({ visible: false, id: null, name: '', description: '', saving: false })
const caseDialog = reactive({
  visible: false,
  id: null,
  seq_no: null,
  question: '',
  pointsText: '',
  expected_answer: '',
  preset_answer: '',
  chatPathText: '[]',
  multi_turn: false,
  scenario_type: '',
  source_file: '',
  file_type: '',
  saving: false
})
const targetDialog = reactive({ visible: false })
const targetForm = reactive({
  visible: false,
  id: null,
  name: '',
  url: '',
  method: 'POST',
  response_type: 'json',
  sse_parser: 'qa_sse_v1',
  answer_jsonpath: '$.data.answer',
  body_template: '{"question":"{{question}}"}',
  defaultBodyText: '',
  connect_timeout_sec: 30,
  read_timeout_sec: 300,
  headersText: '{"Content-Type":"application/json"}',
  debugQuestion: '',
  debugChatPathText: '[]',
  debugHistoryFlag: false,
  debugSessionId: '',
  debugResult: null,
  testing: false,
  saving: false
})
const runDialog = reactive({
  visible: false,
  run_name: '',
  run_mode: 'auto',
  target_id: null,
  judge_config_id: null,
  case_scope: 'all',
  range_start: 1,
  range_end: null,
  retry_source_run_id: null,
  use_auto_batch: false,
  chunk_size: 100,
  request_interval_ms: 0
})
const mergeExportBatchId = ref('')
const mergeExporting = ref(false)
const selectedRunRows = ref([])

function onRunSelectionChange(rows) {
  selectedRunRows.value = rows || []
}

function buildMergePayload() {
  if (mergeExportBatchId.value) {
    return { batch_group_id: mergeExportBatchId.value }
  }
  const ids = (selectedRunRows.value || [])
    .filter((r) => r.status === 'completed')
    .map((r) => r.id)
  if (ids.length) {
    return { run_ids: ids }
  }
  return null
}
const reportDrawer = reactive({ visible: false, loading: false, run: null, results: [] })
const statsDrawer = reactive({ visible: false, loading: false, report: null })
const compareDrawer = reactive({ visible: false, loading: false, report: null })
const compareDialog = reactive({
  visible: false,
  groups: []
})
const resultDetail = reactive({ visible: false, row: null })

const currentRunModeDesc = computed(() => {
  const m = runModes.find((x) => x.value === runDialog.run_mode)
  return m?.desc || ''
})

const runSubmitLabel = computed(() => {
  if (runDialog.use_auto_batch) return '开始分批执行'
  if (runDialog.run_mode === 'fetch_only') return '开始拉取'
  if (runDialog.run_mode === 'judge_only') return '开始评判'
  return '开始评测'
})

const completedRunsForRetry = computed(() =>
  (runs.value || []).filter((r) => r.status === 'completed' || r.status === 'failed')
)

const batchGroupOptions = computed(() => {
  const map = new Map()
  for (const r of runs.value || []) {
    if (!r.batch_group_id) continue
    const namePart = r.run_name || r.display_name || ''
    const batchPart = r.batch_label || `分批 ${String(r.batch_group_id).slice(0, 8)}`
    const label = namePart ? `${namePart} · ${batchPart}` : `${batchPart} · ${r.run_mode_label || ''}`
    if (!map.has(r.batch_group_id)) {
      map.set(r.batch_group_id, label)
    }
  }
  return [...map.entries()].map(([id, label]) => ({ id, label }))
})

function extractBlob(res) {
  const raw = res?.data ?? res
  if (raw instanceof Blob) return raw
  if (raw instanceof ArrayBuffer) return new Blob([raw])
  throw new Error('下载响应无效，请稍后重试')
}

function saveBlob(blob, filename) {
  const file = blob instanceof Blob ? blob : extractBlob(blob)
  const url = URL.createObjectURL(file)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const RUN_STATUS_LABELS = {
  pending: '等待中',
  running: '执行中',
  completed: '已完成',
  failed: '失败'
}

function runStatusLabel(s) {
  return RUN_STATUS_LABELS[s] || s || '—'
}

function runStatusType(s) {
  if (s === 'completed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'running') return 'warning'
  return 'info'
}

function parsePoints(text) {
  const t = (text || '').trim()
  if (!t) return []
  if (t.includes(';') || t.includes('；')) {
    return t.split(/[;；]/).map((x) => x.trim()).filter(Boolean)
  }
  return t.split('\n').map((x) => x.trim()).filter(Boolean)
}

function parseChatPath(text) {
  const t = (text || '').trim()
  if (!t) return []
  if (t.startsWith('[')) {
    try {
      const arr = JSON.parse(t)
      if (Array.isArray(arr)) return arr.map((x) => String(x).trim()).filter(Boolean)
    } catch {
      /* fall through */
    }
  }
  if (t.includes(',') || t.includes('，')) {
    return t.split(/[,，]/).map((x) => x.trim()).filter(Boolean)
  }
  return [t]
}

function buildRunPayload() {
  const payload = {
    run_name: (runDialog.run_name || '').trim(),
    run_mode: runDialog.run_mode,
    case_scope: runDialog.use_auto_batch ? 'all' : runDialog.case_scope,
    request_interval_ms: runDialog.request_interval_ms || 0
  }
  if (runDialog.run_mode !== 'fetch_only') {
    payload.judge_config_id = runDialog.judge_config_id || undefined
  }
  if (runDialog.run_mode !== 'judge_only') {
    payload.target_id = runDialog.target_id
  }
  if (payload.case_scope === 'range') {
    payload.range_start = runDialog.range_start
    payload.range_end = runDialog.range_end ?? runDialog.range_start
  }
  if (payload.case_scope === 'retry_failed') {
    payload.retry_source_run_id = runDialog.retry_source_run_id
  }
  return payload
}

async function loadSets() {
  if (!projectId.value) return
  setsLoading.value = true
  try {
    const res = await qaEvalApi.listSets(projectId.value)
    sets.value = apiPayload(res) || []
  } finally {
    setsLoading.value = false
  }
}

async function loadTargets() {
  if (!projectId.value) return
  const res = await qaEvalApi.listTargets(projectId.value)
  targets.value = apiPayload(res) || []
}

async function loadDetail() {
  if (!currentSet.value?.id || !projectId.value) return
  detailLoading.value = true
  try {
    const [cRes, rRes] = await Promise.all([
      qaEvalApi.listCases(currentSet.value.id, projectId.value),
      qaEvalApi.listRuns(currentSet.value.id, projectId.value)
    ])
    cases.value = apiPayload(cRes) || []
    runs.value = apiPayload(rRes) || []
    loadQuestionTypeOptions()
    await syncActiveRun()
  } finally {
    detailLoading.value = false
  }
}

function stopRunPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pollRunOnce(runId) {
  if (!runId || !projectId.value) return
  try {
    const res = await qaEvalApi.getRunReport(runId, projectId.value)
    const payload = apiPayload(res)
    const run = payload?.run
    if (!run) return
    activeRun.value = run.status === 'pending' || run.status === 'running' ? run : null
    if (currentSet.value?.id === run.set_id) {
      const idx = runs.value.findIndex((r) => r.id === run.id)
      if (idx >= 0) {
        runs.value[idx] = { ...runs.value[idx], ...run }
      } else {
        runs.value = [run, ...runs.value]
      }
    }
    if (run.status === 'completed' || run.status === 'failed') {
      stopRunPolling()
      activeRun.value = null
      if (currentSet.value?.id === run.set_id) {
        await loadDetail()
      }
      if (run.status === 'completed') {
        ElMessage.success(`评测 #${run.id} 已完成，通过率 ${run.pass_rate}%`)
      } else if (run.error) {
        ElMessage.error(run.error)
      }
    }
  } catch (e) {
    console.error(e)
  }
}

function startRunPolling(runId) {
  stopRunPolling()
  if (!runId) return
  pollRunOnce(runId)
  pollTimer = setInterval(() => pollRunOnce(runId), POLL_INTERVAL_MS)
}

async function syncActiveRun() {
  if (!currentSet.value?.id || !projectId.value) {
    if (!pollTimer) activeRun.value = null
    return
  }
  try {
    const res = await qaEvalApi.getActiveRun(currentSet.value.id, projectId.value)
    const run = apiPayload(res)
    if (run && (run.status === 'pending' || run.status === 'running')) {
      activeRun.value = run
      startRunPolling(run.id)
    } else if (!pollTimer) {
      activeRun.value = null
    }
  } catch (e) {
    console.error(e)
  }
}

function onSelectSet(row) {
  currentSet.value = row || null
  if (row) loadDetail()
}

function openSetDialog(row) {
  setDialog.id = row?.id || null
  setDialog.name = row?.name || ''
  setDialog.description = row?.description || ''
  setDialog.visible = true
}

async function saveSet() {
  if (!setDialog.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  setDialog.saving = true
  try {
    const body = { name: setDialog.name.trim(), description: setDialog.description }
    if (setDialog.id) {
      await qaEvalApi.updateSet(setDialog.id, body, projectId.value)
    } else {
      await qaEvalApi.createSet(body, projectId.value)
    }
    setDialog.visible = false
    await loadSets()
    ElMessage.success('已保存')
  } finally {
    setDialog.saving = false
  }
}

async function removeSet() {
  if (!currentSet.value) return
  await ElMessageBox.confirm('确定删除该评测集及全部用例？', '提示', { type: 'warning' })
  await qaEvalApi.deleteSet(currentSet.value.id, projectId.value)
  currentSet.value = null
  cases.value = []
  runs.value = []
  await loadSets()
}

function openCaseDialog(row) {
  loadQuestionTypeOptions()
  caseDialog.id = row?.id || null
  caseDialog.seq_no = row?.seq_no ?? null
  caseDialog.question = row?.question || ''
  caseDialog.pointsText = (row?.expected_points || []).join('\n')
  caseDialog.expected_answer = row?.expected_answer || ''
  caseDialog.preset_answer = row?.preset_answer || ''
  caseDialog.chatPathText = JSON.stringify(row?.chat_path || [])
  caseDialog.multi_turn = !!row?.multi_turn
  caseDialog.scenario_type = row?.scenario_type || ''
  caseDialog.source_file = row?.source_file || ''
  caseDialog.file_type = row?.file_type || ''
  caseDialog.visible = true
}

async function saveCase() {
  const points = parsePoints(caseDialog.pointsText)
  if (!caseDialog.question.trim() || !caseDialog.expected_answer.trim()) {
    ElMessage.warning('请填写问题和标准答案')
    return
  }
  caseDialog.saving = true
  try {
    const body = {
      question: caseDialog.question.trim(),
      expected_points: points,
      expected_answer: caseDialog.expected_answer.trim(),
      preset_answer: caseDialog.preset_answer.trim() || undefined,
      seq_no: caseDialog.seq_no || undefined,
      chat_path: parseChatPath(caseDialog.chatPathText),
      multi_turn: caseDialog.multi_turn,
      scenario_type: caseDialog.scenario_type.trim(),
      source_file: caseDialog.source_file.trim(),
      file_type: caseDialog.file_type.trim()
    }
    if (caseDialog.id) {
      await qaEvalApi.updateCase(currentSet.value.id, caseDialog.id, body, projectId.value)
    } else {
      await qaEvalApi.createCase(currentSet.value.id, body, projectId.value)
    }
    caseDialog.visible = false
    await loadDetail()
    await loadSets()
    ElMessage.success('已保存')
  } finally {
    caseDialog.saving = false
  }
}

async function removeCase(row) {
  await ElMessageBox.confirm('确定删除该用例？', '提示', { type: 'warning' })
  await qaEvalApi.deleteCase(currentSet.value.id, row.id, projectId.value)
  await loadDetail()
  await loadSets()
}

async function onImportFile(file) {
  if (!currentSet.value) return false
  let replace = false
  if ((currentSet.value.case_count || 0) > 0) {
    try {
      await ElMessageBox.confirm(
        '当前评测集已有用例。选择「覆盖导入」将清空旧用例后导入；「追加导入」在保留旧用例基础上追加（可能造成序号重复）。',
        '导入方式',
        {
          type: 'warning',
          confirmButtonText: '覆盖导入',
          cancelButtonText: '追加导入',
          distinguishCancelAndClose: true
        }
      )
      replace = true
    } catch (action) {
      if (action === 'close') return false
      replace = false
    }
  }
  try {
    const res = await qaEvalApi.importCases(currentSet.value.id, file, projectId.value, replace)
    const data = apiPayload(res)
    const msg = res?.data?.message || res?.message || '导入完成'
    if (data?.missing_seq_nos?.length || data?.skipped > 0) {
      ElMessage.warning(msg)
    } else {
      ElMessage.success(msg)
    }
    await loadDetail()
    await loadSets()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '导入失败')
  }
  return false
}

async function openTargetDialog() {
  await loadTargets()
  targetDialog.visible = true
  targetForm.visible = false
}

function buildTargetConfigFromForm() {
  let headers = {}
  let default_body = null
  try {
    headers = JSON.parse(targetForm.headersText || '{}')
  } catch {
    throw new Error('Headers 须为合法 JSON')
  }
  const dbText = (targetForm.defaultBodyText || '').trim()
  if (dbText) {
    try {
      default_body = JSON.parse(dbText)
    } catch {
      throw new Error('default_body 须为合法 JSON')
    }
  }
  let default_chat_path = []
  const chatText = (targetForm.debugChatPathText || '').trim()
  if (chatText) {
    try {
      const parsed = JSON.parse(chatText)
      if (Array.isArray(parsed)) {
        default_chat_path = parsed.map((x) => String(x).trim()).filter(Boolean)
      }
    } catch {
      throw new Error('chatPath 须为合法 JSON 数组')
    }
  }
  return {
    url: targetForm.url.trim(),
    method: targetForm.method,
    response_type: targetForm.response_type || 'json',
    sse_parser: targetForm.sse_parser || QA_SSE_PARSER_V1,
    answer_jsonpath: targetForm.answer_jsonpath,
    body_template: targetForm.body_template,
    default_body,
    default_chat_path,
    connect_timeout_sec: targetForm.connect_timeout_sec || 30,
    read_timeout_sec: targetForm.read_timeout_sec || 300,
    timeout_sec: targetForm.read_timeout_sec || 300,
    headers
  }
}

function parseDebugExtra() {
  let chatPath = []
  const t = (targetForm.debugChatPathText || '').trim()
  if (t) {
    chatPath = JSON.parse(t)
  }
  return {
    chatPath,
    sessionId: targetForm.debugSessionId || '',
    historyFlag: targetForm.debugHistoryFlag
  }
}

const QA_SSE_PARSER_V1 = 'qa_sse_v1'

async function createQaSseTargetFromPreset() {
  try {
    const res = await qaEvalApi.getQaSsePreset(projectId.value)
    const payload = apiPayload(res)
    const body = {
      name: payload?.name || '问答 SSE（流式）',
      config: { ...(payload?.config || {}) }
    }
    const url = body.config.url || ''
    if (!url || String(url).includes('your-')) {
      const { value } = await ElMessageBox.prompt('请填写问答接口 URL', '创建被测 API', {
        inputPlaceholder: 'https://your-host/api/v1/qa',
        confirmButtonText: '创建'
      })
      body.config.url = (value || '').trim()
      if (!body.config.url) {
        ElMessage.warning('URL 不能为空')
        return
      }
    }
    await qaEvalApi.createTarget(body, projectId.value)
    await loadTargets()
    ElMessage.success('已创建流式被测 API 配置，请在列表中编辑 Headers 密钥')
    targetDialog.visible = true
  } catch (e) {
    if (e === 'cancel' || e?.message === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '创建失败')
  }
}

async function applyQaSsePreset() {
  try {
    const res = await qaEvalApi.getQaSsePreset(projectId.value)
    const payload = apiPayload(res)
    targetForm.visible = true
    targetForm.name = payload?.name || '问答 SSE（流式）'
    const cfg = payload?.config || {}
    targetForm.url = cfg.url || ''
    targetForm.method = cfg.method || 'POST'
    targetForm.response_type = cfg.response_type || 'sse'
    targetForm.sse_parser = cfg.sse_parser || QA_SSE_PARSER_V1
    targetForm.answer_jsonpath = cfg.answer_jsonpath || ''
    targetForm.body_template = cfg.body_template || ''
    targetForm.defaultBodyText = cfg.default_body
      ? JSON.stringify(cfg.default_body, null, 2)
      : ''
    targetForm.connect_timeout_sec = cfg.connect_timeout_sec || 30
    targetForm.read_timeout_sec = cfg.read_timeout_sec || 300
    targetForm.headersText = JSON.stringify(cfg.headers || {}, null, 2)
    if (payload?.header_hint) {
      ElMessage.info({ message: payload.header_hint, duration: 8000, showClose: true })
    }
    ElMessage.success('已填入 SSE 流式模板，请补全 URL、Headers 与 default_body 中的目录参数')
  } catch (e) {
    ElMessage.error(e?.message || '加载模板失败')
  }
}

function openTargetForm(row, focusDebug = false) {
  targetForm.visible = true
  targetForm.id = row?.id || null
  targetForm.name = row?.name || ''
  const cfg = row?.config || {}
  targetForm.url = cfg.url || ''
  targetForm.method = cfg.method || 'POST'
  targetForm.response_type = cfg.response_type || 'json'
  targetForm.sse_parser = cfg.sse_parser || QA_SSE_PARSER_V1
  targetForm.answer_jsonpath = cfg.answer_jsonpath || '$.data.answer'
  targetForm.body_template = cfg.body_template || '{"question":"{{question}}"}'
  targetForm.defaultBodyText = cfg.default_body ? JSON.stringify(cfg.default_body, null, 2) : ''
  targetForm.connect_timeout_sec = cfg.connect_timeout_sec || 30
  targetForm.read_timeout_sec = cfg.read_timeout_sec || cfg.timeout_sec || 300
  targetForm.headersText = JSON.stringify(cfg.headers || { 'Content-Type': 'application/json' }, null, 2)
  targetForm.debugChatPathText = JSON.stringify(cfg.default_chat_path || [])
  targetForm.debugResult = null
  if (focusDebug && !targetForm.debugQuestion) {
    targetForm.debugQuestion = '概括 SOP-5000 项目团队的人员配置情况。'
  }
}

async function runTargetTest() {
  if (!targetForm.debugQuestion.trim()) {
    ElMessage.warning('请填写测试问题')
    return
  }
  let config
  try {
    config = buildTargetConfigFromForm()
  } catch (e) {
    ElMessage.warning(e.message)
    return
  }
  if (!config.url) {
    ElMessage.warning('请填写 URL')
    return
  }
  let extra
  try {
    extra = parseDebugExtra()
  } catch {
    ElMessage.warning('chatPath 须为合法 JSON 数组')
    return
  }
  targetForm.testing = true
  targetForm.debugResult = null
  try {
    const res = await qaEvalApi.testTarget(
      { question: targetForm.debugQuestion.trim(), config, extra },
      projectId.value,
      targetForm.id || null
    )
    targetForm.debugResult = apiPayload(res)
  } catch (e) {
    targetForm.debugResult = {
      success: false,
      api_error: e?.response?.data?.detail || e?.message || '请求失败',
      api_latency_ms: 0
    }
  } finally {
    targetForm.testing = false
  }
}

async function saveTarget() {
  let config
  try {
    config = buildTargetConfigFromForm()
  } catch (e) {
    ElMessage.warning(e.message)
    return
  }
  targetForm.saving = true
  try {
    const body = { name: targetForm.name.trim(), config }
    if (targetForm.id) {
      await qaEvalApi.updateTarget(targetForm.id, body, projectId.value)
    } else {
      await qaEvalApi.createTarget(body, projectId.value)
    }
    await loadTargets()
    targetForm.visible = false
    ElMessage.success('已保存')
  } finally {
    targetForm.saving = false
  }
}

async function removeTarget(row) {
  await ElMessageBox.confirm('确定删除？', '提示', { type: 'warning' })
  await qaEvalApi.deleteTarget(row.id, projectId.value)
  await loadTargets()
}

async function exportCurrentSet() {
  if (!currentSet.value) return
  try {
    const res = await qaEvalApi.exportSetCases(currentSet.value.id, projectId.value)
    saveBlob(extractBlob(res), `${currentSet.value.name || 'qa_eval'}_用例.xlsx`)
    ElMessage.success('已导出')
  } catch (e) {
    ElMessage.error(e?.message || '导出失败')
  }
}

async function downloadRunExport(row) {
  if (!row?.id) return
  try {
    const res = await qaEvalApi.exportRunAnswers(row.id, projectId.value)
    saveBlob(extractBlob(res), `qa_eval_run_${row.id}.xlsx`)
    ElMessage.success('已下载')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '导出失败')
  }
}

async function loadConfigOptions() {
  try {
    const res = await aiConfigApi.getSelectOptions()
    const data = apiPayload(res)
    const list = Array.isArray(data) ? data : (data?.list || [])
    configOptions.value = list.filter((c) => c.is_enabled !== false)
  } catch {
    try {
      const res = await aiConfigApi.getList({ size: 200 })
      const data = apiPayload(res)
      configOptions.value = (data?.list || []).filter((c) => c.is_enabled !== false)
    } catch {
      configOptions.value = []
    }
  }
}

async function openRunDialog() {
  await loadTargets()
  if (runDialog.run_mode !== 'fetch_only') {
    await loadConfigOptions()
  }
  runDialog.run_name = currentSet.value?.name || ''
  runDialog.target_id = targets.value[0]?.id || null
  runDialog.judge_config_id = null
  runDialog.case_scope = 'all'
  runDialog.range_start = 1
  runDialog.range_end = currentSet.value?.case_count || null
  runDialog.retry_source_run_id = null
  runDialog.use_auto_batch = (currentSet.value?.case_count || 0) > 500
  runDialog.chunk_size = 100
  runDialog.request_interval_ms = 0
  runDialog.visible = true
}

async function removeRun(row) {
  if (!row?.id) return
  const label = row.display_name || row.run_name || row.status_label || runStatusLabel(row.status)
  await ElMessageBox.confirm(
    `确定删除跑批记录 #${row.id}（${label}）？将同时删除其全部评测结果，且不可恢复。`,
    '提示',
    { type: 'warning' }
  )
  try {
    await qaEvalApi.deleteRun(row.id, projectId.value)
    runs.value = (runs.value || []).filter((r) => r.id !== row.id)
    selectedRunRows.value = (selectedRunRows.value || []).filter((r) => r.id !== row.id)
    if (activeRun.value?.id === row.id) {
      activeRun.value = null
      stopRunPolling()
    }
    if (reportDrawer.run?.id === row.id) {
      reportDrawer.visible = false
      reportDrawer.run = null
    }
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

function retryFailedRun(row) {
  runDialog.run_name = row.run_name || row.display_name || `${currentSet.value?.name || '评测'} · 重跑失败`
  runDialog.run_mode = row.run_mode || 'auto'
  runDialog.target_id = row.target_id || targets.value[0]?.id || null
  runDialog.case_scope = 'retry_failed'
  runDialog.retry_source_run_id = row.id
  runDialog.use_auto_batch = false
  runDialog.visible = true
}

async function downloadMergedExport() {
  const payload = buildMergePayload()
  if (!payload || !currentSet.value) {
    ElMessage.warning('请选择自动分批任务，或勾选已完成的跑批记录')
    return
  }
  mergeExporting.value = true
  try {
    ElMessage.info('正在合并导出，数据量大时请稍候…')
    const res = await qaEvalApi.mergeExportRuns(
      currentSet.value.id,
      payload,
      projectId.value
    )
    saveBlob(extractBlob(res), `${currentSet.value.name || 'qa_eval'}_合并.xlsx`)
    ElMessage.success('已下载合并结果')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '合并导出失败')
  } finally {
    mergeExporting.value = false
  }
}

function runOptionLabel(r) {
  const parts = [
    r.create_time,
    r.target_name || '—',
    r.case_scope_label || '',
    r.batch_label || '',
    r.avg_score != null ? `均分${r.avg_score}` : ''
  ].filter(Boolean)
  return `#${r.id} ${parts.join(' · ')}`
}

function newCompareGroup(partial = {}) {
  return {
    label: partial.label || '',
    sourceType: partial.sourceType || 'runs',
    run_ids: partial.run_ids ? [...partial.run_ids] : [],
    batch_group_id: partial.batch_group_id || ''
  }
}

function openCompareDialog() {
  const prefill = (selectedRunRows.value || [])
    .filter((r) => r.status === 'completed')
    .map((r) => r.id)
  compareDialog.groups = [
    newCompareGroup({ label: '迭代 A', run_ids: prefill.length ? [...prefill] : [] }),
    newCompareGroup({ label: '迭代 B' })
  ]
  compareDialog.visible = true
}

function addCompareGroup() {
  if (compareDialog.groups.length >= 10) {
    ElMessage.warning('最多 10 个对比组')
    return
  }
  compareDialog.groups.push(newCompareGroup({ label: `迭代 ${String.fromCharCode(65 + compareDialog.groups.length)}` }))
}

function addCompareGroupFromSelection() {
  const ids = (selectedRunRows.value || [])
    .filter((r) => r.status === 'completed')
    .map((r) => r.id)
  if (!ids.length) {
    ElMessage.warning('请先勾选已完成的跑批记录')
    return
  }
  if (compareDialog.groups.length >= 10) {
    ElMessage.warning('最多 10 个对比组')
    return
  }
  compareDialog.groups.push(
    newCompareGroup({ label: `迭代 ${compareDialog.groups.length + 1}`, run_ids: ids })
  )
}

function removeCompareGroup(idx) {
  compareDialog.groups.splice(idx, 1)
}

function buildComparePayload() {
  return {
    groups: compareDialog.groups.map((g) => {
      const label = (g.label || '').trim()
      if (g.sourceType === 'batch' && g.batch_group_id) {
        return { label, batch_group_id: g.batch_group_id }
      }
      return { label, run_ids: g.run_ids || [] }
    })
  }
}

async function runCompareReport() {
  if (!currentSet.value) return
  const payload = buildComparePayload()
  if (payload.groups.length < 2) {
    ElMessage.warning('至少需要 2 个对比组')
    return
  }
  for (const g of payload.groups) {
    if (!g.label) {
      ElMessage.warning('请填写每个对比组的名称')
      return
    }
    if (!g.run_ids?.length && !g.batch_group_id) {
      ElMessage.warning(`对比组「${g.label}」请选择跑批或分批任务`)
      return
    }
  }
  compareDrawer.loading = true
  compareDrawer.report = null
  try {
    const res = await qaEvalApi.compareRunsReport(
      currentSet.value.id,
      payload,
      projectId.value
    )
    compareDrawer.report = apiPayload(res)
    compareDialog.visible = false
    compareDrawer.visible = true
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '对比失败')
  } finally {
    compareDrawer.loading = false
  }
}

function compareMetricValue(row, label) {
  const hit = (row.values || []).find((v) => v.label === label)
  const v = hit?.value
  return v === null || v === undefined || v === '' ? '—' : v
}

function compareLevelCell(row, label) {
  const hit = (row.cells || []).find((c) => c.label === label)
  if (!hit || !hit.count) return '—'
  return `${hit.count}（${hit.rate}%）`
}

function compareScenarioCell(row, label) {
  const hit = (row.cells || []).find((c) => c.label === label)
  if (!hit || !hit.count) return '—'
  return hit.avg_score_100 != null ? `${hit.avg_score_100}（${hit.count}题）` : '—'
}

function compareQuestionCell(row, label) {
  return (row.cells || []).find((c) => c.label === label)
}

async function openMergedStatsReport() {
  const payload = buildMergePayload()
  if (!payload || !currentSet.value) {
    ElMessage.warning('请选择自动分批任务，或勾选已完成的跑批记录')
    return
  }
  statsDrawer.visible = true
  statsDrawer.loading = true
  statsDrawer.report = null
  try {
    const res = await qaEvalApi.mergeStatsReport(
      currentSet.value.id,
      payload,
      projectId.value
    )
    statsDrawer.report = apiPayload(res)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载合并统计失败')
    statsDrawer.visible = false
  } finally {
    statsDrawer.loading = false
  }
}

async function doRun() {
  if (runDialog.run_mode !== 'judge_only' && !runDialog.target_id) {
    ElMessage.warning('请选择被测 API')
    return
  }
  if (runDialog.case_scope === 'range' && !runDialog.use_auto_batch) {
    if (!runDialog.range_start || !runDialog.range_end) {
      ElMessage.warning('请填写序号范围')
      return
    }
  }
  if (runDialog.case_scope === 'retry_failed' && !runDialog.retry_source_run_id) {
    ElMessage.warning('请选择来源跑批任务')
    return
  }
  running.value = true
  try {
    const payload = buildRunPayload()
    let res
    if (runDialog.use_auto_batch) {
      res = await qaEvalApi.runEvalBatch(
        currentSet.value.id,
        { ...payload, chunk_size: runDialog.chunk_size },
        projectId.value
      )
    } else {
      res = await qaEvalApi.runEval(currentSet.value.id, payload, projectId.value)
    }
    runDialog.visible = false
    ElMessage.success(res?.data?.message || '评测任务已提交')
    activeTab.value = 'runs'
    const data = apiPayload(res)
    const run = data?.first_run || data
    if (data?.batch_group_id) {
      mergeExportBatchId.value = data.batch_group_id
    }
    if (run?.id) {
      activeRun.value = run
      startRunPolling(run.id)
      await loadDetail()
    } else {
      await loadDetail()
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.message || ''
    if (e?.response?.status === 409) {
      ElMessage.warning(typeof detail === 'string' ? detail : '已有进行中的评测')
      await syncActiveRun()
    } else {
      ElMessage.error(typeof detail === 'string' ? detail : '提交失败')
    }
  } finally {
    running.value = false
  }
}

async function openReport(row) {
  reportDrawer.visible = true
  reportDrawer.loading = true
  try {
    const res = await qaEvalApi.getRunReport(row.id, projectId.value)
    const payload = apiPayload(res)
    reportDrawer.run = payload?.run
    reportDrawer.results = payload?.results || []
  } finally {
    reportDrawer.loading = false
  }
}

async function openStatsReport(row) {
  statsDrawer.visible = true
  statsDrawer.loading = true
  statsDrawer.report = null
  try {
    const res = await qaEvalApi.getStatsReport(row.id, projectId.value)
    statsDrawer.report = apiPayload(res)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载统计失败')
    statsDrawer.visible = false
  } finally {
    statsDrawer.loading = false
  }
}

async function regenerateResult(row) {
  if (!reportDrawer.run?.id || !row?.id) return
  row._regenerating = true
  try {
    const res = await qaEvalApi.regenerateResult(
      reportDrawer.run.id,
      row.id,
      projectId.value
    )
    const payload = apiPayload(res)
    const updated = payload?.result
    if (updated) {
      Object.assign(row, updated)
    }
    if (payload?.run) {
      reportDrawer.run = { ...reportDrawer.run, ...payload.run }
    }
    ElMessage.success('已重新生成')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '重新生成失败')
  } finally {
    row._regenerating = false
  }
}

async function reviewOne(row, status) {
  if (!reportDrawer.run?.id || !row?.id) return
  try {
    await qaEvalApi.reviewResult(
      reportDrawer.run.id,
      row.id,
      { manual_status: status },
      projectId.value
    )
    row.manual_status = status
    row.manual_status_label = status === 'approved' ? '已通过' : status === 'rejected' ? '已驳回' : '待审核'
    ElMessage.success('已保存审核')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  }
}

async function bulkApproveFailed() {
  if (!reportDrawer.run?.id) return
  const ids = (reportDrawer.results || [])
    .filter((r) => !r.passed && r.manual_status !== 'approved')
    .map((r) => r.id)
  if (!ids.length) {
    ElMessage.info('没有需要批量通过的未过题')
    return
  }
  try {
    await qaEvalApi.bulkReviewResults(
      reportDrawer.run.id,
      { result_ids: ids, manual_status: 'approved', manual_comment: '人工确认可接受' },
      projectId.value
    )
    await openReport({ id: reportDrawer.run.id })
    ElMessage.success(`已批量通过 ${ids.length} 条`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '批量审核失败')
  }
}

function showResultDetail(row) {
  resultDetail.row = row
  resultDetail.visible = true
}

watch(projectId, () => {
  stopRunPolling()
  activeRun.value = null
  currentSet.value = null
  loadSets()
  loadTargets()
})

watch(
  () => runDialog.run_mode,
  (mode) => {
    if (runDialog.visible && mode !== 'fetch_only' && !configOptions.value.length) {
      loadConfigOptions()
    }
  }
)

watch(batchGroupOptions, (opts) => {
  if (opts.length && !mergeExportBatchId.value) {
    mergeExportBatchId.value = opts[opts.length - 1].id
  }
})

onMounted(() => {
  loadSets()
  loadTargets()
  fetchQuestionTypePresets()
})

onUnmounted(() => {
  stopRunPolling()
})
</script>

<style scoped>
.page-sub {
  margin-left: 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  font-weight: normal;
}
.guide-card {
  margin-bottom: 16px;
}
.guide-card :deep(.el-card__header) {
  padding: 10px 16px;
}
.guide-card :deep(.el-card__body) {
  padding: 12px 16px 16px;
}
.guide-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.guide-title {
  font-weight: 600;
  font-size: 14px;
}
.guide-steps {
  margin: 0 0 16px;
  padding-left: 20px;
  line-height: 1.75;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.guide-steps li {
  margin-bottom: 6px;
}
.guide-section {
  margin-top: 12px;
}
.guide-section-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}
.guide-table {
  margin-bottom: 8px;
}
.guide-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.guide-code {
  margin: 0;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  color: var(--el-text-color-regular);
}
.guide-footer {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.guide-collapsed-bar {
  margin-bottom: 12px;
}
.run-progress-alert {
  margin-bottom: 16px;
}
.run-progress-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}
.run-progress-text {
  color: var(--el-text-color-regular);
}
.run-current-q {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.main-row {
  margin-top: 0;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: flex-end;
}
.toolbar {
  margin-bottom: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.run-hint,
.run-mode-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0;
  line-height: 1.5;
}
.run-mode-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}
.run-actions {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  white-space: nowrap;
  gap: 2px;
}
.run-actions .el-button {
  padding: 0 4px;
}
.col-tip {
  cursor: help;
  border-bottom: 1px dashed var(--el-text-color-secondary);
}
.answer-pre {
  white-space: pre-wrap;
  background: var(--el-fill-color-light);
  padding: 8px;
  border-radius: 4px;
  max-height: 200px;
  overflow: auto;
  font-size: 12px;
}
.err {
  color: var(--el-color-danger);
}
.report-summary {
  margin-bottom: 12px;
}
.runs-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.seq-count-warn {
  margin-left: 2px;
  color: var(--el-color-warning);
  font-weight: 700;
  cursor: help;
}
.stats-merge-hint {
  margin: 0 0 6px;
}
.stats-merge-detail {
  margin: 0 0 6px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}
.merge-run-chip {
  margin-right: 12px;
}
.compare-group-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
  background: var(--el-fill-color-blank);
}
.compare-group-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
  font-size: 13px;
}
.compare-group-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.stats-block {
  margin-bottom: 16px;
}
.stats-h4 {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
}
.header-hint {
  display: block;
  margin-top: 6px;
  line-height: 1.5;
}
.target-toolbar {
  margin-bottom: 8px;
}
.inline-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.target-debug-result {
  margin-top: 8px;
  padding: 10px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}
.debug-raw {
  max-height: 160px;
}
.case-dialog-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
