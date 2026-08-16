<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑步骤' : '新增步骤'"
    width="700px"
    destroy-on-close
    @closed="handleClose"
  >
    <el-form 
      :model="form" 
      :rules="formRules"
      label-width="100px" 
      ref="formRef"
    >
      <!-- 步骤名称 -->
      <el-form-item label="操作名称" prop="desc">
        <div class="param-input-row">
          <el-input v-model="form.desc" placeholder="简短名称，如：点击登录" style="flex: 1" />
          <VarInsertButton :env-id="varInsertEnvId" label="变量" />
          <ToolInsertButton :env-id="varInsertEnvId" label="工具" />
        </div>
      </el-form-item>

      <el-form-item label="业务意图" prop="intent">
        <el-input
          v-model="form.intent"
          type="textarea"
          :rows="2"
          placeholder="可选。描述本步要完成的操作目标，供 AI 自愈参考。例：点击左侧导航栏的「基础设置」菜单项"
        />
        <p class="step-intent-hint">未填写时自愈使用「操作名称」。填写更具体的意图可提高自愈准确率。</p>
      </el-form-item>

      <el-form-item label="变量参考">
        <div class="step-insert-toolbar">
          <el-select
            v-model="varInsertEnvId"
            placeholder="参考环境"
            size="small"
            clearable
            style="width: 140px"
          >
            <el-option
              v-for="e in envList"
              :key="e.id"
              :label="e.name"
              :value="e.id"
            />
          </el-select>
          <VarInsertButton :env-id="varInsertEnvId" label="插入变量" hint-text="跨环境请优先用环境变量同名 key。" />
          <ToolInsertButton :env-id="varInsertEnvId" label="插入工具" />
          <el-button link type="info" size="small" @click="tagPickerVisible = true">数据工厂标签</el-button>
        </div>
        <p class="step-insert-hint">请先点击要填入的参数输入框，再选择插入项；执行时以运行环境为准。</p>
      </el-form-item>

      <AppH5UsageGuide
        v-if="showAppH5StepGuide"
        scope="step"
        :driver-mode="driverMode"
        :step-method="form.method"
        :has-h5-locator="appFormHasH5Locator"
        :has-image-locator="appFormHasImageLocator"
        :title="appStepGuideTitle"
      />

      <UiStepUsageGuide
        v-if="showUiStepUsageGuide && !hasParams"
        :method="form.method"
        show-label
        class="ui-step-usage-guide-standalone"
      />
      
      <!-- 数据库断言（专用表单） -->
      <el-form-item label="库断言" v-if="isDbAssertStep">
        <UiDbAssertStepFields
          :params="form.params"
          :project-id="projectId"
          :env-id="varInsertEnvId"
        />
      </el-form-item>

      <!-- input 文件上传：平台 MinIO 文件/文件夹选择 -->
      <el-form-item label="上传模式" v-if="isUploadFileStep">
        <el-radio-group v-model="uploadMode">
          <el-radio value="single">单文件</el-radio>
          <el-radio value="multiple">多文件</el-radio>
          <el-radio value="folder">文件夹</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="测试文件" v-if="isUploadFileStep && uploadMode === 'single'">
        <UiTestFilePicker v-model="form.params" :env-id="varInsertEnvId" />
      </el-form-item>
      <el-form-item label="测试文件" v-if="isUploadFileStep && uploadMode === 'multiple'">
        <UiTestMultiFilePicker v-model="form.params" :env-id="varInsertEnvId" />
      </el-form-item>
      <el-form-item label="测试文件夹" v-if="isUploadFileStep && uploadMode === 'folder'">
        <UiTestFolderPicker v-model="form.params" :env-id="varInsertEnvId" />
      </el-form-item>

      <el-form-item label="识别图" v-if="isWebVisionStep">
        <div class="web-vision-template">
          <el-upload
            :show-file-list="false"
            accept="image/png,image/jpeg,image/webp"
            :http-request="handleWebVisionTemplateUpload"
            :disabled="stepTemplateUploading"
          >
            <el-button type="primary" plain size="small" :loading="stepTemplateUploading">上传模板图</el-button>
          </el-upload>
          <el-input
            v-model="form.params.template"
            placeholder="MinIO 对象键，如 app-elements/1/xxx.png"
            class="web-vision-template-input"
          />
          <div class="web-vision-threshold">
            <span>相似度阈值</span>
            <el-slider v-model="form.params.threshold" :min="0.1" :max="0.99" :step="0.01" style="width: 200px" />
          </div>
          <el-image
            v-if="webVisionPreviewSrc"
            :src="webVisionPreviewSrc"
            fit="contain"
            class="step-template-preview"
            :preview-src-list="[webVisionPreviewSrc]"
          />
          <el-text type="info" size="small">固定 viewport 下匹配页面截图；Canvas/纯图标场景兜底，优先 DOM 定位。</el-text>
        </div>
      </el-form-item>

      <!-- 参数配置 -->
      <el-form-item v-if="hasParams && !isDbAssertStep">
        <template #label>
          <span class="params-section-label">
            {{ paramsSectionLabel }}
            <UiStepUsageGuide v-if="showUiStepUsageGuide" :method="form.method" />
          </span>
        </template>
        <div class="params-container" :class="{ 'is-smart-action': isSmartActionStep }">
          <el-alert
            v-if="isDragDropStep"
            type="info"
            :closable="false"
            show-icon
            class="drag-position-hint"
          >
            <template #title>拖拽落点坐标</template>
            <p>坐标相对元素<strong>左上角</strong>，单位像素；X/Y 需成对填写才生效，留空则落在元素中心。</p>
            <p class="drag-position-example">
              例：把「拖拽目录2」插到「拖拽目录1」前面 →
              起始=<code>目录2</code>，结束=<code>目录1</code>，目标 X=<code>20</code>，目标 Y=<code>5</code>
            </p>
          </el-alert>
          <el-alert
            v-if="isSmartStep"
            type="info"
            :closable="false"
            show-icon
            class="drag-position-hint"
          >
            <template #title>智能步骤</template>
            <p>用自然语言描述本步要完成的操作；执行时由 AI 结合当前页面规划并执行。</p>
            <p class="drag-position-example">
              多步可写编号列表，保存时自动拆成多条智能步骤，例如：
              <code>1. 在搜索框输入订单号</code>、<code>2、点击查询按钮</code>
            </p>
          </el-alert>
          <SmartActionGuide
            v-if="isSmartActionStep"
            :method="form.method"
          />
          <div v-if="canConvertCurrentToSmart" class="smart-convert-bar">
            <el-button type="primary" plain size="small" @click="convertCurrentToSmart">
              {{ convertSmartButtonLabel }}
            </el-button>
            <span class="smart-convert-hint">保留 locator / value / 录制候选，改为消歧执行</span>
          </div>
          <el-alert
            v-if="isElementOrderStep"
            type="info"
            :closable="false"
            show-icon
            class="drag-position-hint"
          >
            <template #title>元素顺序断言</template>
            <p>按 <strong>DOM 文档顺序</strong>判断两个元素谁先谁后，适用于列表、表格行、树节点同级排序等场景。</p>
            <p class="drag-position-example">
              例：拖拽后断言「目录2」在「目录1」前面 →
              靠前元素=<code>#treebox nz-tree-node-title[title="拖拽目录2"]</code>，
              参照元素=<code>…[title="拖拽目录1"]</code>，
              期望顺序=<code>前面</code>
            </p>
            <p class="drag-position-example">
              断言「1 在 2 后面」可设期望顺序为「后面」，或交换两个定位表达式并保持「前面」。
            </p>
          </el-alert>
          <div 
            class="param-item" 
            v-for="(value, key) in filteredParams" 
            :key="key"
          >
            <div class="param-label">
              <span>{{ resolveParamLabel(key) }}</span>
              <span v-if="isRequiredParam(key)" class="required-mark">*</span>
              <el-tooltip
                v-if="resolveParamTooltip(key)"
                placement="top"
                :show-after="200"
                popper-class="param-tip-popper"
              >
                <template #content>
                  <div class="param-tip-content">{{ resolveParamTooltip(key) }}</div>
                </template>
                <el-icon class="param-tip-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
            
            <!-- SMART-1：后置条件结构化表单 -->
            <template v-if="key === 'expected_after'">
              <ExpectedAfterFields v-model="form.params.expected_after" />
            </template>
            <!-- 根据参数类型渲染不同输入框 -->
            <template v-else-if="isAppObjectLocator(key)">
              <div v-if="form.params[key].by === 'image'" class="app-image-locator">
                <div class="app-locator-row">
                  <el-select v-model="form.params[key].by" placeholder="定位方式" style="width: 140px" @change="onAppLocatorByChange(key)">
                    <el-option v-for="opt in appLocatorByOptions(key)" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                  <el-upload
                    :show-file-list="false"
                    accept="image/png,image/jpeg,image/webp"
                    :http-request="(req) => handleStepTemplateUpload(req, key)"
                    :disabled="stepTemplateUploading"
                  >
                    <el-button type="primary" plain size="small" :loading="stepTemplateUploading">上传识别图</el-button>
                  </el-upload>
                </div>
                <div v-if="form.params[key].value" class="step-template-path">{{ form.params[key].value }}</div>
                <el-text type="info" size="small">图像识别定位暂不支持 AI 自愈</el-text>
                <el-image
                  v-if="stepTemplatePreviewSrc(key)"
                  :src="stepTemplatePreviewSrc(key)"
                  fit="contain"
                  class="step-template-preview"
                  :preview-src-list="[stepTemplatePreviewSrc(key)]"
                />
                <div class="app-image-fields">
                  <span class="field-label">相似度阈值</span>
                  <el-slider
                    v-model="form.params[key].threshold"
                    :min="0.5"
                    :max="1"
                    :step="0.05"
                    :disabled="false"
                    style="flex: 1"
                  />
                  <span class="field-label">RGB</span>
                  <el-switch v-model="form.params[key].rgb" />
                </div>
                <div class="app-image-fields">
                  <span class="field-label">中心偏移</span>
                  <el-input
                    :model-value="formatLocatorPair(form.params[key].record_pos)"
                    placeholder="相对屏幕中心，如 0.12,-0.05"
                    :disabled="false"
                    style="flex: 1"
                    @update:model-value="(v) => setLocatorPair(form.params[key], 'record_pos', v)"
                  />
                  <span class="field-label">录制分辨率</span>
                  <el-input
                    :model-value="formatLocatorPair(form.params[key].resolution)"
                    placeholder="宽,高，如 1080,2400"
                    :disabled="false"
                    style="flex: 1"
                    @update:model-value="(v) => setLocatorPair(form.params[key], 'resolution', v)"
                  />
                </div>
              </div>
              <div v-else class="app-locator-row">
                <el-select
                  v-model="form.params[key].context"
                  placeholder="定位环境"
                  style="width: 130px"
                  @change="onAppLocatorContextChange(key)"
                >
                  <el-option label="原生 App" :value="APP_LOCATOR_CONTEXT_NATIVE" />
                  <el-option label="WebView / H5" value="webview" />
                </el-select>
                <el-select v-model="form.params[key].by" placeholder="定位方式" style="width: 140px" @change="onAppLocatorByChange(key)">
                  <el-option v-for="opt in appLocatorByOptions(key)" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
                <el-input v-model="form.params[key].value" placeholder="定位值" style="flex: 1" @input="onAppLocatorFieldEdited" />
                <el-input-number v-model="form.params[key].index" :min="1" :max="99" controls-position="right" style="width: 100px" @change="onAppLocatorFieldEdited" />
                <el-button type="primary" link :loading="healingLocator" @click="handleHealLocator">AI 自愈</el-button>
              </div>
            </template>
            <template v-else-if="isAppLocatorRefKey(key)">
              <div class="locator-ref-row">
                <el-select
                  v-model="form.params[key]"
                  filterable
                  clearable
                  placeholder="选择元素库引用（同步到上方定位，可再编辑）"
                  style="flex: 1"
                  @change="onLocatorRefChange"
                >
                  <el-option v-for="opt in appElementOptions" :key="opt.name" :label="opt.name" :value="opt.name">
                    <span>{{ opt.name }}</span>
                    <span style="color: #909399; margin-left: 8px">{{ formatElementLocator(opt.locator) }}</span>
                  </el-option>
                </el-select>
                <el-button type="primary" link @click="openAppInspector">元素探查</el-button>
              </div>
            </template>
            <template v-else-if="isLocatorKey(key)">
              <div class="locator-heal-row">
                <LocatorSelector
                  v-model="form.params[key]"
                  :meta="props.step?.meta || {}"
                />
                <el-button
                  type="primary"
                  link
                  :loading="healingLocator"
                  @click="handleHealLocator"
                >AI 自愈</el-button>
              </div>
            </template>
            <template v-else-if="isFillValueParam(key)">
              <div class="param-input-row">
                <FillValueInput v-model="form.params[key]" style="flex: 1" />
                <VarInsertButton
                  v-if="isFillValueFixedMode(form.params[key])"
                  :env-id="varInsertEnvId"
                  label="变量"
                />
              </div>
            </template>
            <template v-else-if="isLongTextKey(key)">
              <div class="param-input-row">
                <el-input
                  v-model="form.params[key]"
                  type="textarea"
                  :rows="2"
                  :placeholder="smartParamPlaceholder(key) || (isRequiredParam(key) ? '必填' : '请输入')"
                  style="flex: 1"
                />
                <VarInsertButton v-if="canInsertVar(key)" :env-id="varInsertEnvId" label="变量" />
                <ToolInsertButton v-if="canInsertVar(key)" :env-id="varInsertEnvId" label="工具" />
              </div>
            </template>
            <template v-else-if="isNumber(value)">
              <el-input-number
                v-model="form.params[key]"
                :style="{ width: compactNumberWidth(key) }"
                controls-position="right"
              />
            </template>
            <template v-else-if="isSelect(key)">
              <el-select v-model="form.params[key]" style="width: 100%">
                <el-option 
                  v-for="opt in getOptions(key)" 
                  :key="opt.value" 
                  :label="opt.label" 
                  :value="opt.value" 
                />
              </el-select>
            </template>
            <template v-else-if="isBoolean(key)">
              <el-switch v-model="form.params[key]" />
            </template>
            <template v-else>
              <div class="param-input-row">
                <el-input
                  v-model="form.params[key]"
                  :placeholder="smartParamPlaceholder(key) || (isRequiredParam(key) ? '必填' : '请输入')"
                  style="flex: 1"
                />
                <VarInsertButton v-if="canInsertVar(key)" :env-id="varInsertEnvId" label="变量" />
                <ToolInsertButton v-if="canInsertVar(key)" :env-id="varInsertEnvId" label="工具" />
              </div>
            </template>
          </div>

          <el-collapse
            v-if="isSmartActionStep && smartTuningParamEntries.length"
            v-model="smartTuningOpen"
            class="smart-tuning-params"
          >
            <el-collapse-item name="smart-tuning">
              <template #title>
                <span class="smart-tuning-title">消歧与兜底（可选）</span>
                <span class="smart-tuning-hint">多数场景保持默认即可</span>
              </template>
              <div
                v-for="[key, value] in smartTuningParamEntries"
                :key="'smart-tuning-' + key"
                class="param-item"
              >
                <div class="param-label">
                  <span>{{ resolveParamLabel(key) }}</span>
                  <el-tooltip
                    v-if="resolveParamTooltip(key)"
                    placement="top"
                    :show-after="200"
                    popper-class="param-tip-popper"
                  >
                    <template #content>
                      <div class="param-tip-content">{{ resolveParamTooltip(key) }}</div>
                    </template>
                    <el-icon class="param-tip-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </div>
                <template v-if="isBoolean(key)">
                  <el-switch v-model="form.params[key]" />
                </template>
                <template v-else-if="isNumber(value)">
                  <el-input-number
                    v-model="form.params[key]"
                    :style="{ width: compactNumberWidth(key) }"
                    :min="key === 'min_score' || key === 'min_margin' ? 0 : undefined"
                    :max="key === 'min_score' || key === 'min_margin' ? 100 : undefined"
                    :step="key === 'min_score' || key === 'min_margin' ? 5 : 1"
                    controls-position="right"
                  />
                </template>
                <template v-else>
                  <el-input v-model="form.params[key]" placeholder="可选" style="width: 100%" />
                </template>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-form-item>
      
      <!-- 条件分支配置 -->
      <el-form-item label="分支配置" v-if="isConditionBranch" class="condition-branch-form-item">
        <ConditionEdit v-model:branches="form.branches" :module="module" />
      </el-form-item>
      
      <!-- 高级配置（App 步骤使用 params 内超时，不展示此项） -->
      <el-form-item v-if="!isConditionBranch && !isAppStep" label-width="0" class="advanced-form-item">
        <div class="advanced-panel">
          <button type="button" class="advanced-toggle" @click="showAdvanced = !showAdvanced">
            <span class="advanced-toggle-main">
              <span class="advanced-toggle-title">高级配置</span>
              <span class="advanced-toggle-hint">{{ advancedToggleHint }}</span>
              <el-tag v-if="advancedActiveCount > 0" size="small" type="warning" effect="plain" round>
                已启用 {{ advancedActiveCount }} 项
              </el-tag>
            </span>
            <el-icon class="advanced-arrow" :class="{ 'is-open': showAdvanced }"><ArrowDown /></el-icon>
          </button>

          <div v-show="showAdvanced" class="advanced-body">
            <section class="advanced-section">
              <div class="advanced-section-head">
                <h4>超时与重试</h4>
              </div>
              <div class="advanced-grid">
                <div class="advanced-field">
                  <span class="advanced-field-label">超时时间</span>
                  <div class="advanced-field-control">
                    <el-input-number
                      v-model="form.config.timeout"
                      :min="1000"
                      :step="1000"
                      controls-position="right"
                      style="width: 140px"
                      @change="onTimeoutExplicitChange"
                    />
                    <span class="advanced-unit">ms</span>
                  </div>
                </div>
                <div class="advanced-field">
                  <span class="advanced-field-label">执行前等待</span>
                  <div class="advanced-field-control">
                    <el-input-number
                      v-model="form.config.pre_wait_ms"
                      :min="0"
                      :max="600000"
                      :step="100"
                      controls-position="right"
                      style="width: 140px"
                    />
                    <span class="advanced-unit">ms</span>
                  </div>
                </div>
                <div class="advanced-field">
                  <span class="advanced-field-label">失败重试</span>
                  <el-switch v-model="form.config.retry" />
                </div>
              </div>
            </section>

            <section v-if="hasClickAdvanced" class="advanced-section">
              <div class="advanced-section-head">
                <h4>动作前就绪 · 动作后等待 · 原生弹窗 / 文件下载</h4>
                <UiStepUsageGuide :method="form.method" />
              </div>
              <p class="advanced-section-desc">
                慢站：动作前可用「就绪选择器 / 使用环境就绪」；保存/查询后列表刷新填「动作后等待选择器」。
                页面二次确认 Dialog：请拆成两步点击。
                以下原生弹窗/下载仅用于系统弹窗或导出文件。
              </p>
              <div class="params-container advanced-params">
                <div
                  class="param-item"
                  v-for="(value, key) in advancedParams"
                  :key="'adv-' + key"
                >
                  <div class="param-label">
                    <span>{{ resolveParamLabel(key) }}</span>
                    <el-tooltip
                      v-if="resolveParamTooltip(key)"
                      placement="top"
                      :show-after="200"
                      popper-class="param-tip-popper"
                    >
                      <template #content>
                        <div class="param-tip-content">{{ resolveParamTooltip(key) }}</div>
                      </template>
                      <el-icon class="param-tip-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </div>
                  <template v-if="isBoolean(key)">
                    <el-switch
                      v-model="form.params[key]"
                      @change="(val) => onClickAdvancedSwitch(key, val)"
                    />
                  </template>
                  <template v-else-if="isNumber(value)">
                    <el-input-number
                      v-model="form.params[key]"
                      :style="{ width: compactNumberWidth(key) }"
                      controls-position="right"
                    />
                  </template>
                  <template v-else>
                    <div class="param-input-row">
                      <el-input
                        v-model="form.params[key]"
                        :placeholder="isRequiredParam(key) ? '必填' : '可选'"
                        style="flex: 1"
                      />
                      <VarInsertButton v-if="canInsertVar(key)" :env-id="varInsertEnvId" label="变量" />
                      <ToolInsertButton v-if="canInsertVar(key)" :env-id="varInsertEnvId" label="工具" />
                    </div>
                  </template>
                </div>
              </div>
            </section>
          </div>
        </div>
      </el-form-item>
    </el-form>
    
    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>

  <DataFactoryTagPicker
    v-model="tagPickerVisible"
    :project-id="projectId"
    @insert="onDfTagInsert"
  />

  <el-dialog v-model="healDialogVisible" title="AI 定位器自愈" width="520px" append-to-body destroy-on-close>
    <el-form label-width="120px">
      <el-form-item label="抓取方式">
        <el-radio-group v-model="healMode">
          <el-radio value="replay" :disabled="!canReplay">回放前置步骤</el-radio>
          <el-radio value="url">仅打开 URL</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="healMode === 'replay'" label="回放至第 N 步">
        <el-input-number v-model="healReplayThrough" :min="1" :max="Math.max(1, props.stepIndex)" />
        <div class="heal-hint">将执行用例第 1～{{ healReplayThrough }} 步（不含当前第 {{ props.stepIndex + 1 }} 步），再抓取页面 snapshot</div>
      </el-form-item>
      <el-form-item :label="healMode === 'replay' ? '备用 URL' : '页面 URL'">
        <el-input
          v-model="healPageUrl"
          :placeholder="healMode === 'replay' ? '步骤中无 open_url 时填写' : 'https://example.com/page'"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="healDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="healingLocator" @click="confirmHeal">开始自愈</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, QuestionFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import FillValueInput from '@/components/StepEditor/FillValueInput.vue'
