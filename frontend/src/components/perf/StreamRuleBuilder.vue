<template>
  <div class="stream-rule-builder">
    <section v-if="showFramePrefixes" class="rule-section">
      <div class="rule-section-title">帧行前缀（自定义协议）</div>
      <div class="field-tip" style="margin-bottom: 10px">
        按接口真实行首填写。例如其它组用 <code>datas:</code> / <code>events:</code> 时在此改前缀；
        JSON 里的字段名（如 types、agents）仍在下方阶段「匹配条件 / 添加条件」里按真实 key 配置。
      </div>
      <div class="field-grid cols-3">
        <div class="field-cell">
          <label class="field-label">data 前缀</label>
          <el-input
            v-model="localRules.data_prefix"
            placeholder="data: 或 datas:"
            @change="onDataPrefixChange"
          />
        </div>
        <div class="field-cell">
          <label class="field-label">event 前缀</label>
          <el-input
            v-model="localRules.event_prefix"
            placeholder="event: 或 events:"
            @change="emitChange"
          />
        </div>
        <div class="field-cell">
          <label class="field-label">id 前缀</label>
          <el-input
            v-model="localRules.id_prefix"
            placeholder="id:"
            @change="emitChange"
          />
        </div>
      </div>
    </section>

    <section class="rule-section">
      <div class="rule-section-title">数据预处理（可选）</div>
      <div class="field-tip" style="margin-bottom: 10px">
        在匹配阶段之前把 SSE JSON「整形」成可匹配视图。公司改输出规范时只改这里的步骤与下方条件即可，无需改代码。
        常用：<code>unwrap_json_text</code>（解包嵌套 JSON 字符串）、<code>json_patch</code>（累积 p/o/v 及仅 v 续写）。
      </div>
      <div class="field-check-row" style="margin-bottom: 10px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center">
        <el-dropdown trigger="click" @command="applyExampleTemplate">
          <el-button size="small" plain>套用匿名示例模板</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="t in exampleTemplates"
                :key="t.id"
                :command="t.id"
              >
                {{ t.name }}
              </el-dropdown-item>
              <el-dropdown-item v-if="!exampleTemplates.length" disabled>加载中或暂无模板</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="field-tip" style="margin: 0">示例可完全改写，不绑定任何厂商。</span>
      </div>
      <div v-for="(step, sIdx) in localRules.preprocess" :key="'pp-' + sIdx" class="rule-block compact">
        <div class="rule-block-header">
          <span class="rule-block-title">步骤 {{ sIdx + 1 }}</span>
          <el-button type="danger" size="small" text :icon="Delete" @click="removePreprocess(sIdx)" />
        </div>
        <div class="field-grid cols-2">
          <div class="field-cell">
            <label class="field-label">类型</label>
            <el-select v-model="step.op" style="width: 100%" @change="emitChange">
              <el-option label="解包嵌套 JSON 字符串" value="unwrap_json_text" />
              <el-option label="JSON Patch 累积" value="json_patch" />
            </el-select>
          </div>
        </div>
        <div v-if="step.op === 'unwrap_json_text'" class="field-grid cols-2" style="margin-top: 8px">
          <div class="field-cell">
            <label class="field-label">JSONPath（字符串位置）</label>
            <el-input v-model="step.path" placeholder="如 $.data[0].value" @change="emitChange" />
          </div>
          <div class="field-cell">
            <label class="field-label">条件 path（可选）</label>
            <el-input v-model="step.when_path" placeholder="如 $.data[0].type" @change="emitChange" />
          </div>
          <div class="field-cell">
            <label class="field-label">条件等于（可选）</label>
            <el-input v-model="step.when_eq" placeholder="如 JSON_TEXT" @change="emitChange" />
          </div>
        </div>
        <p v-else class="field-tip" style="margin-top: 8px">
          将本帧 data JSON 按 p/o/v（APPEND/SET/BATCH）应用到累积文档；仅含 v 时续写上一 path。
          整形后可用 fragment_type / response_status / delta 非空 等条件匹配。
        </p>
      </div>
      <el-button type="primary" size="small" :icon="Plus" @click="addPreprocess">添加预处理步骤</el-button>
    </section>

    <section class="rule-section">
      <div class="rule-section-title">阶段规则</div>
      <div class="field-tip" style="margin-bottom: 10px">
        默认按 SSE <b>帧</b>解析（空行分隔的 data/id/event 合成一包）。流结束优先认
        <code>event:done</code>（规则里的 done_events），勿把 <code>data:{}</code> 填进 done_markers。
      </div>
      <div v-for="(phase, idx) in localRules.phases" :key="'p-' + idx" class="rule-block">
        <div class="rule-block-header">
          <span class="rule-block-title">阶段 {{ idx + 1 }}</span>
          <el-button
            type="danger"
            size="small"
            text
            :icon="Delete"
            :disabled="localRules.phases.length <= 1"
            @click="removePhase(idx)"
          />
        </div>
        <div class="field-grid cols-2">
          <div class="field-cell">
            <label class="field-label">标识 key</label>
            <el-input v-model="phase.key" placeholder="如 first_char" @change="emitChange" />
          </div>
          <div class="field-cell">
            <label class="field-label">展示名</label>
            <el-input v-model="phase.label" placeholder="首字时间(s)" @change="emitChange" />
          </div>
        </div>
        <div class="field-grid cols-2" style="margin-top: 12px">
          <div class="field-cell">
            <label class="field-label">触发时机</label>
            <el-select v-model="phase.trigger" style="width: 100%" @change="emitChange">
              <el-option label="首次命中" value="first" />
              <el-option label="末次命中" value="last" />
            </el-select>
          </div>
        </div>
        <div class="field-group">
          <div class="field-group-title">
            匹配条件
            <el-tooltip placement="top" :show-after="200">
              <template #content>
                <div>
                  按「SSE 帧」匹配：data 行 JSON 顶层字段 + <code>sse_event</code>（来自 event: 行）+
                  <code>sse_id</code>（来自 id: 行）。自定义 JSON 字段用「添加条件」。
                  行首须是标准 <code>data:</code> / <code>event:</code> / <code>id:</code>（不是 datas/events）。
                </div>
              </template>
              <el-icon class="tip-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
          <div class="field-tip">
            常用字段可直接填；标准 SSE 的 <code>event:</code> 行填到 <code>sse_event</code>（如 message / done），
            <code>id:</code> 行对应 <code>sse_id</code>。JSON 里若是 types/agents 等非标准字段名，用「添加条件」按真实字段名写。
            须同时填字段名和期望值后才会写入规则；未填完的行不会消失。
          </div>
          <div class="field-grid cols-4">
            <div class="field-cell">
              <label class="field-label">type</label>
              <el-input v-model="phase.match.type" placeholder="可选" @change="emitChange" />
            </div>
            <div class="field-cell">
              <label class="field-label">agent</label>
              <el-input v-model="phase.match.agent" placeholder="可选" @change="emitChange" />
            </div>
            <div class="field-cell">
              <label class="field-label">action</label>
              <el-input v-model="phase.match.action" placeholder="可选" @change="emitChange" />
            </div>
            <div class="field-cell">
              <label class="field-label">status</label>
              <el-input v-model="phase.match.status" placeholder="可选" @change="emitChange" />
            </div>
          </div>
          <div class="field-grid cols-2" style="margin-top: 8px">
            <div class="field-cell">
              <label class="field-label">
                sse_event
                <el-tooltip placement="top" :show-after="200">
                  <template #content>
                    来自 SSE 行 <code>event:xxx</code>（不是 JSON 里的字段）。例如 message、done。
                  </template>
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </label>
              <el-input v-model="phase.match.sse_event" placeholder="如 message / done" @change="emitChange" />
            </div>
            <div class="field-cell">
              <label class="field-label">fragment_type</label>
              <el-input v-model="phase.match.fragment_type" placeholder="如 THINK / RESPONSE" @change="emitChange" />
            </div>
            <div class="field-cell">
              <label class="field-label">response_status</label>
              <el-input v-model="phase.match.response_status" placeholder="如 FINISHED" @change="emitChange" />
            </div>
          </div>
          <div class="field-group" style="margin-top: 10px">
            <div class="field-group-title">高级匹配（JSONPath）</div>
            <div class="field-tip">开启预处理后，path 相对整形后的文档（_doc）。text_grew 适合「累计全文变长」协议。</div>
            <div class="field-grid cols-2">
              <div class="field-cell">
                <label class="field-label">path_eq · path</label>
                <el-input
                  :model-value="phase.match.path_eq?.path || ''"
                  placeholder="$.data.messageList[0].status"
                  @update:model-value="(v) => setPathSpec(phase, 'path_eq', 'path', v)"
                />
              </div>
              <div class="field-cell">
                <label class="field-label">path_eq · value</label>
                <el-input
                  :model-value="phase.match.path_eq?.value || ''"
                  placeholder="FINISHED"
                  @update:model-value="(v) => setPathSpec(phase, 'path_eq', 'value', v)"
                />
              </div>
              <div class="field-cell">
                <label class="field-label">path_nonempty · path</label>
                <el-input
                  :model-value="typeof phase.match.path_nonempty === 'string' ? phase.match.path_nonempty : (phase.match.path_nonempty?.path || '')"
                  placeholder="$.data....content"
                  @update:model-value="(v) => setPathNonempty(phase, v)"
                />
              </div>
              <div class="field-cell">
                <label class="field-label">text_grew · path</label>
                <el-input
                  :model-value="phase.match.text_grew?.path || ''"
                  placeholder="累计文本 JSONPath"
                  @update:model-value="(v) => setPathSpec(phase, 'text_grew', 'path', v)"
                />
              </div>
              <div class="field-cell">
                <label class="field-label">text_grew · min_chars</label>
                <el-input
                  :model-value="phase.match.text_grew?.min_chars != null ? String(phase.match.text_grew.min_chars) : ''"
                  placeholder="1"
                  @update:model-value="(v) => setPathSpec(phase, 'text_grew', 'min_chars', v)"
                />
              </div>
            </div>
          </div>
          <div
            v-for="(row, rIdx) in phase.matchExtra"
            :key="'mx-' + idx + '-' + rIdx"
            class="match-extra-row"
          >
            <el-input
              v-model="row.field"
              placeholder="字段名，如 event"
              style="width: 40%"
              @change="emitChange"
            />
            <el-input
              v-model="row.value"
              placeholder="期望值"
              style="flex: 1"
              @change="emitChange"
            />
            <el-button type="danger" text :icon="Delete" @click="removeMatchExtra(phase, rIdx)" />
          </div>
          <div class="field-check-row" style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
            <el-checkbox v-model="phase.match.delta_nonempty" @change="emitChange">delta 非空</el-checkbox>
            <el-button size="small" plain :icon="Plus" @click="addMatchExtra(phase)">添加条件</el-button>
          </div>
        </div>
      </div>
      <el-button type="primary" size="small" :icon="Plus" @click="addPhase">添加阶段</el-button>
    </section>

    <section class="rule-section">
      <div class="rule-section-title">派生指标</div>
      <div class="field-tip">
        用两个时间点相减得到间隔耗时。公式固定为「结束 − 开始」。
        <b>最终完成时间</b>请选内置的 <code>total_time</code>（整体耗时：流读完 / 收到 DONE 的时刻，无需在阶段规则里配置）。
        <b>回答开始</b>选阶段规则里的 key，例如正式回答首字 <code>first_char</code> → 回答耗时 =
        <code>total_time - first_char</code>。
      </div>
      <div class="time-points-bar">
        <span class="time-points-label">可用时间点</span>
        <el-tag
          v-for="opt in timePointOptions"
          :key="opt.key"
          size="small"
          :type="opt.key === 'total_time' ? 'warning' : 'info'"
          effect="plain"
        >
          {{ opt.short }}
        </el-tag>
      </div>
      <div v-for="(d, idx) in localRules.derived" :key="'d-' + idx" class="rule-block compact">
        <div class="rule-block-header">
          <span class="rule-block-title">派生 {{ idx + 1 }}</span>
          <el-button type="danger" size="small" text :icon="Delete" @click="removeDerived(idx)" />
        </div>
        <div class="field-grid cols-2">
          <div class="field-cell">
            <label class="field-label">key</label>
            <el-input v-model="d.key" placeholder="如 answer_streaming" @change="emitChange" />
          </div>
          <div class="field-cell">
            <label class="field-label">展示名</label>
            <el-input v-model="d.label" placeholder="回答耗时(s)" @change="emitChange" />
          </div>
        </div>
        <div class="field-group">
          <div class="field-group-title">计算：结束时间 − 开始时间</div>
          <div class="expr-row">
            <div class="field-cell">
              <label class="field-label">结束（较大）</label>
              <el-select
                :model-value="exprLeft(d)"
                filterable
                allow-create
                default-first-option
                placeholder="如 total_time"
                style="width: 100%"
                @change="(v) => setExprPart(d, 'left', v)"
              >
                <el-option
                  v-for="opt in timePointOptions"
                  :key="'L-' + opt.key"
                  :label="opt.label"
                  :value="opt.key"
                />
              </el-select>
            </div>
            <span class="expr-minus">−</span>
            <div class="field-cell">
              <label class="field-label">开始（较小）</label>
              <el-select
                :model-value="exprRight(d)"
                filterable
                allow-create
                default-first-option
                placeholder="如 first_char"
                style="width: 100%"
                @change="(v) => setExprPart(d, 'right', v)"
              >
                <el-option
                  v-for="opt in timePointOptions"
                  :key="'R-' + opt.key"
                  :label="opt.label"
                  :value="opt.key"
                />
              </el-select>
            </div>
          </div>
          <div class="expr-preview">表达式：<code>{{ d.expr || '（未设置）' }}</code></div>
        </div>
      </div>
      <div class="rule-actions">
        <el-button type="primary" size="small" plain :icon="Plus" @click="addDerived">添加派生指标</el-button>
        <el-button size="small" plain @click="addAnswerDuration">一键添加「回答耗时」</el-button>
      </div>
    </section>

    <section class="rule-section">
      <div class="rule-section-title">
        附加字段提取
        <el-tooltip placement="top" :show-after="200" popper-class="stream-rule-tip-pop">
          <template #content>
            <div>
              <p>写入报告「流式请求阶段明细」的扩展列（不是耗时阶段）。</p>
              <p><b>JSON 字段</b>：从任意 SSE JSON 顶层取值，如 id → thread_id。</p>
              <p><b>EOF 引用</b>：匹配结束包，从 references[] 拼文档名。</p>
              <p><b>拼正式回答</b>：拼接指定 agent 的 output_text 作为答案预览。</p>
            </div>
          </template>
          <el-icon class="tip-icon"><QuestionFilled /></el-icon>
        </el-tooltip>
      </div>
      <div class="field-tip">
        扩展列写入压测报告明细；具体用法悬停「来源」或各类型标题旁的问号查看。
      </div>
      <div v-for="(ex, idx) in localRules.extras_extract" :key="'e-' + idx" class="rule-block">
        <div class="rule-block-header">
          <span class="rule-block-title">提取 {{ idx + 1 }}</span>
          <el-button type="danger" size="small" text :icon="Delete" @click="removeExtra(idx)" />
        </div>
        <div class="field-grid cols-3">
          <div class="field-cell">
            <label class="field-label">key</label>
            <el-input v-model="ex.key" placeholder="如 thread_id" @change="emitChange" />
          </div>
          <div class="field-cell">
            <label class="field-label">展示名</label>
            <el-input v-model="ex.label" placeholder="报告列名" @change="emitChange" />
          </div>
          <div class="field-cell">
            <label class="field-label">
              来源
              <el-tooltip placement="top" :show-after="200" popper-class="stream-rule-tip-pop">
                <template #content>
                  <div class="tip-pop">
                    <p><b>JSON 字段</b>：任意一条 <code>data:&#123;...&#125;</code> 里取顶层字段，首次非空即记下。<br>例：字段名 <code>id</code> → 报告列 thread_id。</p>
                    <p><b>EOF 引用</b>：匹配结束包（常 type=eof），从包内 <code>references[]</code> 取出文档名并拼接。<br>需填包 type / agent，以及引用项字段（如 doc_name）。</p>
                    <p><b>拼正式回答</b>：收集指定 agent 且 type=output_text 的 delta，拼成答案预览。<br>会自动生成 answer_length；预览上限控制报告里截断长度。</p>
                  </div>
                </template>
                <el-icon class="tip-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </label>
            <el-select v-model="ex.from" style="width: 100%" @change="onExtraFromChange(ex)">
              <el-option label="JSON 字段" value="json_field" />
              <el-option label="EOF 引用" value="eof_references" />
              <el-option label="拼正式回答" value="answer_collect" />
              <el-option label="JSONPath 取值" value="json_path" />
              <el-option label="按条件收集增量文本" value="text_collect_path" />
            </el-select>
          </div>
        </div>
        <div v-if="ex.from === 'json_field'" class="field-group">
          <div class="field-group-title">
            从 SSE JSON 取字段
            <el-tooltip placement="top" :show-after="200" popper-class="stream-rule-tip-pop">
              <template #content>
                <div class="tip-pop">
                  <p>扫描每条 SSE JSON，读取你填的「JSON 字段名」对应的顶层值。</p>
                  <p>首次出现非空值时写入报告列（key / 展示名）。</p>
                  <p>示例：SSE 里有 <code>"id":"abc"</code>，字段名填 <code>id</code>，key 填 <code>thread_id</code>。</p>
                </div>
              </template>
              <el-icon class="tip-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
          <div class="field-grid cols-2">
            <div class="field-cell">
              <label class="field-label">JSON 字段名</label>
              <el-input v-model="ex.field" placeholder="如 id" @change="emitChange" />
            </div>
          </div>
        </div>
        <div v-else-if="ex.from === 'eof_references'" class="field-group">
          <div class="field-group-title">
            从结束包 references 取引用
            <el-tooltip placement="top" :show-after="200" popper-class="stream-rule-tip-pop">
              <template #content>
                <div class="tip-pop">
                  <p>只处理匹配的结束包：包内 type / agent 需与下面填写一致（常见 type=<code>eof</code>）。</p>
                  <p>读取该包的 <code>references</code> 数组，取出每项里的「引用项字段」（如 <code>doc_name</code>），用分号拼成一列。</p>
                  <p>用于报告展示本轮回答引用了哪些文档。</p>
                </div>
              </template>
              <el-icon class="tip-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
          <div class="field-grid cols-2">
            <div class="field-cell">
              <label class="field-label">包 type</label>
              <el-input v-model="ex.match.type" placeholder="eof" @change="emitChange" />
            </div>
            <div class="field-cell">
              <label class="field-label">包 agent</label>
              <el-input v-model="ex.match.agent" placeholder="conventional_summary" @change="emitChange" />
            </div>
            <div class="field-cell">
              <label class="field-label">引用项字段</label>
              <el-input v-model="ex.field" placeholder="如 doc_name" @change="emitChange" />
            </div>
          </div>
        </div>
        <div v-else-if="ex.from === 'answer_collect'" class="field-group">
          <div class="field-group-title">
            拼接正式回答文本
            <el-tooltip placement="top" :show-after="200" popper-class="stream-rule-tip-pop">
              <template #content>
                <div class="tip-pop">
                  <p>收集 <code>type=output_text</code> 且 agent 等于下方填写值的所有 delta，按顺序拼成完整回答。</p>
                  <p>报告里展示「答案预览」（按预览上限截断）；完整字数会自动写入 <code>answer_length</code>，无需另配。</p>
                  <p>agent 需与你们协议里正式回答通道一致，常见为 <code>conventional_summary</code>。</p>
                </div>
              </template>
              <el-icon class="tip-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
          <div class="field-grid cols-2">
            <div class="field-cell">
              <label class="field-label">agent</label>
              <el-input v-model="ex.agent" placeholder="conventional_summary" @change="emitChange" />
            </div>
            <div class="field-cell">
              <label class="field-label">预览上限（字符）</label>
              <el-input-number v-model="ex.max_len" :min="50" :max="16000" controls-position="right" style="width: 100%" @change="emitChange" />
            </div>
          </div>
        </div>
        <div v-else-if="ex.from === 'json_path'" class="field-group">
          <div class="field-group-title">按 JSONPath 取值</div>
          <div class="field-grid cols-2">
            <div class="field-cell">
              <label class="field-label">path</label>
              <el-input v-model="ex.path" placeholder="$.data.messageList[0].contentList[1].content" @change="emitChange" />
            </div>
            <div class="field-cell">
              <label class="field-label">触发</label>
              <el-select v-model="ex.trigger" style="width: 100%" @change="emitChange">
                <el-option label="首次" value="first" />
                <el-option label="末次（覆盖）" value="last" />
              </el-select>
            </div>
            <div class="field-cell">
              <label class="field-label">预览上限（字符）</label>
              <el-input-number v-model="ex.max_len" :min="50" :max="16000" controls-position="right" style="width: 100%" @change="emitChange" />
            </div>
          </div>
        </div>
        <div v-else-if="ex.from === 'text_collect_path'" class="field-group">
          <div class="field-group-title">按条件收集增量文本</div>
          <div class="field-tip">命中 match 时收集本帧 delta/text_delta；也可填 path 用累计全文增长量。</div>
          <div class="field-grid cols-2">
            <div class="field-cell">
              <label class="field-label">match.fragment_type</label>
              <el-input v-model="ex.match.fragment_type" placeholder="RESPONSE" @change="emitChange" />
            </div>
            <div class="field-cell">
              <label class="field-label">累计文本 path（可选）</label>
              <el-input v-model="ex.path" placeholder="可空，仅用 delta" @change="emitChange" />
            </div>
            <div class="field-cell">
              <label class="field-label">预览上限（字符）</label>
              <el-input-number v-model="ex.max_len" :min="50" :max="16000" controls-position="right" style="width: 100%" @change="emitChange" />
            </div>
          </div>
        </div>
      </div>
      <div class="rule-actions">
        <el-button type="primary" size="small" plain :icon="Plus" @click="addExtra">添加附加字段</el-button>
        <el-button size="small" plain @click="fillDefaultExtras">填入默认提取项</el-button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, QuestionFilled } from '@element-plus/icons-vue'
