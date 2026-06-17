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
        <el-form-item label="所属目录">
          <CatalogTreeSelect
            v-model="form.catalog_id"
            :project-id="proStore.projectInfo.id"
            placeholder="请选择所属目录"
          />
        </el-form-item>

        <!-- 压测模式 -->
        <el-divider content-position="left">压测模式</el-divider>
        <el-collapse v-model="modeGuideExpanded" class="mode-guide-collapse">
          <el-collapse-item title="压测模式说明（适用场景与选型参考）" name="guide">
            <div class="mode-guide-list">
              <div
                v-for="item in perfModeGuides"
                :key="item.mode"
                class="mode-guide-item"
                :class="{ active: isModeGuideActive(item.mode) }"
              >
                <div class="mode-guide-title">{{ item.title }}</div>
                <div class="mode-guide-desc">{{ item.summary }}</div>
                <div class="mode-guide-scenes"><span class="label">适用场景：</span>{{ item.scenes }}</div>
                <div v-if="item.metrics" class="mode-guide-metrics"><span class="label">关注指标：</span>{{ item.metrics }}</div>
              </div>
            </div>
            <div class="mode-guide-extra">
              <span class="label">流式问答开关：</span>
              在固定/循环/梯度/链路模式下可启用，将 HTTP 压测切换为 SSE 流式采集（首字时间、阶段耗时等）；关闭则按普通 HTTP 请求统计 QPS 与响应时间。
            </div>
          </el-collapse-item>
        </el-collapse>
        <el-form-item label="模式选择" prop="config.mode">
                  <div class="mode-wrap">
            <el-radio-group v-model="form.config.mode" @change="onModeChange">
              <el-radio-button label="fixed">固定模式</el-radio-button>
              <el-radio-button label="loop">循环模式</el-radio-button>
              <el-radio-button label="stepping">梯度模式</el-radio-button>
              <el-radio-button label="stream_burst">流式阶段压测</el-radio-button>
              <el-radio-button label="journey_fixed">链路固定</el-radio-button>
              <el-radio-button label="journey_loop">链路循环</el-radio-button>
            </el-radio-group>
            <div class="mode-hint">
              <el-tag v-if="form.config.mode === 'fixed'" size="small" type="info">固定并发数，持续指定时间</el-tag>
              <el-tag v-if="form.config.mode === 'loop'" size="small" type="info">固定并发数，每个用户循环指定次数</el-tag>
              <el-tag v-if="form.config.mode === 'stepping'" size="small" type="info">分阶段递增并发，每阶段持续指定时间</el-tag>
              <el-tag v-if="isStreamBurst" size="small" type="warning">流式并发单次：每用户 1 次，按解析器采集阶段计时</el-tag>
              <el-tag v-if="isJourneyMode" size="small" type="success">业务链路：每用户按阶段顺序/并行执行，支持变量传递与阶段同步</el-tag>
              <el-tag v-if="form.config.mode === 'fixed' && enableStreamQA" size="small" type="success">流式持续压测：固定并发在持续时间内循环发起流式问答</el-tag>
              <el-tag v-if="form.config.mode === 'stepping' && enableStreamQA" size="small" type="success">流式梯度压测：分阶段递增并发，每阶段持续流式问答</el-tag>
            </div>
          </div>
        </el-form-item>

        <el-form-item v-if="!isStreamBurst" label="流式问答">
          <el-switch
            v-model="enableStreamQA"
            active-text="启用"
            inactive-text="关闭"
            @change="onStreamToggle"
          />
          <div class="field-tip">启用后按 SSE 流式解析器采集首字、整体耗时等阶段指标；关闭则按普通 HTTP 请求压测</div>
        </el-form-item>

        <!-- 分配模式 -->
        <el-form-item v-if="!isJourneyMode" label="分配模式">
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
          <el-slider v-model="form.config.concurrent_users" :min="1" :max="form.config.mode === 'sse_burst' ? 1000 : 1000" show-stops show-input />
          <div class="field-tip" v-if="isStreamBurst">
            同时发起的流式虚拟用户数，每人只发送 1 次请求；高并发建议勾选分布式 Worker 执行
          </div>
          <div class="field-tip" v-else>
            同时发起请求的虚拟用户数，建议不超过 500；超过 500 请确保服务器有足够 CPU 和网络带宽
          </div>
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

        <!-- 链路固定模式 -->
        <template v-if="form.config.mode === 'journey_fixed'">
          <el-form-item label="持续时间" prop="config.duration_seconds">
            <el-input-number v-model="form.config.duration_seconds" :min="1" :max="3600" />
            <span class="unit">秒（每位用户在此时间内反复执行完整链路）</span>
          </el-form-item>
        </template>

        <!-- 链路循环模式 -->
        <template v-if="form.config.mode === 'journey_loop'">
          <el-form-item label="链路次数" prop="config.loop_count">
            <el-input-number v-model="form.config.loop_count" :min="1" :max="100000" />
            <span class="unit">次（每个并发用户执行的完整链路次数）</span>
          </el-form-item>
        </template>

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

        <!-- 流式问答配置（固定/梯度持续压测 或 流式阶段单次） -->
        <template v-if="showStreamConfig && form.config.stream_profile">
          <el-divider content-position="left">流式配置</el-divider>
          <el-form-item label="解析器">
            <el-select v-model="form.config.stream_profile.parser_id" style="width: 280px" @change="onParserChange">
              <el-option
                v-for="p in parserList"
                :key="p.parser_id"
                :label="p.display_name"
                :value="p.parser_id"
              >
                <span>{{ p.display_name }}</span>
                <span v-if="p.supports_rule_builder" style="float: right; color: var(--el-color-primary); font-size: 12px">可自定义规则</span>
              </el-option>
            </el-select>
            <div class="field-tip">
              常见问答 SSE 选「问答流式 v1」；协议字段变更时，在下拉框选择「规则配置」，下方会出现阶段匹配规则编辑器
            </div>
          </el-form-item>
          <el-form-item label="请求超时">
            <el-input-number v-model="form.config.stream_profile.timeout_seconds" :min="30" :max="3600" />
            <span class="unit">秒</span>
          </el-form-item>
          <el-form-item label="成功判定">
            <el-select v-model="successPhaseKey" style="width: 200px" @change="onSuccessRuleChange">
              <el-option label="阶段出现即成功" value="phase_exists" />
              <el-option label="HTTP 2xx 即成功" value="status_ok" />
            </el-select>
            <el-select
              v-if="successPhaseKey === 'phase_exists'"
              v-model="form.config.stream_profile.success_rule.phase"
              style="width: 180px; margin-left: 12px"
              placeholder="选择阶段"
            >
              <el-option
                v-for="s in currentPhaseSchema"
                :key="s.key"
                :label="s.label"
                :value="s.key"
              />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.config.stream_profile.parser_id === 'rule_based'" label="规则配置">
            <StreamRuleBuilder v-model="form.config.stream_profile.parser_options.rules" />
          </el-form-item>
        </template>

        <!-- 业务链路配置 -->
        <template v-if="isJourneyMode">
          <el-divider content-position="left">业务链路</el-divider>
          <el-alert type="info" :closable="false" show-icon style="margin: 0 0 12px 120px;"
            title="并发 N = N 条链路同时执行（非 N×步骤数）。步骤间变量通过用例 extractors 传递；阶段 sync 在本机/单 Worker 内齐步走。" />
          <el-form-item label="失败策略">
            <el-switch v-model="form.config.journey.stop_on_step_fail" active-text="步骤失败中断链路" inactive-text="继续执行" />
          </el-form-item>
          <el-form-item label="链路间隔">
            <el-input-number v-model="form.config.journey.delay_between_journeys_ms" :min="0" :max="60000" />
            <span class="unit">ms（每条链路完成后的等待）</span>
          </el-form-item>
          <el-form-item label="业务阶段">
            <div class="journey-phases">
              <div v-for="(phase, pIdx) in form.config.journey.phases" :key="pIdx" class="journey-phase-card">
                <div class="journey-phase-header">
                  <el-input v-model="phase.name" placeholder="阶段名称" style="width: 160px" />
                  <el-select v-model="phase.execution" style="width: 100px">
                    <el-option label="串行" value="serial" />
                    <el-option label="并行" value="parallel" />
                  </el-select>
                  <el-input-number v-if="phase.execution === 'parallel'" v-model="phase.max_parallel" :min="1" :max="50" />
                  <span v-if="phase.execution === 'parallel'" class="unit">最大并行</span>
                  <el-checkbox v-model="phase.sync_before">阶段前同步</el-checkbox>
                  <el-button type="danger" size="small" circle :icon="Delete" @click="removeJourneyPhase(pIdx)" />
                </div>
                <el-table :data="phase.steps" size="small" border style="width: 100%; margin-top: 8px;">
                  <el-table-column label="顺序" width="60" align="center">
                    <template #default="{ $index }">{{ $index + 1 }}</template>
                  </el-table-column>
                  <el-table-column label="用例" min-width="220">
                    <template #default="{ row }">
                      <el-select v-model="row.case_id" filterable placeholder="选择用例" style="width: 100%">
                        <el-option v-for="c in allCases" :key="c.id" :label="`${c.name} [${c.api?.method || c.api_method || ''}]`" :value="c.id" />
                      </el-select>
                    </template>
                  </el-table-column>
                  <el-table-column label="间隔(ms)" width="110" align="center">
                    <template #default="{ row }">
                      <el-input-number v-model="row.delay_ms" :min="0" :max="60000" size="small" style="width: 90px" />
                    </template>
                  </el-table-column>
                  <el-table-column label="流式" width="70" align="center">
                    <template #default="{ row }">
                      <el-checkbox v-model="row.use_stream" :disabled="!enableStreamQA && !form.config.stream_profile" />
                    </template>
                  </el-table-column>
                  <el-table-column width="60" align="center">
                    <template #default="{ $index }">
                      <el-button type="danger" size="small" link @click="removeJourneyStep(pIdx, $index)">删</el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <el-button type="primary" size="small" :icon="Plus" style="margin-top: 8px" @click="addJourneyStep(pIdx)">添加步骤</el-button>
              </div>
              <el-button type="primary" size="small" :icon="Plus" @click="addJourneyPhase">添加阶段</el-button>
            </div>
          </el-form-item>
        </template>

        <!-- 用例选择 -->
        <el-divider v-if="!isJourneyMode" content-position="left">场景用例</el-divider>
        <el-alert
          v-if="showStreamConfig"
          type="info"
          :closable="false"
          show-icon
          style="margin: 0 0 12px 120px;"
          :title="isStreamBurst
            ? '流式阶段压测需配置支持 SSE 流式响应的接口用例（通常为 POST + JSON）；建议只选 1 个用例。'
            : '流式持续/梯度压测需配置支持 SSE 的问答用例；固定模式在持续时间内循环发问，梯度模式按阶段递增并发。'"
        />
        <p class="field-tip" style="margin: 0 0 12px 120px;">
          压测会合并项目/环境变量、数据工厂标签 <code v-pre>${{df:标签名}}</code>，以及关联接口用例中的
          <strong>内联工具</strong> <code v-pre>${{dt:md5|text=@a}}</code>（在接口/Web 用例编辑页点「插入工具」配置；固定值用引号如 <code v-pre>"test@163.com"</code>）。
          同一轮压测内相同 <code v-pre>dt:</code> 表达式只计算一次，随机数保持一致。
        </p>
        <el-form-item v-if="!isJourneyMode" label="选择用例" prop="scene_items">
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
          <div v-if="casesLoading" class="field-tip">正在加载接口用例…</div>
          <div v-else-if="allCases.length === 0" class="field-tip case-empty-tip">
            当前项目暂无接口用例。请先在
            <el-link type="primary" @click="router.push('/api-case')">接口用例</el-link>
            中创建支持 SSE 流式响应的 POST 用例后再回来选择。
          </div>
        </el-form-item>

        <!-- 已选用例配置 -->
        <el-form-item v-if="!isJourneyMode" label="用例配置" v-show="selectedCases.length > 0">
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
              v-if="!isEdit"
              type="warning"
              :closable="false"
              show-icon
              style="margin-bottom: 12px;"
              title="请先保存场景，保存成功后再回来上传 CSV 文件。"
            />
            <el-alert
              type="info"
              :closable="false"
              style="margin-bottom: 12px;"
            >
              <template #title>
                <div style="font-weight: 600; margin-bottom: 6px;">CSV 参数化使用说明（含流式问答批量问题）</div>
              </template>
              <div style="font-size: 13px; line-height: 1.8;">
                <div><b>Step 1 — 准备 CSV</b></div>
                <div>　• 第一行必须是<b>英文列名</b>（如 question），UTF-8 编码，最多 10000 行</div>
                <div>　• 问答压测示例：</div>
                <div>　<code style="background:#f5f7fa;padding:2px 6px;border-radius:4px;">question</code></div>
                <div>　<code style="background:#f5f7fa;padding:2px 6px;border-radius:4px;">什么是知识库？</code></div>
                <div>　<code style="background:#f5f7fa;padding:2px 6px;border-radius:4px;">如何创建应用？</code></div>
                <div style="margin-top: 4px;"><b>Step 2 — 上传 CSV</b></div>
                <div>　• 编辑已保存的场景，点击「上传 CSV」；上传后可预览前 5 行</div>
                <div style="margin-top: 4px;"><b>Step 3 — 在用例 Body 中引用</b></div>
                <div>　• 写法：<code v-pre style="background:#f5f7fa;padding:2px 6px;border-radius:4px;">${{csv.列名}}</code>（兼容旧写法 <code v-pre>{{csv.列名}}</code>）</div>
                <div>　• 问答 Body 示例：<code v-pre style="background:#f5f7fa;padding:2px 6px;border-radius:4px;">{"question":"${{csv.question}}"}</code></div>
                <div>　• 可用于 Body、Query、Header、URL 路径</div>
                <div style="margin-top: 4px;"><b>Step 4 — 选择分配策略</b></div>
                <div>　• <b>顺序轮询</b>：所有请求按 CSV 行号依次取下一题，<b>最后一题用完后从第一题重新开始</b>（持续压测推荐）</div>
                <div>　• <b>随机</b>：每次请求随机抽一行问题，适合题库很大、不要求按序覆盖的场景</div>
                <div>　• <b>分区独占</b>：每个并发虚拟用户独立顺序取题并循环，互不抢同一行（多用户并行时更均匀）</div>
                <div style="margin-top: 4px; color: #409eff;">💡 固定/梯度 + 流式问答模式下同样生效；每次新请求都会替换 <code v-pre>${{csv.question}}</code> 后再发起 SSE。</div>
              </div>
            </el-alert>
            <div v-if="!csvInfo.hasCSV" style="display: flex; align-items: center; gap: 12px;">
              <el-upload
                accept=".csv"
                :show-file-list="false"
                :auto-upload="false"
                :disabled="!isEdit"
                :on-change="handleCSVUpload"
              >
                <el-button type="primary" :icon="Upload" :disabled="!isEdit">上传 CSV 文件</el-button>
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
                  <el-radio-button label="round_robin">顺序轮询</el-radio-button>
                  <el-radio-button label="random">随机</el-radio-button>
                  <el-radio-button label="unique">分区独占</el-radio-button>
                </el-radio-group>
                <el-tooltip placement="top">
                  <template #content>
                    <div><b>顺序轮询</b>：全局按行依次取题，用完最后一行后从第一行重新开始</div>
                    <div style="margin-top:4px;"><b>随机</b>：每次请求随机抽一行</div>
                    <div style="margin-top:4px;"><b>分区独占</b>：每个并发用户独立顺序取题并循环（分布式多 Worker 时各节点内独立轮询）</div>
                  </template>
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="field-tip" style="margin-top: 8px;">
                当前策略：<strong>{{ csvStrategyLabel }}</strong>。
                用例 Body 中写 <code v-pre>${{csv.question}}</code> 即可把 CSV 里的 question 列填入每次请求。
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
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import StreamRuleBuilder from '@/components/perf/StreamRuleBuilder.vue'
import { perfSceneApi, httpCaseApi } from '@/api'
import { perfSceneApi as perfSceneApiCSV, perfStreamParserApi } from '@/api/modules/perf'
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
const enableStreamQA = ref(false)
const casesLoading = ref(false)
const successPhaseKey = ref('phase_exists')
const modeGuideExpanded = ref([])