import ConditionEdit from '@/components/StepEditor/ConditionEdit.vue'
import { FILL_VALUE_INPUT_METHODS, isFillValueFixedMode } from '@/utils/fillValueMode.js'
import LocatorSelector from '@/components/LocatorSelector.vue'
import VarInsertButton from '@/components/VarInsertButton.vue'
import ToolInsertButton from '@/components/ToolInsertButton.vue'
import DataFactoryTagPicker from '@/views/ApiModule/components/DataFactoryTagPicker.vue'
import UiDbAssertStepFields from './UiDbAssertStepFields.vue'
import ExpectedAfterFields from './ExpectedAfterFields.vue'
import SmartActionGuide from './SmartActionGuide.vue'
import { canConvertToSmart, convertStepToSmart } from '@/utils/stepHelper'
import UiTestFilePicker from './UiTestFilePicker.vue'
import UiTestMultiFilePicker from './UiTestMultiFilePicker.vue'
import UiTestFolderPicker from './UiTestFolderPicker.vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { insertVarRef } from '@/utils/varInsert.js'
import { getOrderedVisibleParams, getParamLabel, getParamTooltip, getStepUsageGuide, hasStepAdvancedParams, isDragDropMethod, isElementOrderMethod, isAssertionMethod } from '@/utils/uiStepMeta.js'
import { splitSmartStepIntents } from '@/utils/smartStepSplit.js'
import { generateStepId } from '@/utils/stepHelper.js'
import { getAppOrderedVisibleParams, getAppParamLabel, getAppParamTooltip, isAppMethod, isAppRequiredParam, getAppSelectOptions, validateAppStepParams, validateAppBranchConditions, getAppLocatorByOptions, isWebviewLocator, isImageLocator, isAppLocatorFilled, APP_LOCATOR_CONTEXT_NATIVE, applyDefaultAppIdToStepParams, getProjectDefaultAppId, prepareAppLocatorForEdit, serializeAppLocatorForSave, normalizeAppLocator } from '@/utils/appStepMeta.js'
import { presignTemplateKeys, resolveTemplatePreviewUrl } from '@/utils/appTemplatePresign.js'
import AppH5UsageGuide from '@/components/App/AppH5UsageGuide.vue'
import UiStepUsageGuide from './UiStepUsageGuide.vue'
import { appElementApi } from '@/api/modules/app.js'
import { aiGenerateApi } from '@/api/modules/ai.js'