import { perfStreamParserApi } from '@/api/modules/perf.js'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  /** 自定义 SSE：展示可改 data/event/id 行前缀 */
  showFramePrefixes: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const exampleTemplates = ref([])

const defaultExtras = () => ([
  { key: 'thread_id', label: 'thread_id', from: 'json_field', field: 'id', trigger: 'first', match: {} },
  {
    key: 'reference_files',
    label: '引用文件',
    from: 'eof_references',
    field: 'doc_name',
    trigger: 'first',
    match: { type: 'eof', agent: 'conventional_summary' }
  },
  {
    key: 'answer_preview',
    label: '答案预览',
    from: 'answer_collect',
    agent: 'conventional_summary',
    max_len: 500,
    trigger: 'first',
    match: {}
  }
])

const defaultRules = () => ({
  line_prefix: 'data:',
  data_prefix: 'data:',
  event_prefix: 'event:',
  id_prefix: 'id:',
  done_markers: ['[DONE]', 'data:[DONE]'],
  frame_mode: true,
  done_events: ['done'],
  preprocess: [],
  phases: [
    { key: 'intent_complete', label: '意图完成(s)', match: { type: 'think', agent: 'think', action: 'intent', status: 'success' }, trigger: 'first' },
    { key: 'first_char', label: '首字时间(s)', match: { type: 'output_text', agent: 'conventional_summary', delta_nonempty: true }, trigger: 'first' }
  ],
  derived: [
    { key: 'thinking_duration', label: '思考耗时(s)', expr: 'first_char - intent_complete' },
    { key: 'answer_streaming', label: '回答耗时(s)', expr: 'total_time - first_char' }
  ],
  extras_extract: defaultExtras()
})