const perfModeGuides = [
  {
    mode: 'fixed',
    title: '固定模式',
    summary: '维持固定并发用户数，在设定时长内持续发起请求，总请求量由并发与时长共同决定。',
    scenes: '接口基准性能评估、稳定负载下的容量摸底、长时间稳定性观察、发布前常规压测。',
    metrics: 'QPS、平均/P95 响应时间、错误率、网络吞吐。'
  },
  {
    mode: 'loop',
    title: '循环模式',
    summary: '维持固定并发，每个虚拟用户执行指定次数后结束，总请求量 = 并发数 × 循环次数。',
    scenes: '请求总量可控的回归压测、版本对比、CI 流水线中的快速性能校验。',
    metrics: '总请求数、成功率、响应时间分位、各接口维度统计。'
  },
  {
    mode: 'stepping',
    title: '梯度模式',
    summary: '分多个阶段逐步提升并发用户数，每阶段持续指定时间，观察各负载下的表现变化。',
    scenes: '探测系统性能拐点、评估限流/熔断阈值、容量规划与扩容决策参考。',
    metrics: '各阶段 QPS、响应时间变化趋势、错误率突增点。'
  },
  {
    mode: 'stream_burst',
    title: '流式阶段压测',
    summary: '每个虚拟用户仅发送 1 次流式请求（如 SSE 问答），按解析器采集各阶段耗时与成功判定。',
    scenes: '大模型问答、流式接口的首字时间/思考耗时/答案输出耗时评估；不适合测持续高 QPS。',
    metrics: '阶段计时（首字、意图完成、流式输出等）、整体耗时、逐路请求明细。'
  },
  {
    mode: 'journey_fixed',
    title: '链路固定',
    summary: '按业务阶段编排多步用例（支持串行/并行、变量传递、阶段同步），在持续时间内反复执行完整链路。',
    scenes: '登录 → 列表 → 详情等多步业务流程压测、端到端场景容量评估。',
    metrics: '链路成功率、链路耗时、各阶段执行次数与失败率。'
  },
  {
    mode: 'journey_loop',
    title: '链路循环',
    summary: '与链路固定相同的多阶段编排，但每个用户执行固定次数完整链路后结束。',
    scenes: '业务流程回归、可控样本量的链路边界测试、版本间链路耗时对比。',
    metrics: '链路成功率、链路耗时分位、分阶段统计。'
  }
]