const router = useRouter()
const route = useRoute()
const proStore = ProjectStore()
const varInsertEnvId = inject('varInsertEnvId', ref(null))
const saveAppInspectorDraft = inject('saveAppInspectorDraft', null)
const envList = computed(() => proStore.envList || [])
const projectId = computed(() => proStore.projectInfo?.id)
const tagPickerVisible = ref(false)
const appElementOptions = ref([])
const stepTemplateUploading = ref(false)
const stepTemplatePreviewMap = ref({})

async function onDfTagInsert(refStr) {
  const m = String(refStr).match(/^\$\{\{(.+)\}\}$/)
  const name = m ? m[1] : refStr
  const result = await insertVarRef(name)
  if (result?.ok) {
    const tip =
      result.mode === 'copy'
        ? `已复制 ${refStr}，请粘贴到目标输入框`
        : `已插入 ${refStr}`
    ElMessage.success(tip)
  } else {
    ElMessage.warning('请先将光标放入要填入的输入框')
  }
}

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  step: {
    type: Object,
    default: null
  },
  allSteps: {
    type: Array,
    default: () => []
  },
  stepIndex: {
    type: Number,
    default: -1
  },
  stepPath: {
    type: Array,
    default: () => [],
  },
  module: {
    type: String,
    default: 'web'
  },
  driverMode: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:visible', 'save', 'save-multiple', 'cancel'])

const formRef = ref()
const form = ref({
  id: '',
  keyword: '',
  desc: '',
  intent: '',
  method: '',
  params: {},
  config: { timeout: 30000, retry: false, pre_wait_ms: 0, timeout_explicit: false }
})
const showAdvanced = ref(false)
const healingLocator = ref(false)
const healPageUrl = ref('')
const healDialogVisible = ref(false)
const healMode = ref('replay')
const healReplayThrough = ref(1)

const canReplay = computed(() => props.stepIndex > 0 && (props.allSteps?.length || 0) > 0)

const effectiveStepPath = computed(() => {
  if (Array.isArray(props.stepPath) && props.stepPath.length) return props.stepPath
  if (props.stepIndex >= 0) return [props.stepIndex]
  return []
})

// 是否是编辑模式
const isEdit = computed(() => !!props.step?.id)

// 是否是 App 步骤（仅按编辑器 module 区分；Web/App 存在同名 method 如 extract_text、open_url）
const isAppStep = computed(() => props.module === 'app')

const H5_CONTEXT_METHODS = new Set(['switch_webview', 'switch_chrome', 'switch_native', 'open_url'])

const appFormHasH5Locator = computed(() => isWebviewLocator(form.value.params?.locator))
const appFormHasImageLocator = computed(() => isImageLocator(form.value.params?.locator))

const appStepGuideTitle = computed(() => {
  if (appFormHasImageLocator.value) return '本步骤图像识别说明'
  if (appFormHasH5Locator.value || H5_CONTEXT_METHODS.has(form.value.method)) return '本步骤 H5 / WebView 说明'
  return 'App 步骤说明'
})

const showAppH5StepGuide = computed(() => {
  if (!isAppStep.value) return false
  const method = form.value.method
  if (H5_CONTEXT_METHODS.has(method)) return true
  if (appFormHasH5Locator.value) return true
  if (appFormHasImageLocator.value) return true
  if (['hybrid_web', 'mobile_chrome'].includes(props.driverMode) && form.value.params?.locator) {
    return true
  }
  return false
})