const localRules = reactive(defaultRules())

const timePointOptions = computed(() => {
  const opts = []
  const seen = new Set()
  for (const p of localRules.phases || []) {
    const key = (p?.key || '').trim()
    if (!key || seen.has(key)) continue
    seen.add(key)
    const name = (p.label || key).trim()
    opts.push({
      key,
      short: `${name} · ${key}`,
      label: `${name}（阶段 · ${key}）`
    })
  }
  opts.push({
    key: 'total_time',
    short: '整体耗时 · total_time（内置）',
    label: '整体耗时 / 流结束（total_time · 内置，无需配置阶段）'
  })
  return opts
})

const splitExpr = (expr) => {
  const raw = (expr || '').trim()
  const sep = ' - '
  const idx = raw.indexOf(sep)
  if (idx < 0) return { left: '', right: '' }
  return {
    left: raw.slice(0, idx).trim(),
    right: raw.slice(idx + sep.length).trim()
  }
}

const exprLeft = (d) => splitExpr(d?.expr).left
const exprRight = (d) => splitExpr(d?.expr).right

const setExprPart = (d, part, value) => {
  const cur = splitExpr(d.expr)
  if (part === 'left') cur.left = (value || '').trim()
  else cur.right = (value || '').trim()
  if (cur.left && cur.right) d.expr = `${cur.left} - ${cur.right}`
  else if (cur.left) d.expr = `${cur.left} - `
  else if (cur.right) d.expr = ` - ${cur.right}`
  else d.expr = ''
  emitChange()
}