const isModeGuideActive = (mode) => form.config.mode === mode

/** 内置解析器（API 不可用时兜底，保证下拉框始终有选项） */
const FALLBACK_PARSERS = [
  {
    parser_id: 'qa_sse_v1',
    display_name: '问答流式 v1',
    supports_rule_builder: false,
    phase_schema: [
      { key: 'think_answer', label: '问题理解首字(s)' },
      { key: 'intent_complete', label: '意图完成(s)' },
      { key: 'first_char', label: '首字时间(s)' },
      { key: 'total_time', label: '整体耗时(s)' },
      { key: 'thinking_duration', label: '思考耗时(s)' },
      { key: 'answer_streaming', label: '答案流式输出(s)' },
    ],
  },
  { parser_id: 'rule_based', display_name: '规则配置', phase_schema: [], supports_rule_builder: true },
  {
    parser_id: 'http_timing_only',
    display_name: '仅总耗时',
    supports_rule_builder: false,
    phase_schema: [{ key: 'total_time', label: '整体耗时(s)' }],
  },
]

const parserList = ref([...FALLBACK_PARSERS])

const defaultStreamProfile = () => ({
  transport: 'sse',
  parser_id: 'qa_sse_v1',
  parser_options: { rules: {} },
  success_rule: { type: 'phase_exists', phase: 'first_char' },
  timeout_seconds: 600
})