const isConditionBranch = computed(() => {
  return form.value.method === 'condition_branch'
})

const isDbAssertStep = computed(() => form.value.method === 'kw_db_assert')

const isUploadFileStep = computed(() => form.value.method === 'upload_file')

const WEB_VISION_METHODS = new Set(['click_by_image', 'fill_by_image', 'wait_for_image', 'kw_assert_image', 'kw_assert_image_not_exists'])
const isWebVisionStep = computed(
  () => !isAppStep.value && WEB_VISION_METHODS.has(form.value.method),
)

const webVisionHiddenKeys = new Set(['template', 'threshold'])

const uploadMode = computed({
  get: () => (form.value.params?.upload_mode || 'single'),
  set: (val) => {
    if (!form.value.params) form.value.params = {}
    form.value.params.upload_mode = val
  },
})

const isDragDropStep = computed(() => isDragDropMethod(form.value.method))

const isSmartStep = computed(() => form.value.method === 'smart_step')

const isSmartActionStep = computed(() =>
  form.value.method === 'smart_click' || form.value.method === 'smart_fill',
)

/** 智能点击/输入：消歧阈值等次要项，主表单收起展示 */
const SMART_TUNING_PARAM_KEYS = ['min_score', 'min_margin', 'allow_ai', 'force']

const smartTuningOpen = ref([])

const canConvertCurrentToSmart = computed(() =>
  !isAppStep.value && canConvertToSmart(form.value),
)

const convertSmartButtonLabel = computed(() => {
  if (form.value.method === 'fill_value') return '转为智能输入'
  return '转为智能点击'
})

const isElementOrderStep = computed(() => isElementOrderMethod(form.value.method))

function convertCurrentToSmart() {
  const next = convertStepToSmart(form.value)
  if (!next) return
  form.value.method = next.method
  form.value.keyword = next.keyword
  form.value.params = { ...(next.params || {}) }
  if (next.meta) form.value.meta = next.meta
  ElMessage.success(
    `已转为「${next.keyword}」，请补全「要点谁 / 本步要做什么」${next.method === 'smart_click' ? '，危险操作再配「点完后应看到」' : ''}`,
  )
}

const showUiStepUsageGuide = computed(() => {
  if (isAppStep.value || isDbAssertStep.value) return false
  // 点击类说明放在高级配置分区标题旁，避免主表单被打扰
  if (hasStepAdvancedParams(form.value.method)) return false
  return !!getStepUsageGuide(form.value.method)
})

const hasClickAdvanced = computed(() => hasStepAdvancedParams(form.value.method))

const advancedParams = computed(() => {
  if (!hasClickAdvanced.value) return {}
  const raw = { ...(form.value.params || {}) }
  return getOrderedVisibleParams(form.value.method, raw, { scope: 'advanced' })
})

const advancedActiveCount = computed(() => {
  if (!hasClickAdvanced.value) return 0
  const p = form.value.params || {}
  let n = 0
  if (p.wait_download) n += 1
  if (p.accept_dialog) n += 1
  if (p.dismiss_dialog) n += 1
  if (String(p.ready_selector || '').trim()) n += 1
  if (p.use_env_ready) n += 1
  if (String(p.expected_selector || '').trim()) n += 1
  if (p.wait_busy_after) n += 1
  return n
})

const advancedToggleHint = computed(() => {
  if (hasClickAdvanced.value) return '超时 · 动作前就绪 · 动作后等待 · 弹窗 / 下载'
  return '超时 · 重试'
})

function onTimeoutExplicitChange() {
  if (!form.value.config || typeof form.value.config !== 'object') {
    form.value.config = { timeout: 30000, retry: false, pre_wait_ms: 0, timeout_explicit: true }
    return
  }
  form.value.config.timeout_explicit = true
}

function onClickAdvancedSwitch(key, val) {
  if (!form.value.params) form.value.params = {}
  if (key === 'accept_dialog' && val) {
    form.value.params.dismiss_dialog = false
  }
  if (key === 'dismiss_dialog' && val) {
    form.value.params.accept_dialog = false
  }
}

const paramsSectionLabel = computed(() => {
  if (form.value.method === 'smart_click') return '智能点击参数'
  if (form.value.method === 'smart_fill') return '智能输入参数'
  return isAssertionMethod(form.value.method) ? '断言参数' : '配置参数'
})

const uploadFileHiddenKeys = new Set([
  'file_path', 'file_key', 'file_bucket', 'file_name', 'upload_as_name', 'file_items',
  'upload_mode', 'folder_key', 'folder_bucket', 'folder_name',
])

// 表单校验规则
const formRules = {
  desc: [
    { required: true, message: '请输入操作名称', trigger: 'blur' }
  ]
}

// 过滤后的参数（按 method 元数据控制可见字段与顺序）
const filteredParams = computed(() => {
  const raw = { ...(form.value.params || {}) }
  const keepTimeoutMethods = ['wait_for_time', 'set_default_timeout']
  if (form.value.method === 'upload_file') {
    uploadFileHiddenKeys.forEach((key) => delete raw[key])
  }
  if (isWebVisionStep.value) {
    webVisionHiddenKeys.forEach((key) => delete raw[key])
  }
  if (!keepTimeoutMethods.includes(form.value.method) && !isAppStep.value) {
    delete raw.timeout
  }
  if (isAppStep.value) {
    return getAppOrderedVisibleParams(form.value.method, raw)
  }
  const ordered = getOrderedVisibleParams(form.value.method, raw, { scope: 'basic' })
  if (!isSmartActionStep.value) return ordered
  const basic = { ...ordered }
  SMART_TUNING_PARAM_KEYS.forEach((key) => delete basic[key])
  return basic
})

const smartTuningParamEntries = computed(() => {
  if (!isSmartActionStep.value) return []
  const params = form.value.params || {}
  return SMART_TUNING_PARAM_KEYS
    .filter((key) => Object.prototype.hasOwnProperty.call(params, key))
    .map((key) => [key, params[key]])
})

// 是否有参数
const hasParams = computed(() => {
  return Object.keys(filteredParams.value).length > 0
    || smartTuningParamEntries.value.length > 0
})

function resolveParamLabel(key) {
  if (form.value.method === 'scroll_to_height' && key === 'height') {
    const pos = String(form.value.params?.position || 'height').toLowerCase()
    if (pos === 'up' || pos === 'down') return '滚动距离(像素)'
    return '绝对高度(距顶部像素)'
  }
  if (isAppStep.value) {
    return getAppParamLabel(form.value.method, key, paramLabelMap[key])
  }
  return getParamLabel(form.value.method, key, paramLabelMap[key])
}

function resolveParamTooltip(key) {
  if (isAppStep.value) {
    return getAppParamTooltip(form.value.method, key)
  }
  return getParamTooltip(form.value.method, key)
}

/** 智能点击/输入字段占位提示 */
function smartParamPlaceholder(key) {
  if (!isSmartActionStep.value) return ''
  const fill = form.value.method === 'smart_fill'
  const map = {
    target: fill ? '如：用户名、手机号' : '如：新增、确定、提交',
    intent: fill ? '如：在创建用户弹窗中填写登录名' : '如：点击顶部工具栏新增，打开创建弹窗',
    region: fill ? '如：创建用户弹窗、筛选区' : '如：顶部工具栏、确认删除弹窗',
    value: '要写入输入框的内容',
    locator: '可选，粘贴录制或自愈得到的定位',
  }
  return map[key] || ''
}

// 判断参数是否必填
function isRequiredParam(key) {
  const method = form.value.method
  if (isAppStep.value) {
    return isAppRequiredParam(method, key)
  }
  const assertionRequired = {
    kw_assert_page_title: ['title'],
    kw_assert_page_url: ['url'],
    kw_assert_value: ['locator', 'value'],
    kw_assert_element_text: ['locator', 'text'],
    kw_assert_element_text_contains: ['locator', 'text'],
    kw_assert_text_contains: ['text'],
    kw_assert_attribute: ['locator', 'attr_name', 'value'],
    kw_assert_visible: ['locator'],
    kw_assert_hidden: ['locator'],
    kw_assert_not_exist: ['locator'],
    kw_assert_not_visible: ['locator'],
    kw_assert_enabled: ['locator'],
    kw_assert_disabled: ['locator'],
    kw_assert_checked: ['locator'],
    kw_assert_empty: ['locator'],
    kw_assert_editable: ['locator'],
    kw_assert_focused: ['locator'],
    kw_assert_element_order: ['first_locator', 'second_locator'],
  }
  if (assertionRequired[method]) {
    return assertionRequired[method].includes(key)
  }
  if (WEB_VISION_METHODS.has(method)) {
    if (method === 'fill_by_image') {
      return key === 'template' || key === 'value'
    }
    return key === 'template'
  }
  if (method === 'smart_step') {
    return key === 'intent'
  }
  if (method === 'smart_click') {
    return key === 'target' || key === 'intent'
  }
  if (method === 'smart_fill') {
    return key === 'target' || key === 'intent' || key === 'value'
  }
  if (method === 'scroll_to_height') {
    if (key === 'position') return true
    if (key === 'height') {
      const pos = String(form.value.params?.position || 'height').toLowerCase()
      return !['top', 'middle', 'bottom'].includes(pos)
    }
    return false
  }
  if (method === 'mouse_wheel') {
    if (key === 'direction') return true
    if (key === 'amount') {
      const dir = String(form.value.params?.direction || 'custom').toLowerCase()
      return ['down', 'up', 'left', 'right'].includes(dir)
    }
    return false
  }
  // url 仅对这些方法必填；切换/关闭页面的 url 是可选匹配条件，不能进全局必填列表
  const urlRequiredMethods = new Set(['open_url', 'wait_for_url_contains', 'kw_assert_page_url'])
  if (key === 'url') {
    return urlRequiredMethods.has(method)
  }
  if (method === 'switch_to_page' || method === 'close_page' || method === 'open_new_page') {
    return false
  }
  const requiredParams = ['selector', 'condition', 'locator', 'var_name', 'attr_name', 'value', 'text']
  return requiredParams.includes(key)
}