const normalizeExtra = (item) => {
  const ex = item && typeof item === 'object' ? { ...item } : {}
  if (!ex.match || typeof ex.match !== 'object') ex.match = {}
  if (!ex.trigger) ex.trigger = 'first'
  if (!ex.from) ex.from = 'json_field'
  if (ex.max_len == null && ex.from === 'answer_collect') ex.max_len = 500
  return ex
}

const STRUCT_MATCH_KEYS = ['path_eq', 'path_nonempty', 'text_grew']
const COMMON_MATCH_KEYS = [
  'type', 'agent', 'action', 'status', 'sse_event', 'delta_nonempty',
  'fragment_type', 'response_status',
  ...STRUCT_MATCH_KEYS,
]

const normalizePhase = (item) => {
  const p = item && typeof item === 'object' ? JSON.parse(JSON.stringify(item)) : {}
  if (!p.match || typeof p.match !== 'object') p.match = {}
  if (!p.trigger) p.trigger = 'first'
  const matchExtra = []
  for (const [k, v] of Object.entries(p.match)) {
    if (COMMON_MATCH_KEYS.includes(k)) continue
    if (v != null && typeof v === 'object') continue
    matchExtra.push({ field: k, value: v == null ? '' : String(v) })
  }
  p.matchExtra = matchExtra
  return p
}

