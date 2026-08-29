<template>
  <PageCard>
    <template #title>
      <div class="scene-title-row">
        <span style="font-size: 18px; font-weight: bold;">
          {{ isEdit ? '✏️ 编辑性能测试场景' : '➕ 新建性能测试场景' }}
        </span>
        <LinkFunctionalCaseButton
          v-if="isEdit"
          asset-type="perf_scene"
          :asset-id="Number(sceneId)"
        />
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
              <span class="label">流式怎么选：</span>
              <b>流式阶段压测</b> = 每人只发 <b>1 次</b> SSE，适合测首字/阶段耗时，不适合持续加压；
              要测持续吞吐请选 <b>固定 / 循环 / 梯度</b>，再打开下方 <b>流式问答</b>（HTTP 压测改为 SSE 采集阶段指标）。
            </div>
            <div class="mode-guide-extra">
              <span class="label">流式问答开关：</span>
              在固定/循环/梯度/链路模式下可启用，将请求切换为 SSE 流式采集（首字时间、阶段耗时等）；关闭则按普通 HTTP 统计 QPS 与响应时间。
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
              <el-tag v-if="isStreamBurst" size="small" type="warning">单次流式：每用户仅 1 次，测阶段耗时（非持续加压）</el-tag>
              <el-tag v-if="isJourneyMode" size="small" type="success">业务链路：每用户按阶段顺序/并行执行，支持变量传递与阶段同步</el-tag>
              <el-tag v-if="form.config.mode === 'fixed' && enableStreamQA" size="small" type="success">流式持续：固定并发 + 持续时间内反复 SSE</el-tag>
              <el-tag v-if="form.config.mode === 'loop' && enableStreamQA" size="small" type="success">流式循环：固定并发 × 循环次数，每次走 SSE</el-tag>
              <el-tag v-if="form.config.mode === 'stepping' && enableStreamQA" size="small" type="success">流式梯度：分阶段加并发，持续 SSE</el-tag>
            </div>
            <div v-if="isStreamBurst" class="field-tip" style="margin-top: 8px;">
              需要「持续加压 + 流式阶段指标」时：请改选 <b>固定/循环/梯度</b>，并打开下方「流式问答」，不要用流式阶段压测。
            </div>
            <div v-else-if="['fixed','loop','stepping'].includes(form.config.mode) && !enableStreamQA" class="field-tip" style="margin-top: 8px;">
              若用例是 SSE 问答且要看首字/阶段耗时：打开下方「流式问答」。仅测普通 HTTP 吞吐可保持关闭。
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
          <div class="field-tip">
            启用后按 SSE 解析器采集首字、整体耗时等阶段指标，并在持续/循环/梯度窗口内反复发问；
            关闭则按普通 HTTP 压测（QPS/RT/状态码），报告不再展示 SSE 阶段汇总。与「流式阶段压测」（每人仅 1 次）不同。
            关闭后请保存场景再执行，否则仍可能沿用旧的流式配置。
          </div>
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
            同时发起的流式虚拟用户数，每人只发送 1 次请求；高并发请先上线压测 Worker（BrickCoreRunner 或 BrickCorePerf）
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
        <el-form-item label="热身(Warmup)">
          <el-input-number
            v-model="form.config.warmup_seconds"
            :min="0"
            :max="600"
            controls-position="right"
            placeholder="跟随 Ramp-up"
          />
          <span class="unit">秒</span>
          <el-tooltip placement="top">
            <template #content>
              汇总 Avg/P95 等延迟指标时，剔除前 N 秒样本，降低冷启动噪声。<br />
              留空 = 跟随 Ramp-up；填 0 = 不剔除（全窗口延迟）。
            </template>
            <el-icon class="tip-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
          <div class="field-tip">建议 ≥ Ramp-up；总请求数 / QPS 仍按全窗口有效加压时长计算</div>
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
          <div class="field-tip">启用后，当错误率连续 3 秒超过该阈值时，压测将自动停止（运行中熔断，与下方「性能验收目标」无关）</div>
        </el-form-item>

        <!-- 性能验收目标 -->
        <el-divider content-position="left">性能验收目标</el-divider>
        <el-form-item label="验收目标">
          <div style="width:100%">
            <el-switch v-model="perfTargets.enabled" active-text="启用" inactive-text="关闭" />
            <div class="field-tip" style="margin-top:6px">
              用于报告判定本次是否达到业务绝对值 SLA。与「错误率熔断」「钉选基线退化」相互独立。目标值可留空；仅填写了数值且勾选启用的项参与判定。
            </div>
            <template v-if="perfTargets.enabled">
              <div style="display:flex;flex-wrap:wrap;gap:16px;margin:12px 0;">
                <div>
                  <span style="font-size:13px;margin-right:8px;">最小样本数</span>
                  <el-input-number v-model="perfTargets.min_total_requests" :min="0" :max="1000000" />
                </div>
                <div>
                  <span style="font-size:13px;margin-right:8px;">最小时长(秒)</span>
                  <el-input-number v-model="perfTargets.min_duration_seconds" :min="0" :max="86400" />
                </div>
              </div>
              <div class="field-tip">样本或时长不足时仍给出 pass/fail，但标记可信度偏低。</div>
              <el-table :data="perfTargetGlobalRows" size="small" border style="width:100%;max-width:920px;margin-top:8px;">
                <el-table-column label="启用" width="70" align="center">
                  <template #default="{ row }">
                    <el-checkbox v-model="row.enabled" />
                  </template>
                </el-table-column>
                <el-table-column label="指标" min-width="140">
                  <template #default="{ row }">{{ row.label }}</template>
                </el-table-column>
                <el-table-column label="条件" width="70" align="center">
                  <template #default="{ row }">{{ row.op }}</template>
                </el-table-column>
                <el-table-column label="目标值" width="140">
                  <template #default="{ row }">
                    <el-input-number
                      v-model="row.value"
                      :controls="false"
                      :precision="2"
                      :min="0"
                      placeholder="可空"
                      style="width:120px"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="单位" width="60" align="center">
                  <template #default="{ row }">{{ row.unit }}</template>
                </el-table-column>
                <el-table-column label="不满足时" width="130">
                  <template #default="{ row }">
                    <el-select v-model="row.severity" size="small" style="width:110px">
                      <el-option label="失败" value="fail" />
                      <el-option label="警告" value="warn" />
                    </el-select>
                  </template>
                </el-table-column>
              </el-table>
              <div class="field-tip" style="margin-top:8px">
                当前可选 {{ PERF_TARGET_GLOBAL_OPTIONS.length }} 项：QPS / 成功 QPS / 总请求数 / 平均与成功平均 RT / P90·P95·P99 与成功 P95 / 错误率。
                勾选并填写目标值后才参与判定；未勾选或留空不影响其它项。
              </div>
            </template>
          </div>
        </el-form-item>

        <!-- 链路固定模式 -->
        <template v-if="form.config.mode === 'journey_fixed'">
          <el-form-item label="持续时间" prop="config.duration_seconds">
            <el-input-number v-model="form.config.duration_seconds" :min="1" :max="86400" />
            <span class="unit">秒（最长 24 小时；每位用户在此时间内反复执行完整链路）</span>
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
            <el-input-number v-model="form.config.duration_seconds" :min="1" :max="86400" />
            <span class="unit">秒（最长 24 小时，适合长时间浸泡压测）</span>
            <el-tooltip placement="top" content="压测持续的总时长，期间保持目标并发数持续施压；最长 86400 秒（24 小时）">
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
          <el-alert
            type="info"
            :closable="false"
            show-icon
            style="margin: 0 0 12px 120px;"
            title="实际执行以「解析器 + 规则/成功判定」为准。上方「SSE 解析方案」只是快捷填入系统里已保存的配置快照，选完后仍可改解析器与规则。"
          />
          <el-form-item label="选用方案">
            <el-select
              v-model="selectedSseConfigId"
              clearable
              filterable
              placeholder="可选：从系统 SSE 解析配置一键填入"
              style="width: 360px"
              @change="onSseConfigSelect"
            >
              <el-option
                v-for="c in sseConfigOptions"
                :key="c.id"
                :label="formatSseConfigLabel(c)"
                :value="c.id"
              />
            </el-select>
            <div class="field-tip">
              方案在「系统设置 → SSE 解析配置」维护（可 AI 生成规则后保存）。选用 = 复制一份到本场景，不是运行时再去查库。
            </div>
          </el-form-item>
          <el-form-item label="解析器类型">
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
              本场景真正生效的解析方式。标准 KCF 用「问答流式 v1」；标准 SSE 字段用「规则配置」；
              行首是 datas/events 等非标准协议时用「自定义 SSE」并改前缀。
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
          <div v-if="streamUsesRuleBuilder" class="rules-panel">
            <StreamRuleBuilder
              v-model="form.config.stream_profile.parser_options.rules"
              :show-frame-prefixes="form.config.stream_profile.parser_id === 'custom_sse'"
            />
          </div>
          <el-form-item label="报告着重">
            <el-select
              v-model="form.config.stream_profile.report_highlight_phases"
              multiple
              clearable
              filterable
              collapse-tags
              collapse-tags-tooltip
              placeholder="可选：报告摘要中着重展示的指标"
              style="width: 420px"
            >
              <el-option
                v-for="s in currentPhaseSchema"
                :key="s.key"
                :label="s.label || s.key"
                :value="s.key"
              />
            </el-select>
            <div class="field-tip">
              默认报告展示全部阶段/派生指标卡片与对比图；勾选后这些指标在摘要区置顶加粗。留空则全部同等展示。
            </div>
          </el-form-item>
        </template>

        <!-- 业务链路配置 -->
        <template v-if="isJourneyMode">
          <el-divider content-position="left">业务链路</el-divider>
          <el-alert type="info" :closable="false" show-icon style="margin: 0 0 12px 120px;"
            title="并发 N = N 条链路同时执行（非 N×步骤数）。步骤间变量通过用例 extractors 传递；阶段 sync 在本机/单 Worker 内齐步走。" />
          <el-alert
            v-if="journeySourceStatus?.changed"
            type="warning"
            :closable="false"
            show-icon
            style="margin: 0 0 12px 120px;"
          >
            <template #title>{{ journeySourceStatus.message || '源套件已变更' }}</template>
            <el-button
              v-if="journeySourceStatus.suite_exists"
              type="warning"
              size="small"
              plain
              style="margin-top: 6px;"
              @click="reopenSuiteImportFromSource"
            >重新导入预览</el-button>
          </el-alert>
          <el-alert
            v-if="missingJourneyCases.length"
            type="error"
            :closable="false"
            show-icon
            style="margin: 0 0 12px 120px;"
            :title="`链路中有 ${missingJourneyCases.length} 个用例不可用（已删除或不在当前项目）：${missingJourneyCaseSummary}`"
          />
          <el-form-item label="失败策略">
            <el-switch v-model="form.config.journey.stop_on_step_fail" active-text="步骤失败中断链路" inactive-text="继续执行" />
          </el-form-item>
          <el-form-item label="链路间隔">
            <el-input-number v-model="form.config.journey.delay_between_journeys_ms" :min="0" :max="60000" />
            <span class="unit">ms（每条链路完成后的等待）</span>
          </el-form-item>
          <el-form-item label="业务阶段">
            <div class="journey-toolbar" style="margin-bottom: 10px;">
              <el-select
                v-model="journeyCaseTagFilter"
                clearable
                filterable
                allow-create
                default-first-option
                placeholder="按标签筛选用例"
                style="width: 180px; margin-right: 8px;"
              >
                <el-option label="perf" value="perf" />
                <el-option label="journey" value="journey" />
                <el-option label="login" value="login" />
              </el-select>
              <el-button type="primary" plain size="small" @click="openSuiteImport">从接口套件导入</el-button>
              <el-button type="success" plain size="small" @click="openSaveTemplate">保存为链路模板</el-button>
              <el-button type="warning" plain size="small" @click="openApplyTemplate">从模板应用</el-button>
            </div>
            <div v-if="journeyCaseTagFilter && journeyCaseOptions.length === 0" class="field-tip" style="margin-bottom: 8px;">
              无匹配标签「{{ journeyCaseTagFilter }}」的用例，请清空筛选或先在用例上打标签。
            </div>
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
                <el-table :data="phase.steps" size="small" border style="width: 100%; margin-top: 8px;" :row-class-name="journeyStepRowClass">
                  <el-table-column label="顺序" width="60" align="center">
                    <template #default="{ $index }">{{ $index + 1 }}</template>
                  </el-table-column>
                  <el-table-column label="用例" min-width="220">
                    <template #default="{ row }">
                      <div>
                        <el-select
                          v-model="row.case_id"
                          filterable
                          clearable
                          placeholder="选择用例"
                          style="width: 100%"
                          :class="{ 'is-missing-case': isMissingJourneyCase(row.case_id) }"
                        >
                          <el-option
                            v-for="c in journeyCaseOptionsForStep(row.case_id)"
                            :key="c.id"
                            :label="`${c.name} [${c.api?.method || c.api_method || ''}]`"
                            :value="c.id"
                          />
                        </el-select>
                        <div v-if="isMissingJourneyCase(row.case_id)" class="missing-case-hint">
                          用例 #{{ row.case_id }} 不存在或已删除，请重新选择
                        </div>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="间隔" min-width="240" align="center">
                    <template #header>
                      <span>间隔</span>
                      <el-tooltip placement="top">
                        <template #content>
                          固定：步骤完成后等待固定毫秒<br/>
                          随机：在区间内均匀抽样（类似 Locust between），更接近真实思考时间；尖刺可设 0
                        </template>
                        <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </template>
                    <template #default="{ row }">
                      <div class="delay-cell">
                        <el-select
                          v-model="row.delay_mode"
                          size="small"
                          style="width: 72px"
                          @change="onDelayModeChange(row)"
                        >
                          <el-option label="固定" value="fixed" />
                          <el-option label="随机" value="random" />
                        </el-select>
                        <template v-if="row.delay_mode === 'random'">
                          <el-input-number
                            v-model="row.delay_ms_min"
                            :min="0"
                            :max="60000"
                            size="small"
                            controls-position="right"
                            style="width: 86px"
                          />
                          <span class="delay-sep">~</span>
                          <el-input-number
                            v-model="row.delay_ms_max"
                            :min="0"
                            :max="60000"
                            size="small"
                            controls-position="right"
                            style="width: 86px"
                          />
                          <el-button link type="primary" size="small" @click="applyDelayPreset(row, 1000, 3000)">1~3s</el-button>
                        </template>
                        <el-input-number
                          v-else
                          v-model="row.delay_ms"
                          :min="0"
                          :max="60000"
                          size="small"
                          style="width: 100px"
                        />
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="流式" width="70" align="center">
                    <template #default="{ row }">
                      <el-checkbox v-model="row.use_stream" :disabled="!enableStreamQA && !form.config.stream_profile" />
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="100" align="center">
                    <template #default="{ row, $index }">
                      <el-button type="primary" size="small" link @click="debugJourneyStep(row, pIdx)">调试</el-button>
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

        <!-- 从套件导入链路 -->
        <el-dialog v-model="suiteImport.visible" title="从接口套件导入业务链路" width="640px" destroy-on-close>
          <el-form label-width="100px">
            <el-form-item label="接口套件" required>
              <el-select
                v-model="suiteImport.suiteId"
                filterable
                placeholder="选择套件"
                style="width: 100%"
                :loading="suiteImport.loadingSuites"
                @change="previewSuiteImport"
              >
                <el-option
                  v-for="s in suiteImport.suites"
                  :key="s.id"
                  :label="`${s.name}（${s.case_count ?? 0} 用例）`"
                  :value="s.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="布局">
              <el-radio-group v-model="suiteImport.layout" @change="previewSuiteImport">
                <el-radio label="single_phase">单阶段多步骤</el-radio>
                <el-radio label="per_case_phase">每用例一阶段</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-form>
          <el-table v-if="suiteImport.previewCases.length" :data="suiteImport.previewCases" size="small" border max-height="280">
            <el-table-column type="index" width="50" label="#" />
            <el-table-column prop="case_name" label="用例" min-width="180" />
            <el-table-column prop="case_id" label="用例ID" width="90" align="center" />
          </el-table>
          <div v-if="suiteImport.skipped.length" class="field-tip" style="margin-top: 8px; color: #e6a23c;">
            已跳过 {{ suiteImport.skipped.length }} 个无效用例
          </div>
          <template #footer>
            <el-button @click="suiteImport.visible = false">取消</el-button>
            <el-button type="primary" :loading="suiteImport.applying" :disabled="!suiteImport.journey" @click="applySuiteImport">导入到当前链路</el-button>
          </template>
        </el-dialog>

        <!-- 保存为链路模板 -->
        <el-dialog v-model="templateSave.visible" title="保存为链路模板" width="480px" destroy-on-close>
          <el-form label-width="80px">
            <el-form-item label="名称" required>
              <el-input v-model="templateSave.name" maxlength="100" placeholder="模板名称" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="templateSave.description" type="textarea" :rows="2" placeholder="可选" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="templateSave.visible = false">取消</el-button>
            <el-button type="primary" :loading="templateSave.saving" @click="submitSaveTemplate">保存</el-button>
          </template>
        </el-dialog>

        <!-- 从模板应用 -->
        <el-dialog v-model="templateApply.visible" title="从链路模板应用" width="560px" destroy-on-close>
          <el-table
            :data="templateApply.list"
            size="small"
            border
            highlight-current-row
            v-loading="templateApply.loading"
            @current-change="(row) => { templateApply.selected = row }"
          >
            <el-table-column prop="name" label="模板名称" min-width="160" />
            <el-table-column prop="create_by" label="创建人" width="100" />
            <el-table-column prop="update_time" label="更新时间" width="160" />
          </el-table>
          <template #footer>
            <el-button @click="templateApply.visible = false">取消</el-button>
            <el-button type="primary" :disabled="!templateApply.selected" :loading="templateApply.applying" @click="applyTemplate">应用到当前链路</el-button>
          </template>
        </el-dialog>

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
                <el-input-number v-model="row.cfg.weight" :min="1" :max="100" size="small" style="width: 90px" />
              </template>
            </el-table-column>
            <el-table-column min-width="240" align="center">
              <template #header>
                <span>间隔</span>
                <el-tooltip placement="top">
                  <template #content>
                    固定：每次请求后等待固定毫秒<br/>
                    随机：在区间内均匀抽样（类似 Locust between），更接近真实用户思考时间；尖刺压测可设 0
                  </template>
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <div class="delay-cell">
                  <el-select
                    v-model="row.cfg.delay_mode"
                    size="small"
                    style="width: 72px"
                    @change="onDelayModeChange(row.cfg)"
                  >
                    <el-option label="固定" value="fixed" />
                    <el-option label="随机" value="random" />
                  </el-select>
                  <template v-if="row.cfg.delay_mode === 'random'">
                    <el-input-number
                      v-model="row.cfg.delay_ms_min"
                      :min="0"
                      :max="60000"
                      size="small"
                      controls-position="right"
                      style="width: 86px"
                    />
                    <span class="delay-sep">~</span>
                    <el-input-number
                      v-model="row.cfg.delay_ms_max"
                      :min="0"
                      :max="60000"
                      size="small"
                      controls-position="right"
                      style="width: 86px"
                    />
                    <el-button link type="primary" size="small" @click="applyDelayPreset(row.cfg, 1000, 3000)">1~3s</el-button>
                  </template>
                  <el-input-number
                    v-else
                    v-model="row.cfg.delay_ms"
                    :min="0"
                    :max="60000"
                    size="small"
                    style="width: 100px"
                  />
                </div>
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
              title="请先保存场景，保存成功后再回来选择 CSV；下载模板可随时使用。"
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
                <div>　• 可点击「下载模板」获取样例文件后改内容</div>
                <div style="margin-top: 4px;"><b>Step 2 — 选择 CSV</b></div>
                <div>　• 编辑已保存的场景，选择文件后可预览；<b>须再点下方「保存」才会写入场景</b>（取消离开则丢弃）</div>
                <div style="margin-top: 4px;"><b>Step 3 — 在用例 Body 中引用</b></div>
                <div>　• 写法：<code v-pre style="background:#f5f7fa;padding:2px 6px;border-radius:4px;">${{csv.列名}}</code>（兼容旧写法 <code v-pre>{{csv.列名}}</code>）</div>
                <div>　• 对 CSV 列做 MD5 等工具：<code v-pre style="background:#f5f7fa;padding:2px 6px;border-radius:4px;">${{dt:md5|text=@csv.列名}}</code>（与环境变量同名时仍取 CSV）</div>
                <div>　• 问答 Body 示例：<code v-pre style="background:#f5f7fa;padding:2px 6px;border-radius:4px;">{"question":"${{csv.question}}"}</code></div>
                <div>　• 可用于 Body、Query、Header、URL 路径；须本场景已绑定 CSV</div>
                <div style="margin-top: 4px;"><b>Step 4 — 选择分配策略</b></div>
                <div>　• <b>顺序轮询</b>：所有请求按 CSV 行号依次取下一题，<b>最后一题用完后从第一题重新开始</b>（持续压测推荐）</div>
                <div>　• <b>随机</b>：每次请求随机抽一行问题，适合题库很大、不要求按序覆盖的场景</div>
                <div>　• <b>分区独占</b>：每个并发虚拟用户独立顺序取题并循环，互不抢同一行（多用户并行时更均匀）</div>
                <div style="margin-top: 4px; color: #409eff;">💡 固定/梯度 + 流式问答模式下同样生效；每次新请求都会替换 <code v-pre>${{csv.question}}</code> 后再发起 SSE。</div>
              </div>
            </el-alert>
            <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 12px;">
              <el-button :icon="Download" @click="downloadCSVTemplate">下载模板</el-button>
              <el-upload
                v-if="isEdit"
                accept=".csv"
                :show-file-list="false"
                :auto-upload="false"
                :on-change="handleCSVUpload"
              >
                <el-button type="primary" :icon="Upload">
                  {{ csvInfo.hasCSV ? '重新选择 CSV' : '选择 CSV 文件' }}
                </el-button>
              </el-upload>
              <span style="color: #909399; font-size: 13px;">支持 UTF-8 / GBK，最多 10000 行；变更需点下方保存</span>
            </div>
            <el-alert
              v-if="csvDirty"
              type="warning"
              :closable="false"
              show-icon
              style="margin-bottom: 12px;"
              title="CSV 尚未写入场景，请点击下方「保存」生效；取消离开将丢弃本次变更。"
            />
            <div v-if="csvInfo.hasCSV">
              <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                <el-tag size="small" :type="csvDirty ? 'warning' : 'success'">{{ csvInfo.fileName }}</el-tag>
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
import { Plus, Delete, QuestionFilled, Upload, Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import LinkFunctionalCaseButton from '@/views/TestManagement/components/LinkFunctionalCaseButton.vue'
import StreamRuleBuilder from '@/components/perf/StreamRuleBuilder.vue'
import { perfSceneApi, httpCaseApi, httpSuiteApi, perfJourneyTemplateApi } from '@/api'
import { perfSceneApi as perfSceneApiCSV, perfStreamParserApi } from '@/api/modules/perf'
import { streamParserConfigApi } from '@/api/modules/sys.js'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { defaultPerfTargets, normalizePerfTargetsLocal, ensureGlobalTargetItems, PERF_TARGET_GLOBAL_OPTIONS } from '@/views/Perf/perfTargets'

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
const perfTargets = reactive(defaultPerfTargets())
ensureGlobalTargetItems(perfTargets)
watch(
  () => [perfTargets.enabled, (perfTargets.items || []).map((i) => i && i.key).join(',')],
  () => {
    if (perfTargets.enabled) ensureGlobalTargetItems(perfTargets)
  },
)
const perfTargetGlobalRows = computed(() =>
  (perfTargets.items || []).filter((it) => it.scope === 'global')
)
const enableStreamQA = ref(false)
const casesLoading = ref(false)
const casesLoadedOk = ref(false)
const successPhaseKey = ref('phase_exists')
const modeGuideExpanded = ref([])
const appendCaseHandled = ref(false)
const journeyCaseTagFilter = ref('')
const journeySourceStatus = ref(null)

const caseIdMap = computed(() => {
  const map = new Map()
  for (const c of allCases.value) {
    map.set(c.id, c)
  }
  return map
})

const journeyCaseOptions = computed(() => {
  const tag = (journeyCaseTagFilter.value || '').trim()
  if (!tag) return allCases.value
  return allCases.value.filter(c => Array.isArray(c.tags) && c.tags.includes(tag))
})

const journeyCaseOptionsForStep = (selectedId) => {
  const options = [...journeyCaseOptions.value]
  if (selectedId && !options.some(c => c.id === selectedId)) {
    const selected = caseIdMap.value.get(selectedId)
    if (selected) options.unshift(selected)
  }
  return options
}

const isMissingJourneyCase = (caseId) => {
  if (caseId == null || caseId === '') return false
  // 用例列表未成功加载时不误判为缺失，避免拦截保存
  if (!casesLoadedOk.value || casesLoading.value) return false
  return !caseIdMap.value.has(caseId)
}

const missingJourneyCases = computed(() => {
  const seen = new Set()
  const missing = []
  for (const phase of form.config.journey?.phases || []) {
    for (const step of phase.steps || []) {
      if (!step.case_id || seen.has(step.case_id)) continue
      if (isMissingJourneyCase(step.case_id)) {
        seen.add(step.case_id)
        missing.push({ case_id: step.case_id, reason: '用例不存在或已删除，或不属于当前项目' })
      }
    }
  }
  return missing
})

const missingJourneyCaseSummary = computed(() =>
  missingJourneyCases.value.map(m => `#${m.case_id}`).join('、')
)

const journeyStepRowClass = ({ row }) => (isMissingJourneyCase(row?.case_id) ? 'journey-step-missing' : '')

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
    summary: '每个虚拟用户仅发送 1 次流式请求（如 SSE 问答），按解析器采集各阶段耗时与成功判定。不是持续加压模式。',
    scenes: '大模型问答首字/阶段耗时摸底；若要持续加压请改用固定/循环/梯度并打开「流式问答」。',
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
  { parser_id: 'custom_sse', display_name: '自定义 SSE', phase_schema: [], supports_rule_builder: true },
  {
    parser_id: 'http_timing_only',
    display_name: '仅总耗时',
    supports_rule_builder: false,
    phase_schema: [{ key: 'total_time', label: '整体耗时(s)' }],
  },
]