// 参数标签映射（完整的参数映射表）
const paramLabelMap = {
  // 页面操作
  browser_type: '浏览器类型',
  url: '页面url地址',
  wait_until: '等待状态',
  timeout: '超时时间(毫秒)',
  tag: '页面标签名',
  index: '顺序索引',
  title: '网页标题',
  name: '截图名称',
  height: '滚动高度',
  script: 'JS脚本(箭头函数)',
  args: '传给JS的参数',
  
  // 元素操作
  locator: '元素定位表达式',
  selector: '元素定位表达式',
  value: '输入值',
  button: '按键(left/right)',
  count: '点击次数',
  ready_selector: '动作前就绪选择器',
  use_env_ready: '使用环境就绪选择器',
  expected_selector: '动作后等待选择器',
  post_wait_state: '动作后等待状态',
  wait_busy_after: '动作后再等忙碌遮罩',
  start_selector: '起始元素定位',
  end_selector: '结束元素定位',
  first_locator: '靠前元素定位',
  second_locator: '靠后参照元素定位',
  first_index: '靠前元素索引',
  second_index: '参照元素索引',
  order: '期望顺序',
  source_position_x: '起始落点X(像素)',
  source_position_y: '起始落点Y(像素)',
  target_position_x: '目标落点X(像素)',
  target_position_y: '目标落点Y(像素)',
  delay: '时长(秒)',
  
  // 鼠标键盘
  x: 'X坐标',
  y: 'Y坐标',
  key: '按键',
  keys: '输入文本',
  button: '鼠标按键',
  
  // iframe操作
  frame: 'iframe定位表达式',
  
  // 断言
  expect_results: '预期结果',
  is_equal: '是否相等',
  attr_name: '属性名称',
  text: '预期文本',
  match_mode: '匹配方式',
  
  // 变量提取
  var_name: '变量名',
  
  // 文件上传
  file_path: '文件绝对路径',
  
  // 强制点击 / 点击高级（标签以 uiStepMeta 为准，此处兜底）
  force: '强制点击(绕过遮挡)',
  wait_download: '点击后等待文件下载',
  accept_dialog: '自动点原生弹窗「确定」',
  dismiss_dialog: '自动点原生弹窗「取消」',
  dialog_timeout: '等待原生弹窗超时',
  use_regex: '使用正则匹配',
  save_path: '下载保存路径',
  download_timeout: '下载超时(毫秒)',
}

// 长文本类型的key
const longTextKeys = ['url', 'selector', 'script', 'condition', 'text', 'value', 'path', 'download_path', 'intent']

function repairWebStepParams(params) {
  if (!params || typeof params !== 'object') return params || {}
  const next = { ...params }
  for (const key of ['locator', 'selector', 'first_locator', 'second_locator']) {
    const v = next[key]
    if (v && typeof v === 'object' && v.by !== undefined) {
      next[key] = v.value != null ? String(v.value) : ''
    }
  }
  if (next.locator_ref != null) {
    delete next.locator_ref
  }
  return next
}

/** 历史步骤补齐顺序索引默认值，避免编辑页数字框空白（引擎侧本就默认 1） */
function ensureWebIndexDefaults(method, params) {
  const next = { ...(params || {}) }
  if (!method) return next
  const ordered = getOrderedVisibleParams(method, next, { scope: 'basic' })
  const advanced = getOrderedVisibleParams(method, next, { scope: 'advanced' })
  const merged = { ...ordered, ...advanced }
  for (const key of ['index', 'source_index', 'target_index', 'first_index', 'second_index']) {
    if (!Object.prototype.hasOwnProperty.call(merged, key)) continue
    if (next[key] == null || next[key] === '') {
      next[key] = merged[key] ?? 1
    }
  }
  return next
}

function normalizeScrollToHeightParams(params) {
  const next = { ...(params || {}) }
  if (!next.position) next.position = 'height'
  const pos = String(next.position).toLowerCase()
  if (next.height == null || next.height === '') {
    next.height = (pos === 'up' || pos === 'down') ? 600 : 0
  } else if (typeof next.height === 'string' && String(next.height).trim() !== '' && !Number.isNaN(Number(next.height))) {
    next.height = Number(next.height)
  }
  return next
}

function normalizeMouseWheelParams(params) {
  const next = { ...(params || {}) }
  let dir = String(next.direction || '').trim().toLowerCase()
  if (!dir) dir = 'custom'
  next.direction = dir
  const preset = ['down', 'up', 'left', 'right'].includes(dir)
  const toNum = (v, fallback) => {
    if (v == null || v === '') return fallback
    const n = Number(v)
    return Number.isFinite(n) ? n : fallback
  }
  if (preset) {
    const fallback = (dir === 'left' || dir === 'right')
      ? Math.abs(toNum(next.x, 600))
      : Math.abs(toNum(next.y, 600))
    const amount = Math.abs(toNum(next.amount, fallback || 600)) || 600
    next.amount = amount
    if (dir === 'down') {
      next.x = 0
      next.y = amount
    } else if (dir === 'up') {
      next.x = 0
      next.y = -amount
    } else if (dir === 'left') {
      next.x = -amount
      next.y = 0
    } else {
      next.x = amount
      next.y = 0
    }
  } else {
    next.x = toNum(next.x, 0)
    next.y = toNum(next.y, 600)
  }
  if (next.cursor_x == null) next.cursor_x = ''
  if (next.cursor_y == null) next.cursor_y = ''
  return next
}

// 监听 step 变化
watch(() => props.step, (newStep) => {
  if (newStep) {
    // 确保条件分支有branches字段
    const stepData = { ...newStep }
    if (stepData.method === 'condition_branch' && !stepData.branches) {
      const defaultCond = props.module === 'app'
        ? { type: 'element_exist', locator: { by: 'resource_id', value: '', index: 1 }, operator: 'is_true' }
        : { type: 'element_visible', locator: '', operator: 'is_true' }
      stepData.branches = [
        {
          id: `branch_${Date.now()}`,
          name: '分支1',
          condition: defaultCond,
          steps: [],
        },
        {
          id: `else_branch_${Date.now()}`,
          name: '默认分支',
          condition: { type: 'else' },
          steps: [],
        },
      ]
    }
    const baseParams = props.module === 'app'
      ? { ...newStep.params }
      : repairWebStepParams(newStep.params)
    const normalizedParams = (() => {
      if (props.module === 'app') return baseParams
      let webParams = baseParams
      if (stepData.method === 'scroll_to_height') webParams = normalizeScrollToHeightParams(webParams)
      else if (stepData.method === 'mouse_wheel') webParams = normalizeMouseWheelParams(webParams)
      return ensureWebIndexDefaults(stepData.method, webParams)
    })()
    form.value = {
      ...stepData,
      params: normalizedParams,
      config: {
        timeout: 30000,
        retry: false,
        pre_wait_ms: 0,
        timeout_explicit: false,
        ...newStep.config,
        pre_wait_ms: newStep.config?.pre_wait_ms ?? newStep.pre_wait_ms ?? 0,
      },
      // 必须用 stepData.branches（可能刚补了默认值），不能回读 newStep.branches
      branches: stepData.branches ? JSON.parse(JSON.stringify(stepData.branches)) : undefined,
    }
    // 历史 params.timeout：同步到 config.timeout；非模板默认值视为用户手工超时
    if (!isAppStep.value) {
      const pt = form.value.params?.timeout
      const n = parseInt(pt, 10)
      if (Number.isFinite(n) && n > 0) {
        form.value.config.timeout = n
        if (n !== 20000 && n !== 30000) {
          form.value.config.timeout_explicit = true
        }
      }
    }
    if (isAppStep.value && isAppMethod(form.value.method)) {
      form.value.params = applyDefaultAppIdToStepParams(
        form.value.method,
        form.value.params || {},
        proStore.projectInfo,
        props.allSteps || []
      )
      if (form.value.params?.locator) {
        form.value.params.locator = prepareAppLocatorForEdit(form.value.params.locator)
      }
    }
  }
}, { immediate: true, deep: true })

watch(
  () => (form.value.method === 'mouse_wheel' ? form.value.params?.direction : null),
  (dir, prev) => {
    if (!dir || dir === prev || form.value.method !== 'mouse_wheel') return
    form.value.params = normalizeMouseWheelParams(form.value.params || {})
  },
)