const buildPhaseMatchForEmit = (phase) => {
  const match = {}
  for (const k of ['type', 'agent', 'action', 'status', 'sse_event', 'fragment_type', 'response_status']) {
    const v = phase.match?.[k]
    if (v !== '' && v != null) match[k] = v
  }
  if (phase.match?.delta_nonempty) match.delta_nonempty = true
  for (const sk of STRUCT_MATCH_KEYS) {
    const spec = phase.match?.[sk]
    if (!spec) continue
    if (sk === 'path_nonempty') {
      const path = typeof spec === 'string' ? spec.trim() : String(spec?.path || '').trim()
      if (path) match.path_nonempty = { path }
      continue
    }
    if (typeof spec === 'object') {
      const path = String(spec.path || '').trim()
      if (!path) continue
      if (sk === 'path_eq') {
        match.path_eq = { path, value: spec.value == null ? '' : String(spec.value) }
      } else if (sk === 'text_grew') {
        let minChars = 1
        try { minChars = Math.max(1, parseInt(spec.min_chars, 10) || 1) } catch { minChars = 1 }
        match.text_grew = { path, min_chars: minChars }
      }
    }
  }
  for (const row of phase.matchExtra || []) {
    const field = String(row.field || '').trim()
    if (!field || COMMON_MATCH_KEYS.includes(field)) continue
    if (row.value === '' || row.value == null) continue
    match[field] = row.value
  }
  return match
}