const parserList = ref([...FALLBACK_PARSERS])
const sseConfigOptions = ref([])
const selectedSseConfigId = ref(null)

const defaultStreamProfile = () => ({
  transport: 'sse',
  parser_id: 'qa_sse_v1',
  parser_options: { rules: {} },
  success_rule: { type: 'phase_exists', phase: 'first_char' },
  timeout_seconds: 600,
  sse_parser_config_id: undefined,
  report_highlight_phases: []
})

const isStreamBurst = computed(() => ['stream_burst', 'sse_burst'].includes(form.config.mode))
const isJourneyMode = computed(() => ['journey_fixed', 'journey_loop'].includes(form.config.mode))
const showStreamConfig = computed(() => isStreamBurst.value || enableStreamQA.value || (isJourneyMode.value && form.config.stream_profile))

const schemaFromRules = (rules) => {
  const schema = []
  for (const p of rules?.phases || []) {
    if (p?.key) schema.push({ key: p.key, label: p.label || p.key })
  }
  for (const d of rules?.derived || []) {
    if (d?.key) schema.push({ key: d.key, label: d.label || d.key })
  }
  schema.push({ key: 'total_time', label: '整体耗时(s)' })
  return schema
}

const streamUsesRuleBuilder = computed(() => {
  const pid = form.config.stream_profile?.parser_id
  return pid === 'rule_based' || pid === 'custom_sse'
})