watch(() => props.visible, (open) => {
  if (open && !varInsertEnvId.value && proStore.envList.length) {
    varInsertEnvId.value = proStore.envList[0].id
  }
  if (open) {
    const p = form.value.params || {}
    showAdvanced.value = !!(
      p.wait_download || p.accept_dialog || p.dismiss_dialog
      || String(p.ready_selector || '').trim() || p.use_env_ready
      || String(p.expected_selector || '').trim() || p.wait_busy_after
    )
  }
  if (open && isAppStep.value) {
    loadAppElementOptions().then(() => {
      if (form.value.params?.locator_ref) {
        syncLocatorFromElementRef(form.value.params.locator_ref)
      }
    })
    const loc = form.value.params?.locator
    if (isImageLocator(loc) && loc?.value) {
      hydrateStepTemplatePreview(loc.value)
    }
    if (isAppMethod(form.value.method)) {
      form.value.params = applyDefaultAppIdToStepParams(
        form.value.method,
        form.value.params || {},
        proStore.projectInfo,
        props.allSteps || []
      )
    }
  }
})

// 监听 visible 变化
const visible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
})

function isFillValueParam(key) {
  return key === 'value' && FILL_VALUE_INPUT_METHODS.has(form.value.method) && !isAppStep.value
}

// 判断是否为长文本key
function isLongTextKey(key) {
  return longTextKeys.includes(key)
}

// 判断是否为长文本
function isLongText(value) {
  if (typeof value !== 'string') return false
  return value.length > 50 || value.includes('\n')
}

// 判断是否为数字
function isNumber(value) {
  return typeof value === 'number'
}

/** 索引/计数/超时等短数字，避免拉满整行 */
function compactNumberWidth(key) {
  const tiny = new Set([
    'index', 'first_index', 'second_index', 'source_index', 'target_index',
    'count', 'length', 'min_length', 'max_length',
    'amount', 'cursor_x', 'cursor_y',
  ])
  if (tiny.has(key)) return '120px'
  if (key === 'min_score' || key === 'min_margin') return '140px'
  return '168px'
}

// 判断是否为下拉选择
function isSelect(key) {
  if (isAppStep.value) {
    return ['direction', 'key'].includes(key)
  }
  if (key === 'position' && form.value.method === 'scroll_to_height') return true
  if (key === 'direction' && form.value.method === 'mouse_wheel') return true
  if (key === 'target_role' && isSmartActionStep.value) return true
  // 「key」仅键盘按键步骤是下拉；LocalStorage 的键名必须是文本输入
  if (key === 'key') {
    return form.value.method === 'press_key'
  }
  const selectKeys = ['wait_until', 'browser_type', 'operator', 'button', 'match_mode', 'order', 'post_wait_state']
  return selectKeys.includes(key)
}

// 是否为定位表达式参数（使用 LocatorSelector 组件）
function isAppLocatorRefKey(key) {
  return isAppStep.value && key === 'locator_ref'
}

function formatElementLocator(locator) {
  if (!locator || typeof locator !== 'object') return ''
  return `${locator.by || ''}=${locator.value || ''}`
}

async function loadAppElementOptions() {
  if (!isAppStep.value || !proStore.projectInfo?.id) {
    appElementOptions.value = []
    return
  }
  try {
    const res = await appElementApi.options({ project_id: proStore.projectInfo.id })
    appElementOptions.value = res.data?.data || res.data || []
  } catch {
    appElementOptions.value = []
  }
}

function appLocatorByOptions(key) {
  return getAppLocatorByOptions(form.value.params?.[key])
}

function onAppLocatorContextChange(key) {
  const loc = form.value.params?.[key]
  if (!loc) return
  if (loc.context === 'webview' && !['css', 'xpath', 'text', 'id'].includes(loc.by)) {
    loc.by = 'css'
  }
  if (loc.context === APP_LOCATOR_CONTEXT_NATIVE && ['css', 'id'].includes(loc.by)) {
    loc.by = 'resource_id'
  }
  onAppLocatorFieldEdited()
}

function onAppLocatorByChange(key) {
  const loc = form.value.params?.[key]
  if (!loc) return
  if (loc.by === 'image') {
    loc.value = loc.value || ''
    loc.threshold = loc.threshold ?? 0.8
    loc.rgb = loc.rgb ?? false
    delete loc.index
    delete loc.context
    hydrateStepTemplatePreview(loc.value)
  } else {
    delete loc.threshold
    delete loc.rgb
    delete loc.record_pos
    delete loc.resolution
    if (String(loc.value || '').startsWith('app-elements/')) {
      loc.value = ''
    }
    if (!loc.context) {
      loc.context = APP_LOCATOR_CONTEXT_NATIVE
    }
    if (loc.by === 'resource_id' && !loc.index) {
      loc.index = 1
    }
  }
  onAppLocatorFieldEdited()
}

function onAppLocatorFieldEdited() {
  if (form.value.params?.locator_ref) {
    form.value.params.locator_ref = ''
  }
}

function syncLocatorFromElementRef(refName) {
  const loc = form.value.params?.locator
  if (!loc || !refName) return
  const found = appElementOptions.value.find((opt) => opt.name === refName)
  if (!found?.locator) return
  const synced = prepareAppLocatorForEdit(JSON.parse(JSON.stringify(found.locator)))
  Object.assign(loc, synced)
  if (isImageLocator(synced) && synced.value) {
    hydrateStepTemplatePreview(synced.value)
  }
}

function onLocatorRefChange(val) {
  if (!val) return
  syncLocatorFromElementRef(val)
}

function formatLocatorPair(value) {
  if (value == null || value === '') return ''
  if (Array.isArray(value) && value.length >= 2) return `${value[0]},${value[1]}`
  if (typeof value === 'object' && value.x != null && value.y != null) return `${value.x},${value.y}`
  return String(value)
}

function setLocatorPair(loc, field, text) {
  if (!loc) return
  const parts = String(text || '').split(',').map((s) => s.trim()).filter(Boolean)
  if (parts.length >= 2) {
    const a = Number(parts[0])
    const b = Number(parts[1])
    if (!Number.isNaN(a) && !Number.isNaN(b)) loc[field] = [a, b]
  } else {
    delete loc[field]
  }
}

async function hydrateStepTemplatePreview(objectKey) {
  if (!objectKey || String(objectKey).startsWith('http')) return
  const urlMap = await presignTemplateKeys([objectKey], projectId.value)
  stepTemplatePreviewMap.value = { ...stepTemplatePreviewMap.value, ...urlMap }
}

function stepTemplatePreviewSrc(key) {
  const value = form.value.params?.[key]?.value
  return resolveTemplatePreviewUrl(value, stepTemplatePreviewMap.value)
}

async function handleStepTemplateUpload(options, key) {
  const file = options.file
  if (!file || !projectId.value) return
  stepTemplateUploading.value = true
  try {
    const res = await appElementApi.uploadTemplate(projectId.value, file)
    const data = res.data?.data || res.data
    const objectKey = data?.object_key || ''
    const accessUrl = data?.access_url || ''
    if (!objectKey) {
      ElMessage.error('上传失败')
      return
    }
    const loc = form.value.params?.[key]
    if (loc) {
      loc.by = 'image'
      loc.value = objectKey
      loc.threshold = loc.threshold ?? 0.8
      loc.rgb = loc.rgb ?? false
    }
    if (accessUrl) {
      stepTemplatePreviewMap.value = { ...stepTemplatePreviewMap.value, [objectKey]: accessUrl }
    }
    ElMessage.success('识别图已上传')
  } catch (e) {
    ElMessage.error('识别图上传失败')
  } finally {
    stepTemplateUploading.value = false
  }
}

const webVisionPreviewSrc = computed(() => {
  const key = form.value.params?.template
  return resolveTemplatePreviewUrl(key, stepTemplatePreviewMap.value)
})

async function handleWebVisionTemplateUpload(options) {
  const file = options.file
  if (!file || !projectId.value) return
  stepTemplateUploading.value = true
  try {
    const res = await appElementApi.uploadTemplate(projectId.value, file)
    const data = res.data?.data || res.data
    const objectKey = data?.object_key || ''
    const accessUrl = data?.access_url || ''
    if (!objectKey) {
      ElMessage.error('上传失败')
      return
    }
    if (!form.value.params) form.value.params = {}
    form.value.params.template = objectKey
    form.value.params.threshold = form.value.params.threshold ?? 0.8
    if (accessUrl) {
      stepTemplatePreviewMap.value = { ...stepTemplatePreviewMap.value, [objectKey]: accessUrl }
    } else {
      await hydrateStepTemplatePreview(objectKey)
    }
    ElMessage.success('模板图已上传')
  } catch (e) {
    ElMessage.error('模板图上传失败')
  } finally {
    stepTemplateUploading.value = false
  }
}

import { setAppInspectorContext, setAppInspectorCaseDraft } from '@/utils/appInspectorContext.js'

function openAppInspector() {
  if (!isAppStep.value) {
    router.push({ name: 'appInspector' })
    return
  }
  if (typeof saveAppInspectorDraft === 'function') {
    saveAppInspectorDraft()
  }
  setAppInspectorContext({
    returnPath: route.fullPath,
    returnName: route.name,
    stepPath: effectiveStepPath.value,
    stepIndex: effectiveStepPath.value[effectiveStepPath.value.length - 1],
    driverMode: props.driverMode || 'hybrid',
    caseId: route.params.id || null,
    projectId: proStore.projectInfo?.id || null,
  })
  router.push({ name: 'appInspector', query: { from: 'step_edit' } })
}