const setPathSpec = (phase, key, field, value) => {
  if (!phase.match || typeof phase.match !== 'object') phase.match = {}
  const cur = (phase.match[key] && typeof phase.match[key] === 'object')
    ? { ...phase.match[key] }
    : {}
  if (field === 'min_chars') {
    cur[field] = value === '' || value == null ? 1 : Number(value) || 1
  } else {
    cur[field] = value
  }
  const path = String(cur.path || '').trim()
  if (!path && field === 'path' && !String(value || '').trim()) {
    delete phase.match[key]
  } else {
    phase.match[key] = cur
  }
  emitChange()
}

const setPathNonempty = (phase, value) => {
  if (!phase.match || typeof phase.match !== 'object') phase.match = {}
  const path = String(value || '').trim()
  if (!path) delete phase.match.path_nonempty
  else phase.match.path_nonempty = { path }
  emitChange()
}

const addPreprocess = () => {
  if (!Array.isArray(localRules.preprocess)) localRules.preprocess = []
  localRules.preprocess.push({ op: 'unwrap_json_text', path: '', when_path: '', when_eq: '' })
  emitChange()
}

const removePreprocess = (idx) => {
  if (!Array.isArray(localRules.preprocess)) return
  localRules.preprocess.splice(idx, 1)
  emitChange()
}