const currentPhaseSchema = computed(() => {
  const profile = form.config.stream_profile
  if (streamUsesRuleBuilder.value) {
    return schemaFromRules(profile?.parser_options?.rules)
  }
  const p = parserList.value.find(x => x.parser_id === profile?.parser_id)
  return p?.phase_schema || []
})

const formatSseConfigLabel = (c) => {
  if (!c) return ''
  const type = c.parser_display_name || c.parser_id || ''
  return type ? `${c.name}（${type}）` : c.name
}
// CSV 参数化数据（选择/删除/改策略均为本地待定，点「保存」才写入）
const csvInfo = reactive({
  hasCSV: false,
  fileName: '',
  rowCount: 0,
  columns: [],
  preview: [],
  strategy: 'round_robin'
})
/** 服务端已有 CSV（用于判断删除是否需要落库） */
const csvServerHasData = ref(false)
const csvServerStrategy = ref('round_robin')
/** 待落库的文件；非 null 表示有新文件待上传 */
const csvPendingFile = ref(null)
/** 待落库删除 */
const csvPendingDelete = ref(false)

const csvDirty = computed(() => {
  if (csvPendingFile.value || csvPendingDelete.value) return true
  if (!csvInfo.hasCSV || !csvServerHasData.value) return false
  return csvInfo.strategy !== csvServerStrategy.value
})