function isAppObjectLocator(key) {
  if (!isAppStep.value) return false
  const val = form.value.params?.[key]
  return key === 'locator' && val && typeof val === 'object' && val.by !== undefined
}

function isLocatorKey(key) {
  if (isAppObjectLocator(key)) return false
  return ['locator', 'selector', 'first_locator', 'second_locator'].includes(key)
}

function canInsertVar(key) {
  return !isLocatorKey(key) && !isNumber(form.value.params?.[key]) && !isBoolean(key) && !isSelect(key)
}

async function handleHealLocator() {
  if (isAppStep.value) {
    return handleAppHealLocator()
  }
  const locatorKey = Object.keys(form.value.params || {}).find(k => isLocatorKey(k))
  if (!locatorKey) {
    ElMessage.warning('当前步骤无定位器参数')
    return
  }
  const failed = (form.value.params[locatorKey] || '').trim()
  if (!failed) {
    ElMessage.warning('请先填写失败的定位器')
    return
  }
  healReplayThrough.value = Math.max(1, props.stepIndex)
  healMode.value = canReplay.value ? 'replay' : 'url'
  healDialogVisible.value = true
}

async function handleAppHealLocator() {
  const locator = form.value.params?.locator
  if (!locator || !isAppLocatorFilled(locator)) {
    ElMessage.warning('请先填写定位器')
    return
  }
  if (isImageLocator(locator)) {
    ElMessage.warning('图像识别定位暂不支持 AI 自愈')
    return
  }
  healingLocator.value = true
  try {
    const res = await aiGenerateApi.healAppLocator({
      method: form.value.method,
      failed_locator: serializeAppLocatorForSave(locator),
      step_desc: form.value.desc,
      step_intent: form.value.intent || undefined,
    })
    if (res.data?.code === 200 && res.data.data?.locator) {
      form.value.params.locator = prepareAppLocatorForEdit(res.data.data.locator)
      ElMessage.success(`已应用新定位器（${res.data.data.confidence || 'medium'}）`)
    } else {
      ElMessage.error(res.data?.data?.reason || res.data?.message || '自愈失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '自愈请求失败')
  } finally {
    healingLocator.value = false
  }
}

async function confirmHeal() {
  const locatorKey = Object.keys(form.value.params || {}).find(k => isLocatorKey(k))
  const failed = (form.value.params[locatorKey] || '').trim()
  const payload = {
    method: form.value.method,
    failed_locator: failed,
    step_desc: form.value.desc,
    step_intent: form.value.intent || undefined,
  }

  if (healMode.value === 'replay' && canReplay.value) {
    payload.replay_steps = props.allSteps
    payload.replay_through_index = healReplayThrough.value
    if (healPageUrl.value.trim()) {
      payload.page_url = healPageUrl.value.trim()
    }
  } else {
    if (!healPageUrl.value.trim()) {
      ElMessage.warning('请填写页面 URL')
      return
    }
    payload.page_url = healPageUrl.value.trim()
  }

  healingLocator.value = true
  try {
    const res = await aiGenerateApi.healLocator(payload)
    if (res.data?.code === 200 && res.data.data?.locator) {
      form.value.params[locatorKey] = res.data.data.locator
      ElMessage.success(`已应用新定位器（${res.data.data.confidence || 'medium'}）`)
      healDialogVisible.value = false
    } else {
      ElMessage.error(res.data?.data?.reason || res.data?.message || '自愈失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '自愈请求失败')
  } finally {
    healingLocator.value = false
  }
}

// 判断是否为布尔值
function isBoolean(key) {
  if (form.value.method === 'fill_by_image' && key === 'clear_first') return true
  const booleanKeys = [
    'force', 'wait_download', 'exact', 'accept_dialog', 'dismiss_dialog',
    'use_regex', 'wait_busy_after', 'use_env_ready', 'allow_ai',
  ]
  return booleanKeys.includes(key)
}

// 获取选项
function getOptions(key) {
  if (isAppStep.value) {
    return getAppSelectOptions(key)
  }
  if (key === 'direction' && form.value.method === 'mouse_wheel') {
    return [
      { label: '向下滚', value: 'down' },
      { label: '向上滚', value: 'up' },
      { label: '向左滚', value: 'left' },
      { label: '向右滚', value: 'right' },
      { label: '自定义 ΔX / ΔY', value: 'custom' },
    ]
  }
  if (key === 'target_role') {
    return [
      { label: 'button', value: 'button' },
      { label: 'link', value: 'link' },
      { label: 'textbox', value: 'textbox' },
      { label: 'checkbox', value: 'checkbox' },
      { label: 'radio', value: 'radio' },
      { label: 'menuitem', value: 'menuitem' },
      { label: 'tab', value: 'tab' },
      { label: 'option', value: 'option' },
    ]
  }
  const options = {
    wait_until: [
      { label: 'DOM就绪', value: 'domcontentloaded' },
      { label: '页面加载完成', value: 'load' },
      { label: '网络空闲', value: 'networkidle' }
    ],
    browser_type: [
      { label: 'Chrome', value: 'chromium' },
      { label: 'Firefox', value: 'firefox' },
      { label: 'Safari', value: 'webkit' }
    ],
    operator: [
      { label: '等于', value: 'eq' },
      { label: '包含', value: 'contains' },
      { label: '大于', value: 'gt' },
      { label: '小于', value: 'lt' }
    ],
    key: [
      { label: 'Enter', value: 'Enter' },
      { label: 'Tab', value: 'Tab' },
      { label: 'Escape', value: 'Escape' },
      { label: 'Backspace', value: 'Backspace' },
      { label: 'ArrowUp', value: 'ArrowUp' },
      { label: 'ArrowDown', value: 'ArrowDown' },
      { label: 'ArrowLeft', value: 'ArrowLeft' },
      { label: 'ArrowRight', value: 'ArrowRight' }
    ],
    button: [
      { label: '左键', value: 'left' },
      { label: '右键', value: 'right' },
      { label: '中键', value: 'middle' }
    ],
    match_mode: [
      { label: '完全相等', value: 'exact' },
      { label: '包含', value: 'contains' }
    ],
    order: [
      { label: '前面（第一个在第二个之前）', value: 'before' },
      { label: '后面（第一个在第二个之后）', value: 'after' }
    ],
    post_wait_state: [
      { label: '先消失再出现 (reappear，推荐)', value: 'reappear' },
      { label: '等待出现 (visible，易抢跑)', value: 'visible' },
      { label: '等待消失 (hidden)', value: 'hidden' },
    ],
    position: [
      { label: '指定高度（距顶部像素）', value: 'height' },
      { label: '滚到顶部', value: 'top' },
      { label: '滚到中间', value: 'middle' },
      { label: '滚到底部', value: 'bottom' },
      { label: '相对向下滚', value: 'down' },
      { label: '相对向上滚', value: 'up' },
    ]
  }
  return options[key] || []
}

// 保存 - 带校验
async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    ElMessage.warning('请填写必填项')
    return
  }
  
  // 条件分支不需要校验参数
  if (isDbAssertStep.value) {
    if (!form.value.params?.sql?.trim()) {
      ElMessage.warning('请填写 SQL/Redis 命令')
      return
    }
  } else if (!isConditionBranch.value) {
    if (isUploadFileStep.value) {
      const p = form.value.params || {}
      const mode = (p.upload_mode || 'single').toLowerCase()
      if (mode === 'folder') {
        const hasPlatformFolder = !!(p.folder_key && p.folder_bucket)
        const hasLegacyPath = !!(p.file_path && String(p.file_path).trim())
        if (!hasPlatformFolder && !hasLegacyPath) {
          ElMessage.warning('请选择测试文件夹，或填写 Runner 本地路径')
          return
        }
      } else if (mode === 'multiple') {
        const items = Array.isArray(p.file_items) ? p.file_items : []
        const hasItems = items.some((it) => it?.file_key && it?.file_bucket)
        if (!hasItems) {
          ElMessage.warning('请至少选择一个测试文件')
          return
        }
      } else {
        const hasPlatformFile = !!(p.file_key && p.file_bucket)
        const hasLegacyPath = !!(p.file_path && String(p.file_path).trim())
        if (!hasPlatformFile && !hasLegacyPath) {
          ElMessage.warning('请选择测试文件，或填写 Runner 本地路径')
          return
        }
      }
    }
    // App / Web 步骤参数校验
    if (isAppStep.value) {
      const appErr = validateAppStepParams(form.value.method, form.value.params)
      if (appErr) {
        ElMessage.warning(appErr)
        return
      }
    } else {
      for (const key of Object.keys(filteredParams.value)) {
        if (isRequiredParam(key)) {
          const value = form.value.params[key]
          if (isFillValueParam(key)) {
            if (value == null || value === '') {
              ElMessage.warning(`请填写${resolveParamLabel(key)}`)
              return
            }
            continue
          }
          if (!value || (typeof value === 'string' && value.trim() === '')) {
            ElMessage.warning(`请填写${resolveParamLabel(key)}`)
            return
          }
        }
      }
    }
  }

  if (isConditionBranch.value && isAppStep.value) {
    const branchErr = validateAppBranchConditions(form.value.branches)
    if (branchErr) {
      ElMessage.warning(branchErr)
      return
    }
  }
  
  // 构建保存的步骤数据
  let saveParams = { ...(form.value.params || {}) }
  if (!isAppStep.value && form.value.method === 'scroll_to_height') {
    saveParams = normalizeScrollToHeightParams(saveParams)
  }
  if (!isAppStep.value && form.value.method === 'mouse_wheel') {
    saveParams = normalizeMouseWheelParams(saveParams)
    if (Number(saveParams.x || 0) === 0 && Number(saveParams.y || 0) === 0) {
      ElMessage.warning('请设置滚动量（方向距离或自定义 ΔX/ΔY）')
      return
    }
  }
  const keepTimeoutMethods = ['wait_for_time', 'set_default_timeout']
  if (!isAppStep.value && !keepTimeoutMethods.includes(form.value.method)) {
    const pt = saveParams.timeout
    if (pt != null && String(pt).trim() !== '') {
      const n = parseInt(pt, 10)
      // 迁移 params.timeout → config.timeout；模板默认 20s/30s 不标 explicit，仍吃环境倍率
      if (Number.isFinite(n) && n > 0) {
        if (!form.value.config || typeof form.value.config !== 'object') {
          form.value.config = {
            timeout: n,
            retry: false,
            pre_wait_ms: 0,
            timeout_explicit: n !== 20000 && n !== 30000,
          }
        } else {
          form.value.config.timeout = n
          if (n !== 20000 && n !== 30000) {
            form.value.config.timeout_explicit = true
          }
        }
      }
    }
    delete saveParams.timeout
  }
  const savedStep = { 
    ...form.value,
    keyword: form.value.keyword,
    method: form.value.method || form.value.keyword,
    params: saveParams,
  }
  delete savedStep.pre_wait_ms
  if (savedStep.config && typeof savedStep.config === 'object') {
    const rawWait = savedStep.config.pre_wait_ms
    const parsed = parseInt(rawWait, 10)
    savedStep.config.pre_wait_ms = Number.isFinite(parsed)
      ? Math.max(0, Math.min(600_000, parsed))
      : 0
  }
  const intent = (savedStep.intent || '').trim()
  if (intent) {
    savedStep.intent = intent
  } else {
    delete savedStep.intent
  }
  if (isAppStep.value) {
    if (savedStep.params?.locator) {
      savedStep.params.locator = serializeAppLocatorForSave(savedStep.params.locator)
    }
    if (!savedStep.params?.locator_ref) {
      delete savedStep.params.locator_ref
    }
  }
  
  // 条件分支特殊处理
  if (isConditionBranch.value) {
    savedStep.is_container = true
    // 确保branches字段存在
    if (!savedStep.branches || savedStep.branches.length === 0) {
      const defaultCond = isAppStep.value
        ? { type: 'element_exist', locator: { by: 'resource_id', value: '', index: 1 }, operator: 'is_true' }
        : { type: 'element_visible', locator: '', operator: 'is_true' }
      savedStep.branches = [
        {
          id: `branch_${Date.now()}`,
          name: '分支1',
          condition: defaultCond,
          steps: [],
        },
        {
          id: `else_branch_${Date.now()}`,
          name: '默认分支',
          condition: { type: 'else' },
          steps: [],
        },
      ]
    }
  }

  if (savedStep.method === 'smart_step') {
    const intentRaw = (savedStep.params?.intent || '').trim()
    if (!intentRaw) {
      ElMessage.warning('请填写步骤意图')
      return
    }
    const intents = splitSmartStepIntents(intentRaw)
    if (intents.length === 0) {
      ElMessage.warning('请填写步骤意图')
      return
    }
    if (intents.length > 1) {
      const steps = intents.map((intent, index) => {
        const desc = intent.length > 40 ? `${intent.slice(0, 40)}...` : intent
        return {
          ...savedStep,
          id: index === 0 ? (savedStep.id || generateStepId()) : generateStepId(),
          desc,
          params: { ...(savedStep.params || {}), intent },
        }
      })
      emit('save-multiple', steps)
      return
    }
    if (intents.length === 1) {
      savedStep.params = { ...(savedStep.params || {}), intent: intents[0] }
      if (!savedStep.desc || savedStep.desc === '智能步骤') {
        const intent = intents[0]
        savedStep.desc = intent.length > 40 ? `${intent.slice(0, 40)}...` : intent
      }
    }
  }
  
  emit('save', savedStep)
}

// 取消
function handleCancel() {
  emit('cancel')
}

// 关闭
function handleClose() {
  form.value = {
    id: '',
    keyword: '',
    desc: '',
    intent: '',
    method: '',
    params: {},
    config: { timeout: 30000, retry: false, pre_wait_ms: 0, timeout_explicit: false }
  }
  showAdvanced.value = false
  smartTuningOpen.value = []
}
</script>

<style scoped lang="scss">
.params-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
}

.params-section-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.ui-step-usage-guide-standalone {
  display: inline-flex;
  margin: 0 0 8px 100px;
}

.smart-convert-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 4px;
  padding: 8px 12px;
  background: var(--el-fill-color-blank);
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
}
.smart-convert-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}