const loadExampleTemplates = async () => {
  try {
    const res = await perfStreamParserApi.getExampleTemplates()
    const data = res?.data?.data ?? res?.data ?? res
    exampleTemplates.value = Array.isArray(data) ? data : []
  } catch {
    exampleTemplates.value = []
  }
}

const applyExampleTemplate = async (id) => {
  const t = exampleTemplates.value.find((x) => x.id === id)
  if (!t?.rules) return
  try {
    await ElMessageBox.confirm(
      `将用「${t.name}」覆盖当前规则（可再改），是否继续？`,
      '套用示例模板',
      { type: 'warning' }
    )
  } catch {
    return
  }
  syncFromProps(t.rules)
  emitChange()
  ElMessage.success('已套用示例，请按协议调整后保存')
}

onMounted(loadExampleTemplates)

/** 未写完的「添加条件」行（缺字段名或期望值），emit 时不会进 match，需在 props 回写时保留，否则输入框会消失。 */
const snapshotDraftMatchExtras = () =>
  (localRules.phases || []).map((phase) =>
    (phase.matchExtra || [])
      .filter((row) => {
        const field = String(row.field || '').trim()
        return !field || row.value === '' || row.value == null
      })
      .map((row) => ({
        field: row.field == null ? '' : String(row.field),
        value: row.value == null ? '' : String(row.value),
      }))
  )

const mergeDraftMatchExtras = (draftsByPhase) => {
  ;(localRules.phases || []).forEach((phase, idx) => {
    if (!Array.isArray(phase.matchExtra)) phase.matchExtra = []
    const known = new Set(
      phase.matchExtra.map((r) => String(r.field || '').trim()).filter(Boolean)
    )
    let hasBlank = phase.matchExtra.some((r) => !String(r.field || '').trim())
    for (const d of draftsByPhase[idx] || []) {
      const f = String(d.field || '').trim()
      if (f) {
        if (known.has(f)) continue
        phase.matchExtra.push({ field: d.field || '', value: d.value == null ? '' : String(d.value) })
        known.add(f)
        continue
      }
      if (hasBlank) continue
      phase.matchExtra.push({ field: '', value: d.value == null ? '' : String(d.value) })
      hasBlank = true
    }
  })
}

const syncFromProps = (val) => {
  const base = defaultRules()
  const src = val || {}
  const extrasSrc = Array.isArray(src.extras_extract) ? src.extras_extract : null
  const draftExtras = snapshotDraftMatchExtras()
  Object.assign(localRules, {
    line_prefix: src.line_prefix || base.line_prefix,
    data_prefix: src.data_prefix || base.data_prefix,
    event_prefix: src.event_prefix || base.event_prefix,
    id_prefix: src.id_prefix || base.id_prefix,
    done_markers: src.done_markers || base.done_markers,
    frame_mode: src.frame_mode !== undefined ? src.frame_mode : base.frame_mode,
    done_events: Array.isArray(src.done_events) ? src.done_events : base.done_events,
    preprocess: Array.isArray(src.preprocess)
      ? JSON.parse(JSON.stringify(src.preprocess))
      : JSON.parse(JSON.stringify(base.preprocess || [])),
    phases: (src.phases && src.phases.length)
      ? src.phases.map((x) => normalizePhase(x))
      : base.phases.map((x) => normalizePhase(x)),
    derived: (src.derived && src.derived.length) ? JSON.parse(JSON.stringify(src.derived)) : base.derived,
    // 显式空数组保留空；未传才用默认提取项
    extras_extract: extrasSrc !== null
      ? extrasSrc.map((x) => normalizeExtra(JSON.parse(JSON.stringify(x))))
      : JSON.parse(JSON.stringify(base.extras_extract))
  })
  if (!Array.isArray(localRules.preprocess)) localRules.preprocess = []
  mergeDraftMatchExtras(draftExtras)
}

watch(() => props.modelValue, (v) => syncFromProps(v), { immediate: true, deep: true })

const onDataPrefixChange = () => {
  const pfx = String(localRules.data_prefix || '').trim()
  if (pfx) localRules.line_prefix = pfx
  emitChange()
}

const emitChange = () => {
  const out = JSON.parse(JSON.stringify(localRules))
  for (const phase of out.phases || []) {
    phase.match = buildPhaseMatchForEmit(phase)
    delete phase.matchExtra
    if (!phase.trigger) phase.trigger = 'first'
  }
  emit('update:modelValue', out)
}