const isStreamBurst = computed(() => ['stream_burst', 'sse_burst'].includes(form.config.mode))
const isJourneyMode = computed(() => ['journey_fixed', 'journey_loop'].includes(form.config.mode))
const showStreamConfig = computed(() => isStreamBurst.value || enableStreamQA.value || (isJourneyMode.value && form.config.stream_profile))

const currentPhaseSchema = computed(() => {
  const p = parserList.value.find(x => x.parser_id === form.config.stream_profile?.parser_id)
  return p?.phase_schema || []
})

// CSV 参数化数据
const csvInfo = reactive({
  hasCSV: false,
  fileName: '',
  rowCount: 0,
  columns: [],
  preview: [],
  strategy: 'round_robin'
})

const defaultJourney = () => ({
  stop_on_step_fail: true,
  delay_between_journeys_ms: 0,
  phases: [{ name: '阶段1', execution: 'serial', sync_before: false, max_parallel: 6, steps: [] }]
})

const form = reactive({
  name: '',
  description: '',
  catalog_id: null,
  config: {
    mode: 'fixed',
    distribution_mode: 'random_weight',
    concurrent_users: 10,
    ramp_up_seconds: 5,
    duration_seconds: 60,
    loop_count: 100,
    steps: [{ users: 10, duration: 30 }],
    target_host: '',
    error_rate_threshold: 50,
    stream_profile: undefined,
    journey: defaultJourney()
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

const csvStrategyLabel = computed(() => {
  const map = {
    round_robin: '顺序轮询（跑完最后一题后从头再来）',
    random: '随机抽题',
    unique: '分区独占（每用户独立顺序循环）',
  }
  return map[csvInfo.strategy] || csvInfo.strategy
})

const filterCase = (query, item) => {
  return item.label.toLowerCase().includes(query.toLowerCase())
}

const getMethodType = (method) => {
  const map = { GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger', PATCH: 'info' }
  return map[method?.toUpperCase()] || ''
}

const ensureStreamProfileForMode = (mode) => {
  if (['stream_burst', 'sse_burst'].includes(mode)) {
    if (!form.config.stream_profile) {
      form.config.stream_profile = defaultStreamProfile()
    }
    enableStreamQA.value = true
    successPhaseKey.value = form.config.stream_profile.success_rule?.type || 'phase_exists'
  }
}

watch(() => form.config.mode, (mode) => {
  ensureStreamProfileForMode(mode)
}, { flush: 'sync' })

const onModeChange = (mode) => {
  ensureStreamProfileForMode(mode)
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
  } else if (mode === 'stream_burst') {
    form.config.duration_seconds = undefined
    form.config.loop_count = undefined
    form.config.steps = undefined
    if (!form.config.concurrent_users) form.config.concurrent_users = 10
  } else if (mode === 'journey_fixed') {
    form.config.loop_count = undefined
    form.config.steps = undefined
    if (!form.config.duration_seconds) form.config.duration_seconds = 60
    if (!form.config.journey) form.config.journey = defaultJourney()
  } else if (mode === 'journey_loop') {
    form.config.duration_seconds = undefined
    form.config.steps = undefined
    if (!form.config.loop_count) form.config.loop_count = 10
    if (!form.config.journey) form.config.journey = defaultJourney()
  }
}

const addJourneyPhase = () => {
  if (!form.config.journey) form.config.journey = defaultJourney()
  const n = (form.config.journey.phases?.length || 0) + 1
  form.config.journey.phases.push({
    name: `阶段${n}`, execution: 'serial', sync_before: false, max_parallel: 6, steps: []
  })
}

const removeJourneyPhase = (idx) => {
  if (form.config.journey?.phases?.length <= 1) {
    ElMessage.warning('至少保留一个阶段')
    return
  }
  form.config.journey.phases.splice(idx, 1)
}

const addJourneyStep = (phaseIdx) => {
  const phase = form.config.journey.phases[phaseIdx]
  phase.steps.push({ case_id: null, delay_ms: 0, use_stream: false, order: phase.steps.length })
}

const removeJourneyStep = (phaseIdx, stepIdx) => {
  form.config.journey.phases[phaseIdx].steps.splice(stepIdx, 1)
}

const buildJourneySceneItems = () => {
  const items = []
  const seen = new Set()
  for (const phase of form.config.journey?.phases || []) {
    for (const step of phase.steps || []) {
      if (step.case_id && !seen.has(step.case_id)) {
        seen.add(step.case_id)
        items.push({ case_id: step.case_id, weight: 1, delay_ms: step.delay_ms || 0 })
      }
    }
  }
  return items
}

const validateJourney = () => {
  const phases = form.config.journey?.phases || []
  if (!phases.length) {
    ElMessage.warning('请至少配置一个业务阶段')
    return false
  }
  let hasStep = false
  let hasSync = false
  for (const phase of phases) {
    if (phase.sync_before) hasSync = true
    for (const step of phase.steps || []) {
      if (step.case_id) hasStep = true
      else {
        ElMessage.warning('请为每个链路步骤选择用例')
        return false
      }
      if (step.use_stream && !form.config.stream_profile?.parser_id) {
        ElMessage.warning('流式步骤需先配置流式解析器（开启流式问答或流式配置）')
        return false
      }
    }
  }
  if (!hasStep) {
    ElMessage.warning('请至少添加一个链路步骤')
    return false
  }
  if (hasSync && (form.config.ramp_up_seconds || 0) > 0) {
    ElMessage.warning('阶段同步与 Ramp-up 不能同时使用，请将 Ramp-up 设为 0')
    return false
  }
  return true
}

const onStreamToggle = (enabled) => {
  if (enabled) {
    if (!form.config.stream_profile) form.config.stream_profile = defaultStreamProfile()
    successPhaseKey.value = form.config.stream_profile.success_rule?.type || 'phase_exists'
  }
}

const onParserChange = async (parserId) => {
  try {
    const res = await perfStreamParserApi.getPreset(parserId)
    const preset = res.data || res
    if (preset.default_options?.rules) {
      form.config.stream_profile.parser_options = { rules: preset.default_options.rules }
    }
    if (preset.default_success_rule) {
      form.config.stream_profile.success_rule = { ...preset.default_success_rule }
      successPhaseKey.value = preset.default_success_rule.type || 'phase_exists'
    }
  } catch (e) {
    console.error(e)
  }
}

const onSuccessRuleChange = (type) => {
  if (type === 'status_ok') {
    form.config.stream_profile.success_rule = { type: 'status_ok' }
  } else {
    form.config.stream_profile.success_rule = {
      type: 'phase_exists',
      phase: form.config.stream_profile.success_rule?.phase || 'first_char'
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

const loadParsers = async () => {
  try {
    const res = await perfStreamParserApi.getList()
    if (res?.status !== 200) return
    const list = res.data?.data
    if (Array.isArray(list) && list.length > 0) {
      parserList.value = list
    }
  } catch (err) {
    console.warn('[PerfSceneEdit] stream-parsers API unavailable, using built-in parsers', err)
  }
}

const loadCases = async () => {
  if (!proStore.projectInfo?.id) return
  casesLoading.value = true
  try {
    const res = await httpCaseApi.getList({ project_id: proStore.projectInfo.id, page: 1, size: 5000 })
    if (res.status === 200) {
      allCases.value = res.data?.data || []
    } else {
      allCases.value = []
      ElMessage.error(res.data?.detail || '加载用例列表失败')
    }
  } catch (err) {
    console.error(err)
    allCases.value = []
    ElMessage.error('加载用例列表失败')
  } finally {
    casesLoading.value = false
  }
}

const loadScene = async () => {
  if (!isEdit.value) return
  try {
    const res = await perfSceneApi.getDetail(sceneId.value)
    const data = res.data || res
    form.name = data.name || ''
    form.description = data.description || ''
    form.catalog_id = data.catalog_id ?? null
    if (data.config) {
      Object.assign(form.config, data.config)
      if (!form.config.mode) form.config.mode = 'fixed'
      if (form.config.mode === 'sse_burst') form.config.mode = 'stream_burst'
      const hasStream = form.config.stream_profile?.parser_id
      enableStreamQA.value = hasStream && form.config.mode !== 'stream_burst'
      if (form.config.mode === 'stream_burst' || hasStream) {
        if (!form.config.stream_profile) form.config.stream_profile = defaultStreamProfile()
        else form.config.stream_profile = { ...defaultStreamProfile(), ...form.config.stream_profile }
        successPhaseKey.value = form.config.stream_profile.success_rule?.type || 'phase_exists'
      } else {
        form.config.stream_profile = undefined
      }
      if (!form.config.steps) form.config.steps = [{ users: 10, duration: 30 }]
      if (!form.config.journey) form.config.journey = defaultJourney()
      else {
        form.config.journey = {
          ...defaultJourney(),
          ...form.config.journey,
          phases: (form.config.journey.phases || defaultJourney().phases).map((p, i) => ({
            name: p.name || `阶段${i + 1}`,
            execution: p.execution || 'serial',
            sync_before: !!p.sync_before,
            max_parallel: p.max_parallel || 6,
            steps: (p.steps || []).map((s, j) => ({
              case_id: s.case_id,
              delay_ms: s.delay_ms || 0,
              use_stream: !!s.use_stream,
              order: s.order ?? j
            }))
          }))
        }
      }
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

  if (isJourneyMode.value) {
    if (!validateJourney()) return
  } else if (selectedCaseIds.value.length === 0) {
    ElMessage.warning('请至少选择一个用例')
    return
  }

  saving.value = true
  try {
    const payload = {
      name: form.name,
      description: form.description,
      catalog_id: form.catalog_id,
      project_id: proStore.projectInfo.id,
      config: { ...form.config },
      scene_items: isJourneyMode.value
        ? buildJourneySceneItems()
        : selectedCases.value.map(c => ({
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
    } else if (payload.config.mode === 'stream_burst') {
      delete payload.config.duration_seconds
      delete payload.config.loop_count
      delete payload.config.steps
    } else if (payload.config.mode === 'journey_fixed') {
      delete payload.config.loop_count
      delete payload.config.steps
    } else if (payload.config.mode === 'journey_loop') {
      delete payload.config.duration_seconds
      delete payload.config.steps
    }

    if (payload.config.mode !== 'stream_burst' && !enableStreamQA.value) {
      delete payload.config.stream_profile
    } else if (!payload.config.stream_profile) {
      payload.config.stream_profile = defaultStreamProfile()
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
  if (!isEdit.value) {
    ElMessage.warning('请先保存场景后再上传 CSV')
    return
  }
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

onMounted(async () => {
  await Promise.all([loadParsers(), loadCases(), loadScene(), loadCSVPreview()])
})

watch(
  () => proStore.projectInfo?.id,
  (pid) => {
    if (pid) loadCases()
  },
)
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
.case-empty-tip {
  margin-top: 8px;
  line-height: 1.6;
}
.journey-phases {
  width: 100%;
}
.journey-phase-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  background: var(--el-fill-color-blank);
}
.journey-phase-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.mode-guide-collapse {
  margin: 0 0 16px 120px;
  max-width: 900px;
}
.mode-guide-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  color: #606266;
  height: 40px;
  line-height: 40px;
}
.mode-guide-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.mode-guide-item {
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
  line-height: 1.55;
  font-size: 13px;
  color: #606266;
}
.mode-guide-item.active {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}
.mode-guide-title {
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}
.mode-guide-desc {
  margin-bottom: 4px;
}
.mode-guide-scenes,
.mode-guide-metrics {
  color: #909399;
  font-size: 12px;
}
.mode-guide-item .label,
.mode-guide-extra .label {
  font-weight: 600;
  color: #606266;
}
.mode-guide-extra {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  background: #f5f7fa;
  font-size: 12px;
  color: #909399;
  line-height: 1.55;
}
</style>