.params-container.is-smart-action {
  gap: 12px;

  > .param-item {
    padding: 10px 12px;
    border-radius: 8px;
    background: var(--el-fill-color-blank);
    border: 1px solid var(--el-border-color-extra-light);
  }

  > .param-item .param-label {
    margin-bottom: 8px;
    font-weight: 500;
    color: var(--el-text-color-regular);
  }
}

.smart-tuning-params {
  margin-top: 2px;
  border: none;

  :deep(.el-collapse-item__header) {
    height: auto;
    min-height: 36px;
    line-height: 1.4;
    padding: 6px 2px;
    background: transparent;
    border-bottom: 1px dashed var(--el-border-color-lighter);
    font-size: 13px;
  }

  :deep(.el-collapse-item__wrap) {
    border-bottom: none;
    background: transparent;
  }

  :deep(.el-collapse-item__content) {
    padding: 10px 0 2px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
}

.smart-tuning-title {
  font-weight: 600;
  color: var(--el-text-color-regular);
  margin-right: 8px;
}

.smart-tuning-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

.drag-position-hint {
  margin-bottom: 4px;

  p {
    margin: 0 0 6px;
    font-size: 13px;
    line-height: 1.55;
    color: var(--el-text-color-regular);
  }

  .drag-position-example {
    margin-bottom: 0;
    font-size: 12px;
    color: var(--el-text-color-secondary);

    code {
      padding: 0 4px;
      border-radius: 3px;
      background: var(--el-fill-color);
      font-size: 12px;
    }
  }
}

.param-item {
  width: 100%;
  
  .param-label {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 13px;
    color: var(--el-text-color-secondary);
    margin-bottom: 6px;
    
    .required-mark {
      color: var(--el-color-danger);
    }

    .param-tip-icon {
      font-size: 14px;
      color: var(--el-color-primary);
      cursor: help;
      vertical-align: middle;
    }
  }
  
  :deep(.el-input__wrapper),
  :deep(.el-textarea__inner) {
    width: 100%;
  }
}

// 高级配置
.advanced-form-item {
  margin-bottom: 8px;

  :deep(.el-form-item__content) {
    margin-left: 0 !important;
    width: 100%;
  }
}

.condition-branch-form-item {
  :deep(.el-form-item__content) {
    width: 100%;
    max-width: 100%;
  }

  :deep(.condition-edit) {
    width: 100%;
  }
}

.advanced-panel {
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-bg-color);
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.advanced-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 0;
  background: linear-gradient(180deg, var(--el-fill-color-blank) 0%, var(--el-fill-color-light) 100%);
  cursor: pointer;
  text-align: left;
  transition: background 0.2s;

  &:hover {
    background: var(--el-fill-color-light);
  }
}

.advanced-toggle-main {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.advanced-toggle-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.advanced-toggle-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.advanced-arrow {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  transition: transform 0.25s;
  flex-shrink: 0;

  &.is-open {
    transform: rotate(180deg);
  }
}

.advanced-body {
  padding: 0 14px 14px;
  border-top: 1px solid var(--el-border-color-extra-light);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.advanced-section {
  padding-top: 12px;
}

.advanced-section-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;

  h4 {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    color: var(--el-text-color-regular);
  }
}

.advanced-section-desc {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--el-text-color-secondary);
}

.advanced-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px 16px;
}

.advanced-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.advanced-field-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.advanced-field-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.advanced-unit {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.advanced-params {
  gap: 12px;
}

.app-locator-row {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.app-image-locator {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.app-image-fields {
  display: flex;
  align-items: center;
  gap: 12px;
}

.app-image-fields .field-label {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

.step-template-path {
  font-size: 12px;
  color: #909399;
  word-break: break-all;
}

.web-vision-template {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.web-vision-template-input {
  max-width: 520px;
}
.web-vision-threshold {
  display: flex;
  align-items: center;
  gap: 12px;
}
.step-template-preview {
  width: 72px;
  height: 72px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
}

.locator-ref-row {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.locator-heal-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  :deep(.locator-selector) {
    flex: 1;
  }
}

.param-input-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
}

.heal-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.step-intent-hint {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.step-insert-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 8px;
  width: 100%;
  overflow-x: auto;
}

.step-insert-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
</style>

<style lang="scss">
.param-tip-popper {
  max-width: 420px;

  .param-tip-content {
    font-size: 13px;
    line-height: 1.55;
    white-space: pre-line;
  }
}
</style>