const addPhase = () => {
  localRules.phases.push(normalizePhase({
    key: '',
    label: '',
    match: { type: '', agent: '', action: '', status: '', sse_event: '' },
    trigger: 'first'
  }))
  emitChange()
}
const removePhase = (idx) => {
  localRules.phases.splice(idx, 1)
  emitChange()
}
const addMatchExtra = (phase) => {
  if (!Array.isArray(phase.matchExtra)) phase.matchExtra = []
  phase.matchExtra.push({ field: '', value: '' })
}
const removeMatchExtra = (phase, rIdx) => {
  phase.matchExtra?.splice(rIdx, 1)
  emitChange()
}
const addDerived = () => {
  const startKey = (localRules.phases || []).find((p) => p.key)?.key || 'first_char'
  localRules.derived.push({
    key: '',
    label: '',
    expr: `total_time - ${startKey}`
  })
  emitChange()
}
const addAnswerDuration = () => {
  const startKey = (localRules.phases || []).find((p) => /first_char|answer|首字|回答/.test(`${p.key} ${p.label}`))?.key
    || (localRules.phases || []).slice(-1)[0]?.key
    || 'first_char'
  const exists = (localRules.derived || []).some((d) => d.key === 'answer_streaming' || d.expr === `total_time - ${startKey}`)
  if (exists) {
    const hit = localRules.derived.find((d) => d.key === 'answer_streaming')
    if (hit) {
      hit.label = hit.label || '回答耗时(s)'
      hit.expr = `total_time - ${startKey}`
    }
  } else {
    localRules.derived.push({
      key: 'answer_streaming',
      label: '回答耗时(s)',
      expr: `total_time - ${startKey}`
    })
  }
  emitChange()
}
const removeDerived = (idx) => {
  localRules.derived.splice(idx, 1)
  emitChange()
}
const addExtra = () => {
  localRules.extras_extract.push(normalizeExtra({
    key: '',
    label: '',
    from: 'json_field',
    field: '',
    trigger: 'first',
    match: {}
  }))
  emitChange()
}
const removeExtra = (idx) => {
  localRules.extras_extract.splice(idx, 1)
  emitChange()
}
const onExtraFromChange = (ex) => {
  if (ex.from === 'json_field' && !ex.field) ex.field = 'id'
  if (ex.from === 'eof_references') {
    if (!ex.field) ex.field = 'doc_name'
    if (!ex.match) ex.match = {}
    if (!ex.match.type) ex.match.type = 'eof'
  }
  if (ex.from === 'answer_collect') {
    if (!ex.agent) ex.agent = 'conventional_summary'
    if (ex.max_len == null) ex.max_len = 500
  }
  emitChange()
}
const fillDefaultExtras = () => {
  localRules.extras_extract = JSON.parse(JSON.stringify(defaultExtras()))
  emitChange()
}
</script>

<style scoped>
.stream-rule-builder {
  width: 100%;
  min-width: 0;
}

.rule-section {
  margin-bottom: 20px;
}

.rule-section-title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  letter-spacing: 0.02em;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.rule-block {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 12px;
  background: var(--el-fill-color-blank);
}

.rule-block.compact {
  padding: 12px 16px;
}

.rule-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.rule-block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.field-group {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.field-group-title {
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.field-grid {
  display: grid;
  gap: 12px 16px;
}

.field-grid.cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.field-grid.cols-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.field-grid.cols-4 {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.field-grid.cols-3 .span-wide {
  grid-column: 1 / -1;
}

.field-cell {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 12px;
  line-height: 1.2;
  color: var(--el-text-color-secondary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.tip-icon {
  color: var(--el-text-color-secondary);
  cursor: help;
  font-size: 14px;
  vertical-align: middle;
}

.tip-icon:hover {
  color: var(--el-color-primary);
}

.field-check-row {
  margin-top: 10px;
}

.match-extra-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}

.field-tip {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.55;
}

.field-tip code {
  font-size: 11px;
  padding: 0 4px;
  border-radius: 3px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
}

.tip-list {
  margin: 6px 0 0;
  padding-left: 18px;
}

.tip-list li {
  margin: 4px 0;
}

.time-points-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px;
}

.time-points-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.expr-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 12px;
  align-items: end;
}

.expr-minus {
  padding-bottom: 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  line-height: 1;
}

.expr-preview {
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.expr-preview code {
  font-size: 12px;
  color: var(--el-color-primary);
}

.rule-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 900px) {
  .field-grid.cols-4 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .field-grid.cols-3 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .expr-row {
    grid-template-columns: 1fr;
  }
  .expr-minus {
    display: none;
  }
}
</style>

<style>
/* tooltip 挂到 body，需非 scoped */
.stream-rule-tip-pop {
  max-width: 340px !important;
}
.stream-rule-tip-pop p {
  margin: 0 0 8px;
  line-height: 1.55;
  font-size: 12px;
}
.stream-rule-tip-pop p:last-child {
  margin-bottom: 0;
}
</style>