const CSV_TEMPLATE_CONTENT = [
  'question',
  '什么是知识库？',
  '如何创建应用？',
  '压测场景如何配置并发？',
].join('\n') + '\n'

const downloadCSVTemplate = () => {
  const blob = new Blob(['\ufeff' + CSV_TEMPLATE_CONTENT], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'perf_csv_template.csv'
  a.click()
  URL.revokeObjectURL(url)
}

const resetCSVLocal = () => {
  csvInfo.hasCSV = false
  csvInfo.fileName = ''
  csvInfo.rowCount = 0
  csvInfo.columns = []
  csvInfo.preview = []
  csvInfo.strategy = 'round_robin'
  csvPendingFile.value = null
  csvPendingDelete.value = false
}

const applyCSVPreviewData = (data, { fromServer = false } = {}) => {
  csvInfo.hasCSV = true
  csvInfo.fileName = data.file_name || ''
  csvInfo.rowCount = data.row_count || 0
  csvInfo.columns = data.columns || []
  csvInfo.preview = data.preview || []
  csvInfo.strategy = data.strategy || csvInfo.strategy || 'round_robin'
  if (fromServer) {
    csvServerHasData.value = true
    csvServerStrategy.value = csvInfo.strategy
    csvPendingFile.value = null
    csvPendingDelete.value = false
  }
}

const flushCSVChanges = async (sid) => {
  if (!sid) return
  if (csvPendingDelete.value) {
    await perfSceneApiCSV.deleteCSV(sid)
    csvServerHasData.value = false
    csvServerStrategy.value = 'round_robin'
    csvPendingDelete.value = false
    csvPendingFile.value = null
    return
  }
  if (csvPendingFile.value) {
    const formData = new FormData()
    formData.append('file', csvPendingFile.value)
    await perfSceneApiCSV.uploadCSV(sid, formData, {
      dryRun: false,
      strategy: csvInfo.strategy,
    })
    csvServerHasData.value = true
    csvServerStrategy.value = csvInfo.strategy
    csvPendingFile.value = null
    return
  }
  if (
    csvInfo.hasCSV
    && csvServerHasData.value
    && csvInfo.strategy !== csvServerStrategy.value
  ) {
    await perfSceneApiCSV.updateCSVConfig(sid, { strategy: csvInfo.strategy, enabled: true })
    csvServerStrategy.value = csvInfo.strategy
  }
}

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
    warmup_seconds: null,
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

const normalizeDelayFields = (src = {}) => {
  const mode = src.delay_mode === 'random' ? 'random' : 'fixed'
  return {
    delay_mode: mode,
    delay_ms: Number(src.delay_ms) || 0,
    delay_ms_min: Number(src.delay_ms_min) || 0,
    delay_ms_max: Number(src.delay_ms_max) || 0,
  }
}

const onDelayModeChange = (row) => {
  if (row.delay_mode === 'random' && !(row.delay_ms_min > 0 || row.delay_ms_max > 0)) {
    row.delay_ms_min = 1000
    row.delay_ms_max = 3000
  }
}

const applyDelayPreset = (row, minMs, maxMs) => {
  row.delay_mode = 'random'
  row.delay_ms_min = minMs
  row.delay_ms_max = maxMs
}

const serializeDelayFields = (row) => normalizeDelayFields(row)

const ensureSceneItem = (caseId) => {
  let item = form.scene_items.find(i => i.case_id === caseId)
  if (!item) {
    item = { case_id: caseId, weight: 1, ...normalizeDelayFields() }
    form.scene_items.push(item)
  } else {
    Object.assign(item, {
      weight: item.weight || 1,
      ...normalizeDelayFields(item),
    })
  }
  return item
}

watch(selectedCaseIds, (ids) => {
  const idSet = new Set(ids)
  form.scene_items = form.scene_items.filter(i => idSet.has(i.case_id))
  for (const id of ids) {
    ensureSceneItem(id)
  }
})

const selectedCases = computed(() => {
  return selectedCaseIds.value.map(id => {
    const caseInfo = allCases.value.find(c => c.id === id)
    const item = form.scene_items.find(i => i.case_id === id) || {
      case_id: id,
      weight: 1,
      ...normalizeDelayFields(),
    }
    return {
      case_id: id,
      case_name: caseInfo?.name || '未知',
      api_method: caseInfo?.api?.method || caseInfo?.api_method || '',
      cfg: item,
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
    selectedSseConfigId.value = form.config.stream_profile.sse_parser_config_id || null
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
  phase.steps.push({ case_id: null, ...normalizeDelayFields(), use_stream: false, order: phase.steps.length })
}

const removeJourneyStep = (phaseIdx, stepIdx) => {
  form.config.journey.phases[phaseIdx].steps.splice(stepIdx, 1)
}

const applyJourneyConfig = (journey) => {
  if (!form.config.journey) form.config.journey = defaultJourney()
  form.config.journey = {
    stop_on_step_fail: journey.stop_on_step_fail !== false,
    delay_between_journeys_ms: journey.delay_between_journeys_ms || 0,
    phases: (journey.phases || []).map((p, i) => ({
      name: p.name || `阶段${i + 1}`,
      execution: p.execution || 'serial',
      sync_before: !!p.sync_before,
      max_parallel: p.max_parallel || 6,
      steps: (p.steps || []).map((s, j) => ({
        case_id: s.case_id,
        ...normalizeDelayFields(s),
        use_stream: !!s.use_stream,
        order: s.order ?? j
      }))
    }))
  }
  if (!['journey_fixed', 'journey_loop'].includes(form.config.mode)) {
    form.config.mode = 'journey_fixed'
    onModeChange('journey_fixed')
  }
}

const suiteImport = reactive({
  visible: false,
  suiteId: null,
  layout: 'single_phase',
  suites: [],
  loadingSuites: false,
  previewCases: [],
  skipped: [],
  journey: null,
  applying: false
})

const openSuiteImport = async () => {
  suiteImport.visible = true
  suiteImport.suiteId = null
  suiteImport.journey = null
  suiteImport.previewCases = []
  suiteImport.skipped = []
  suiteImport.layout = 'single_phase'
  suiteImport.loadingSuites = true
  try {
    const res = await httpSuiteApi.getList({
      project_id: proStore.projectInfo.id,
      page: 1,
      size: 500
    })
    suiteImport.suites = res.data?.data || res.data || []
  } catch (e) {
    console.error(e)
    ElMessage.error('加载套件列表失败')
  } finally {
    suiteImport.loadingSuites = false
  }
}

const previewSuiteImport = async () => {
  if (!suiteImport.suiteId) {
    suiteImport.journey = null
    suiteImport.previewCases = []
    return
  }
  try {
    const res = await perfSceneApi.journeyFromSuite({
      suite_id: suiteImport.suiteId,
      project_id: proStore.projectInfo.id,
      layout: suiteImport.layout
    })
    const data = res.data || res
    suiteImport.journey = data.journey
    suiteImport.previewCases = data.cases || []
    suiteImport.skipped = data.skipped || []
  } catch (e) {
    console.error(e)
    suiteImport.journey = null
    suiteImport.previewCases = []
    ElMessage.error(e?.response?.data?.detail || '预览失败')
  }
}

const applySuiteImport = async () => {
  if (!suiteImport.journey) return
  const hasSteps = (form.config.journey?.phases || []).some(p => (p.steps || []).some(s => s.case_id))
  if (hasSteps) {
    try {
      await ElMessageBox.confirm('将覆盖当前业务链路配置，是否继续？', '确认导入', { type: 'warning' })
    } catch {
      return
    }
  }
  suiteImport.applying = true
  try {
    applyJourneyConfig(suiteImport.journey)
    const caseIds = (suiteImport.previewCases || []).map(c => c.case_id).filter(Boolean)
    const suiteMeta = (suiteImport.suites || []).find(s => s.id === suiteImport.suiteId)
    form.config.journey_source = {
      suite_id: suiteImport.suiteId,
      suite_name: suiteMeta?.name || '',
      layout: suiteImport.layout,
      case_ids: caseIds,
      imported_at: new Date().toISOString()
    }
    journeySourceStatus.value = {
      suite_id: suiteImport.suiteId,
      suite_exists: true,
      changed: false,
      stored_case_ids: caseIds,
      current_case_ids: caseIds,
      message: null
    }
    await loadCases()
    suiteImport.visible = false
    ElMessage.success('已导入套件链路，请检查后保存场景')
  } finally {
    suiteImport.applying = false
  }
}

const reopenSuiteImportFromSource = async () => {
  const src = journeySourceStatus.value
  await openSuiteImport()
  if (src?.suite_id) {
    suiteImport.suiteId = src.suite_id
    if (src.layout) suiteImport.layout = src.layout
    await previewSuiteImport()
  }
}

const templateSave = reactive({
  visible: false,
  name: '',
  description: '',
  saving: false
})

const openSaveTemplate = () => {
  if (!validateJourney()) return
  templateSave.name = form.name ? `${form.name}-链路模板` : '业务链路模板'
  templateSave.description = ''
  templateSave.visible = true
}

const submitSaveTemplate = async () => {
  if (!templateSave.name.trim()) {
    ElMessage.warning('请填写模板名称')
    return
  }
  templateSave.saving = true
  try {
    await perfJourneyTemplateApi.create({
      project_id: proStore.projectInfo.id,
      name: templateSave.name.trim(),
      description: templateSave.description || null,
      journey: form.config.journey,
      source_scene_id: isEdit.value ? Number(sceneId.value) : null
    })
    ElMessage.success('链路模板已保存')
    templateSave.visible = false
  } catch (e) {
    console.error(e)
    ElMessage.error(e?.response?.data?.detail || '保存模板失败')
  } finally {
    templateSave.saving = false
  }
}

const templateApply = reactive({
  visible: false,
  list: [],
  loading: false,
  selected: null,
  applying: false
})

const openApplyTemplate = async () => {
  templateApply.visible = true
  templateApply.selected = null
  templateApply.loading = true
  try {
    const res = await perfJourneyTemplateApi.getList({ project_id: proStore.projectInfo.id })
    templateApply.list = res.data?.data || []
  } catch (e) {
    console.error(e)
    ElMessage.error('加载模板失败')
  } finally {
    templateApply.loading = false
  }
}

const applyTemplate = async () => {
  if (!templateApply.selected) return
  const hasSteps = (form.config.journey?.phases || []).some(p => (p.steps || []).some(s => s.case_id))
  if (hasSteps) {
    try {
      await ElMessageBox.confirm('将覆盖当前业务链路配置，是否继续？', '确认应用模板', { type: 'warning' })
    } catch {
      return
    }
  }
  templateApply.applying = true
  try {
    const res = await perfJourneyTemplateApi.getDetail(templateApply.selected.id)
    const data = res.data || res
    applyJourneyConfig(data.journey || {})
    await loadCases()
    templateApply.visible = false
    ElMessage.success('已应用链路模板，请检查后保存场景')
  } catch (e) {
    console.error(e)
    ElMessage.error(e?.response?.data?.detail || '应用模板失败')
  } finally {
    templateApply.applying = false
  }
}

const debugJourneyStep = (row, phaseIdx) => {
  if (!row?.case_id) {
    ElMessage.warning('请先选择用例')
    return
  }
  const caseInfo = allCases.value.find(c => c.id === row.case_id)
  const apiId = caseInfo?.api_id || caseInfo?.api?.id
  if (!apiId) {
    ElMessage.warning('该用例未关联接口，无法打开调试')
    return
  }
  const query = {
    debug_api_id: String(apiId),
    from_perf_scene: isEdit.value ? String(sceneId.value) : 'new',
    phase_index: String(phaseIdx)
  }
  router.push({ path: '/api-module', query })
}

const consumeAppendCaseQuery = async () => {
  const appendId = route.query.append_case_id
  if (!appendId || appendCaseHandled.value) return
  const caseId = Number(appendId)
  if (!caseId) return
  appendCaseHandled.value = true
  const phaseIdx = Math.max(0, Number(route.query.phase_index) || 0)
  if (!form.config.journey) form.config.journey = defaultJourney()
  if (!['journey_fixed', 'journey_loop'].includes(form.config.mode)) {
    form.config.mode = 'journey_fixed'
    onModeChange('journey_fixed')
  }
  await loadCases()
  const phases = form.config.journey.phases || []
  while (phases.length <= phaseIdx) addJourneyPhase()
  const phase = form.config.journey.phases[phaseIdx]
  phase.steps.push({
    case_id: caseId,
    ...normalizeDelayFields(),
    use_stream: false,
    order: phase.steps.length
  })
  ElMessage.success(`已将用例 #${caseId} 追加到阶段「${phase.name || phaseIdx + 1}」`)
  const nextQuery = { ...route.query }
  delete nextQuery.append_case_id
  delete nextQuery.phase_index
  router.replace({ path: route.path, query: nextQuery, params: route.params })
}

const buildJourneySceneItems = () => {
  const items = []
  const seen = new Set()
  for (const phase of form.config.journey?.phases || []) {
    for (const step of phase.steps || []) {
      if (step.case_id && !seen.has(step.case_id)) {
        seen.add(step.case_id)
        items.push({
          case_id: step.case_id,
          weight: 1,
          ...serializeDelayFields(step),
        })
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
  const missingIds = []
  for (const phase of phases) {
    if (phase.sync_before) hasSync = true
    for (const step of phase.steps || []) {
      if (step.case_id) hasStep = true
      else {
        ElMessage.warning('请为每个链路步骤选择用例')
        return false
      }
      if (isMissingJourneyCase(step.case_id)) {
        missingIds.push(step.case_id)
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
  if (missingIds.length) {
    const uniq = [...new Set(missingIds)]
    ElMessage.error(`链路中存在不可用用例：${uniq.map(id => `#${id}`).join('、')}，请重新选择后再保存`)
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
    selectedSseConfigId.value = form.config.stream_profile.sse_parser_config_id || null
  } else {
    // 立刻清掉，避免界面已关但仍带着 stream_profile 去跑 SSE 解析
    form.config.stream_profile = undefined
    selectedSseConfigId.value = null
    successPhaseKey.value = 'phase_exists'
    // 链路步骤上的「流式」勾选一并清掉，避免保存后无 profile 却仍标记 use_stream
    for (const phase of form.config.journey?.phases || []) {
      for (const step of phase.steps || []) {
        if (step && step.use_stream) step.use_stream = false
      }
    }
    ElMessage.info('已关闭流式问答：将按普通 HTTP 统计（QPS/RT），不再采集 SSE 阶段。请保存场景后再执行。')
  }
}

const onParserChange = async (parserId) => {
  if (form.config.stream_profile) {
    form.config.stream_profile.sse_parser_config_id = undefined
  }
  selectedSseConfigId.value = null
  try {
    const res = await perfStreamParserApi.getPreset(parserId)
    const preset = res.data || res
    if (preset.default_options?.rules) {
      form.config.stream_profile.parser_options = { rules: preset.default_options.rules }
    } else {
      form.config.stream_profile.parser_options = { rules: {} }
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

const loadSseConfigs = async () => {
  try {
    const res = await streamParserConfigApi.getList({ enabled_only: true })
    const list = res.data?.data || res.data || []
    sseConfigOptions.value = Array.isArray(list) ? list : []
  } catch (err) {
    console.warn('[PerfSceneEdit] stream-parser-configs unavailable', err)
    sseConfigOptions.value = []
  }
}

const onSseConfigSelect = async (configId) => {
  if (!configId) {
    if (form.config.stream_profile) {
      form.config.stream_profile.sse_parser_config_id = undefined
    }
    return
  }
  try {
    const res = await streamParserConfigApi.getDetail(configId)
    const detail = res.data?.data || res.data || {}
    if (!detail.parser_id) {
      ElMessage.error('解析配置无效')
      selectedSseConfigId.value = form.config.stream_profile?.sse_parser_config_id || null
      return
    }
    if (!form.config.stream_profile) {
      form.config.stream_profile = defaultStreamProfile()
    }
    const timeout = form.config.stream_profile.timeout_seconds || 600
    form.config.stream_profile.transport = 'sse'
    form.config.stream_profile.parser_id = detail.parser_id
    form.config.stream_profile.parser_options = detail.parser_options?.rules
      ? { rules: JSON.parse(JSON.stringify(detail.parser_options.rules)) }
      : (detail.parser_options ? JSON.parse(JSON.stringify(detail.parser_options)) : { rules: {} })
    form.config.stream_profile.success_rule = detail.success_rule?.type
      ? { ...detail.success_rule }
      : { type: 'phase_exists', phase: 'first_char' }
    form.config.stream_profile.timeout_seconds = timeout
    form.config.stream_profile.sse_parser_config_id = detail.id
    selectedSseConfigId.value = detail.id
    successPhaseKey.value = form.config.stream_profile.success_rule?.type || 'phase_exists'
    ElMessage.success(`已应用「${detail.name}」`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载解析配置失败')
    selectedSseConfigId.value = form.config.stream_profile?.sse_parser_config_id || null
  }
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
  casesLoadedOk.value = false
  try {
    const res = await httpCaseApi.getList({ project_id: proStore.projectInfo.id, page: 1, size: 5000 })
    if (res.status === 200) {
      allCases.value = res.data?.data || []
      casesLoadedOk.value = true
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
    journeySourceStatus.value = data.journey_source_status || null
    if (data.config) {
      Object.assign(form.config, data.config)
      if (!('warmup_seconds' in data.config) || data.config.warmup_seconds === undefined) {
        form.config.warmup_seconds = null
      }
      if (!form.config.mode) form.config.mode = 'fixed'
      if (form.config.mode === 'sse_burst') form.config.mode = 'stream_burst'
      const hasStream = form.config.stream_profile?.parser_id
      enableStreamQA.value = hasStream && form.config.mode !== 'stream_burst'
      if (form.config.mode === 'stream_burst' || hasStream) {
        if (!form.config.stream_profile) form.config.stream_profile = defaultStreamProfile()
        else form.config.stream_profile = { ...defaultStreamProfile(), ...form.config.stream_profile }
        if (!Array.isArray(form.config.stream_profile.report_highlight_phases)) {
          form.config.stream_profile.report_highlight_phases = []
        }
        successPhaseKey.value = form.config.stream_profile.success_rule?.type || 'phase_exists'
        selectedSseConfigId.value = form.config.stream_profile.sse_parser_config_id || null
      } else {
        form.config.stream_profile = undefined
        selectedSseConfigId.value = null
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
              ...normalizeDelayFields(s),
              use_stream: !!s.use_stream,
              order: s.order ?? j
            }))
          }))
        }
      }
      enableErrorThreshold.value = !!(data.config.error_rate_threshold && data.config.error_rate_threshold > 0)
      const nextTargets = normalizePerfTargetsLocal(data.config.perf_targets)
      perfTargets.enabled = nextTargets.enabled
      perfTargets.profile = nextTargets.profile
      perfTargets.mode = nextTargets.mode
      perfTargets.min_total_requests = nextTargets.min_total_requests
      perfTargets.min_duration_seconds = nextTargets.min_duration_seconds
      perfTargets.items = nextTargets.items
      ensureGlobalTargetItems(perfTargets)
    }
    if (data.scene_items) {
      form.scene_items = data.scene_items.map(item => ({
        case_id: item.case_id,
        weight: item.weight || 1,
        ...normalizeDelayFields(item),
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
        : selectedCaseIds.value.map(id => {
          const item = ensureSceneItem(id)
          return {
            case_id: id,
            weight: item.weight || 1,
            ...serializeDelayFields(item),
          }
        })
    }

    // 错误率阈值：未启用时设为 0
    if (!enableErrorThreshold.value) {
      payload.config.error_rate_threshold = 0
    }
    payload.config.perf_targets = normalizePerfTargetsLocal(perfTargets)
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
      try {
        await flushCSVChanges(sceneId.value)
      } catch (csvErr) {
        console.error(csvErr)
        ElMessage.warning('场景已保存，但 CSV 写入失败，请重新选择文件后再保存')
        return
      }
      ElMessage.success('更新成功')
    } else {
      await perfSceneApi.create(payload)
      ElMessage.success('创建成功')
    }
    router.push('/perf-scenes')
  } catch (err) {
    console.error(err)
    const detail = err?.response?.data?.detail
    const msg = typeof detail === 'string'
      ? detail
      : (Array.isArray(detail) ? detail.map(d => d.msg || d.message || JSON.stringify(d)).join('；') : null)
    ElMessage.error(msg || (isEdit.value ? '更新失败' : '创建失败'))
  } finally {
    saving.value = false
  }
}

const handleCancel = () => {
  router.push('/perf-scenes')
}

// 选择 CSV：仅 dry_run 解析预览，不落库
const handleCSVUpload = async (file) => {
  if (!isEdit.value) {
    ElMessage.warning('请先保存场景后再选择 CSV')
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
    const res = await perfSceneApiCSV.uploadCSV(sceneId.value, formData, { dryRun: true })
    const data = res.data || res
    const keepStrategy = csvInfo.hasCSV ? csvInfo.strategy : (data.strategy || 'round_robin')
    applyCSVPreviewData({ ...data, strategy: keepStrategy })
    csvPendingFile.value = raw
    csvPendingDelete.value = false
    ElMessage.success('已解析预览，请点击下方「保存」写入场景')
  } catch (err) {
    console.error(err)
    const detail = err?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : 'CSV 解析失败')
  }
}

// 删除：仅本地标记，保存时落库
const handleCSVDelete = async () => {
  try {
    await ElMessageBox.confirm(
      csvServerHasData.value
        ? '确定删除 CSV？需再点下方「保存」才会从场景中移除。'
        : '确定清除已选择的 CSV？',
      '删除 CSV',
      { type: 'warning' }
    )
  } catch {
    return
  }
  const hadServer = csvServerHasData.value
  resetCSVLocal()
  if (hadServer) csvPendingDelete.value = true
  ElMessage.info(hadServer ? '已标记删除，请点击下方「保存」生效' : '已清除所选 CSV')
}

// 策略变更：仅本地，保存时写入
const handleCSVStrategyChange = () => {
  if (!csvInfo.hasCSV) return
  if (csvDirty.value) {
    ElMessage.info('策略已修改，请点击下方「保存」生效')
  }
}

// 加载 CSV 预览
const loadCSVPreview = async () => {
  if (!isEdit.value || !sceneId.value) return
  try {
    const res = await perfSceneApiCSV.previewCSV(sceneId.value)
    const data = res.data || res
    if (data.row_count > 0) {
      applyCSVPreviewData(data, { fromServer: true })
    } else {
      resetCSVLocal()
      csvServerHasData.value = false
      csvServerStrategy.value = 'round_robin'
    }
  } catch (err) {
    // 忽略错误，可能没有 CSV
  }
}

onMounted(async () => {
  await Promise.all([loadParsers(), loadSseConfigs(), loadCases(), loadScene(), loadCSVPreview()])
  await consumeAppendCaseQuery()
})

watch(
  () => proStore.projectInfo?.id,
  (pid) => {
    if (pid) loadCases()
  },
)
</script>

<style scoped>
.scene-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

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
.rules-panel {
  margin: 8px 0 16px;
  max-width: 960px;
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
.delay-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  flex-wrap: wrap;
}
.delay-sep {
  color: #909399;
  font-size: 12px;
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
.missing-case-hint {
  margin-top: 4px;
  font-size: 12px;
  color: #f56c6c;
}
:deep(.is-missing-case .el-select__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}
:deep(.el-table .journey-step-missing) {
  --el-table-tr-bg-color: #fef0f0;
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
