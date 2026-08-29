<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    width="1100px"
    destroy-on-close
    @closed="handleClosed"
    class="case-edit-dialog"
  >
    <template #header>
      <div class="dialog-header">
        <span>{{ isEdit ? '编辑测试用例' : '新建测试用例' }}</span>
        <LinkFunctionalCaseButton
          v-if="isEdit && props.data?.id"
          asset-type="api_case"
          :asset-id="props.data.id"
          size="small"
        />
        <el-tooltip placement="bottom" :show-after="300" :hide-after="0">
          <template #content>
            <div class="help-content">
              <p class="help-title">📝 测试用例使用指南</p>
              <p class="help-section">测试用例用于验证接口返回是否符合预期，主要包含三部分：</p>
              <p class="help-section"><b>1. 请求覆盖</b> - 覆盖接口定义的请求参数，实现不同场景</p>
              <p class="help-item">• 请求头覆盖：修改/新增 Header，如去掉 Authorization 测试鉴权失败</p>
              <p class="help-item">• 请求参数覆盖：修改 Query/Path 参数值，测试边界值场景</p>
              <p class="help-item">• 请求体覆盖：支持 JSON / form-data / x-www-form-urlencoded / XML / Raw</p>
              <p class="help-item">• form-data 文件字段：本地选文件后会自动上传到 MinIO，仅保存引用信息</p>
              <p class="help-section"><b>2. 断言规则</b> - 验证接口返回结果</p>
              <p class="help-item">• 状态：检查 HTTP 状态码</p>
              <p class="help-item">• 响应体：JSON 路径 / 全文包含 / 全文不包含（JSON 路径可点右侧图标对照示例取值）</p>
              <p class="help-item">• 响应头：按 Header 名称取值后再比较</p>
              <p class="help-section"><b>3. 变量提取</b> - 从响应体或响应头提取数据</p>
              <p class="help-item">• 将登录接口返回的 token 提取出来</p>
              <p class="help-item">• 在后续接口的 Headers 中使用 <code v-pre>${{变量名}}</code> 引用</p>
              <p class="help-example">💡 示例：登录接口提取 token → 其他接口使用 <code v-pre>Authorization: Bearer ${{token}}</code></p>
            </div>
          </template>
          <el-icon class="help-icon"><QuestionFilled /></el-icon>
        </el-tooltip>
      </div>
    </template>
    <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="用例名称" prop="name">
            <el-input v-model="form.name" placeholder="请输入用例名称"/>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="关联接口" prop="api_id">
            <el-select 
              v-model="form.api_id" 
              placeholder="搜索或选择接口" 
              style="width: 100%;"
              filterable
              remote
              :remote-method="filterApis"
              :loading="apiLoading"
            >
              <el-option
                v-for="api in filteredApis"
                :key="api.id"
                :label="`${api.name} (${api.method} ${api.path})`"
                :value="api.id"
              >
                <div class="api-option">
                  <div class="api-option-name">{{ api.name }}</div>
                  <div class="api-option-path">
                    <el-tag :type="getMethodType(api.method)" size="small">{{ api.method }}</el-tag>
                    <span>{{ api.path }}</span>
                  </div>
                </div>
              </el-option>
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      
      <el-row :gutter="20">
        <el-col :span="8">
          <el-form-item label="优先级">
            <el-select v-model="form.priority">
              <el-option label="P0 - 核心" value="P0"/>
              <el-option label="P1 - 高" value="P1"/>
              <el-option label="P2 - 中" value="P2"/>
              <el-option label="P3 - 低" value="P3"/>
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="超时时间">
            <el-input-number v-model="form.timeout" :min="1" :max="300" style="width: 100%;">
              <template #suffix>秒</template>
            </el-input-number>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="重试次数">
            <el-input-number v-model="form.retry_count" :min="0" :max="5" style="width: 100%;"/>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="20">
        <el-col :span="16">
          <el-form-item label="业务标签">
            <el-select
              v-model="form.tags"
              multiple
              filterable
              allow-create
              default-first-option
              collapse-tags
              collapse-tags-tooltip
              placeholder="输入或选择标签，如 压测 / 业务链路"
              style="width: 100%;"
            >
              <el-option
                v-for="t in tagSuggestions"
                :key="t.value"
                :label="t.label"
                :value="t.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="所属目录">
            <el-tree-select
              v-model="form.catalog_id"
              :data="catalogTree"
              :props="{ label: 'name', value: 'id', children: 'children' }"
              placeholder="选择目录"
              style="width: 100%;"
              clearable
            />
          </el-form-item>
        </el-col>
      </el-row>

      <ApiCaseUsedVarsPanel :case-form="form" />

      <div class="var-toolbar">
        <div class="var-toolbar-actions">
          <el-select
            v-model="refEnvId"
            placeholder="参考环境"
            clearable
            size="small"
            style="width: 160px"
          >
            <el-option
              v-for="env in proStore.envList"
              :key="env.id"
              :label="env.name"
              :value="env.id"
            />
          </el-select>
          <VarInsertButton
            :env-id="refEnvId"
            :extra-vars="extractorVarNames"
            hint-text="不含工厂标签；标签与内联工具请用右侧按钮。"
          />
          <ToolInsertButton :env-id="refEnvId" :extra-vars="extractorVarNames" />
          <el-button type="info" link size="small" @click="tagPickerVisible = true">数据工厂标签</el-button>
        </div>
        <span class="var-toolbar-hint">先点击下方输入框再插入；变量 <code v-pre>${{名}}</code> / 标签 <code v-pre>${{df:标签}}</code> / 工具 <code v-pre>${{dt:md5|text=@a}}</code></span>
      </div>

      <!-- 请求配置覆盖 -->
      <el-collapse v-model="activeCollapse" class="request-config-collapse">
        <el-collapse-item name="headers">
          <template #title>
            <span class="collapse-title">
              请求头覆盖
              <el-tooltip placement="top" :show-after="300">
                <template #content>
                  <div class="help-popover">
                    <p><b>请求头覆盖</b>用于在用例级别修改请求头</p>
                    <p class="mt-5"><b>典型场景：</b></p>
                    <p>• 去掉 Authorization 测试鉴权失败场景</p>
                    <p>• 修改 Content-Type 测试不同格式</p>
                    <p class="mt-5"><b>规则：</b>用例 Header 会覆盖接口定义的同名 Header</p>
                  </div>
                </template>
                <el-icon class="section-help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
              <el-tag v-if="form.request_headers.length > 0" type="warning" size="small" class="count-tag">{{ form.request_headers.length }}</el-tag>
            </span>
          </template>
          <HeaderEditorPanel
            v-model="form.request_headers"
            local-title="用例 Header 覆盖"
            :show-description="false"
          >
            <template #toolbar-extra>
              <el-button type="info" link size="small" @click="copyApiHeaders" :disabled="!form.api_id" icon="CopyDocument">从接口复制</el-button>
            </template>
          </HeaderEditorPanel>
          <el-empty v-if="form.request_headers.length === 0" :image-size="40" description="暂无覆盖的 Header；为空时使用接口定义的全部 Header。一旦添加/复制了覆盖项，将整表以本列表为准（在此删除的字段不会再从接口补回）"/>
        </el-collapse-item>

        <el-collapse-item name="params">
          <template #title>
            <div class="collapse-header-row">
              <span class="collapse-title">
                请求参数覆盖
                <el-tooltip placement="top" :show-after="300">
                  <template #content>
                    <div class="help-popover">
                      <p><b>请求参数覆盖</b>用于在用例级别修改请求参数</p>
                      <p class="mt-5"><b>典型场景：</b></p>
                      <p>• 修改 pageSize 为超大值测试分页边界</p>
                      <p>• 传入非法字符测试参数校验</p>
                      <p class="mt-5"><b>规则：</b>用例参数会完全覆盖接口定义的参数（非按 key 合并）</p>
                      <p>• 与 Header 不同：这里是 Query/Path 参数，不是 JSON 请求体</p>
                    </div>
                  </template>
                  <el-icon class="section-help-icon" @click.stop><QuestionFilled /></el-icon>
                </el-tooltip>
                <el-tag v-if="form.request_params.length > 0" type="warning" size="small" class="count-tag">{{ form.request_params.length }}</el-tag>
              </span>
              <div class="section-actions" @click.stop>
                <el-button type="info" link size="small" @click="copyApiParams" :disabled="!form.api_id" icon="CopyDocument">从接口复制</el-button>
                <el-button type="info" link size="small" @click="tagPickerVisible = true" icon="Collection">数据工厂标签</el-button>
                <el-button type="primary" link size="small" @click="addParam" icon="Plus">添加</el-button>
              </div>
            </div>
          </template>
          <el-table :data="form.request_params" size="small" border class="config-table">
            <el-table-column label="参数名" width="180">
              <template #default="{ $index }">
                <el-input v-model="form.request_params[$index].name" size="small" placeholder="pageSize"/>
              </template>
            </el-table-column>
            <el-table-column label="参数值">
              <template #default="{ $index }">
                <el-input v-model="form.request_params[$index].value" size="small" placeholder="10000"/>
              </template>
            </el-table-column>
            <el-table-column label="类型" width="100">
              <template #default="{ $index }">
                <el-select v-model="form.request_params[$index].type" size="small" style="width: 100%">
                  <el-option label="string" value="string"/>
                  <el-option label="number" value="number"/>
                  <el-option label="boolean" value="boolean"/>
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="60">
              <template #default="{ $index }">
                <el-button type="danger" link size="small" @click="removeParam($index)" icon="Delete"/>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="form.request_params.length === 0" :image-size="40" description="暂无覆盖的参数，为空时使用接口定义的默认参数"/>
        </el-collapse-item>

        <el-collapse-item name="body" v-if="showBodySection">
          <template #title>
            <div class="collapse-header-row">
              <span class="collapse-title">
                请求体覆盖
                <el-tooltip placement="top" :show-after="300">
                  <template #content>
                    <div class="help-popover">
                      <p><b>请求体覆盖</b>用于在用例级别修改请求体（仅 POST/PUT/PATCH）</p>
                      <p class="mt-5"><b>支持类型：</b></p>
                      <p>• JSON / XML / Raw：继续使用文本方式编辑</p>
                      <p>• form-data：支持文本字段与文件字段</p>
                      <p>• 文件字段：本地选择后自动上传到 MinIO，仅保存 bucket/key 引用</p>
                      <p class="mt-5"><b>规则：</b>用例 Body 覆盖优先于接口默认 Body</p>
                      <p>• 为空时自动使用接口定义的 Body</p>
                    </div>
                  </template>
                  <el-icon class="section-help-icon" @click.stop><QuestionFilled /></el-icon>
                </el-tooltip>
                <el-tag v-if="form.request_body || form.request_body_fields.length" type="warning" size="small" class="count-tag">已覆盖</el-tag>
              </span>
              <div class="section-actions" @click.stop>
                <el-button type="info" link size="small" @click="copyApiBody" :disabled="!form.api_id" icon="CopyDocument">从接口复制</el-button>
                <el-button type="danger" link size="small" @click="clearBody" icon="Delete">清空</el-button>
              </div>
            </div>
          </template>
          <div class="body-mode-row">
            <el-radio-group v-model="form.request_body_type" size="small" class="body-mode-group">
              <el-radio-button label="json">JSON</el-radio-button>
              <el-radio-button label="form-data">Form Data</el-radio-button>
              <el-radio-button label="x-www-form-urlencoded">x-www-form-urlencoded</el-radio-button>
              <el-radio-button label="xml">XML</el-radio-button>
              <el-radio-button label="raw">Raw</el-radio-button>
            </el-radio-group>
          </div>

          <JsonTextarea
            v-if="form.request_body_type !== 'form-data'"
            v-model="form.request_body"
            :rows="8"
            :placeholder="bodyPlaceholder"
            input-class="body-textarea"
            :json-mode="form.request_body_type === 'json'"
            show-compact
          />
          <el-empty
            v-if="form.request_body_type !== 'form-data' && !(form.request_body || '').trim()"
            :image-size="40"
            description="暂无覆盖的请求体；为空时执行会使用接口定义的 Body。需要改内容时点「从接口复制」后再编辑"
          />

          <div v-else class="form-data-editor">
            <div class="section-actions compact-actions">
              <el-button type="primary" link size="small" @click="addBodyField" icon="Plus">添加字段</el-button>
              <el-button type="info" link size="small" @click="copyApiBody" :disabled="!form.api_id" icon="CopyDocument">从接口复制</el-button>
            </div>
            <el-table :data="form.request_body_fields" size="small" border class="config-table">
              <el-table-column label="字段名" width="180">
                <template #default="{ $index }">
                  <el-input v-model="form.request_body_fields[$index].name" size="small" placeholder="file" />
                </template>
              </el-table-column>
              <el-table-column label="类型" width="120">
                <template #default="{ $index }">
                  <el-select v-model="form.request_body_fields[$index].field_type" size="small" @change="onBodyFieldTypeChange($index)">
                    <el-option label="文本" value="text" />
                    <el-option label="文件" value="file" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="值 / 文件" min-width="280">
                <template #default="{ $index }">
                  <div class="file-field-cell">
                    <ApiTestFilePicker
                      v-if="form.request_body_fields[$index].field_type === 'file'"
                      :model-value="form.request_body_fields[$index]"
                      @update:model-value="(v) => onBodyFieldFileUpdate($index, v)"
                    />
                    <el-input v-else v-model="form.request_body_fields[$index].value" size="small" placeholder="文本值" />
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="MIME" width="180">
                <template #default="{ $index }">
                  <el-input v-model="form.request_body_fields[$index].mime_type" size="small" placeholder="application/octet-stream" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="70">
                <template #default="{ $index }">
                  <el-button type="danger" link size="small" @click="removeBodyField($index)">删</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="form.request_body_fields.length === 0" :image-size="40" description="暂无 form-data 字段" />
          </div>

          <div v-if="form.request_body_type !== 'form-data' && form.request_body" class="body-hint">
            <el-alert type="info" :closable="false" show-icon>
              <template #title>
                <span>此用例会覆盖接口定义的默认请求体</span>
              </template>
            </el-alert>
          </div>
        </el-collapse-item>
      </el-collapse>

      <div v-if="isWsApi" class="section-title"><span>WebSocket 步骤</span></div>
      <WsStepsEditor v-if="isWsApi" v-model="form.ws_steps" />
      
      <!-- 断言配置 -->
      <div class="section-title">
        <span>
          断言规则
          <el-tooltip placement="top" :show-after="300">
            <template #content>
              <div class="help-popover">
                <p><b>简单模式</b>：所有断言均会执行</p>
                <p><b>条件分支</b>：按响应条件选择断言组（如 code=0 校验成功字段，否则校验错误信息）</p>
                <p class="mt-5"><b>先选对象，再填目标：</b></p>
                <p>• <b>状态</b>：校验 HTTP 状态码</p>
                <p>• <b>响应体</b>：JSON 路径 / 全文包含 / 全文不包含</p>
                <p>• <b>响应头</b>：按 Header 名称取值后再比较</p>
              </div>
            </template>
            <el-icon class="section-help-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </span>
        <el-radio-group v-model="assertionMode" size="small" style="margin-right: 12px">
          <el-radio-button value="flat">简单模式</el-radio-button>
          <el-radio-button value="conditional">条件分支</el-radio-button>
        </el-radio-group>
        <template v-if="assertionMode === 'flat'">
          <el-button type="primary" link size="small" @click="addAssertion" icon="Plus">添加</el-button>
          <el-button type="warning" link size="small" @click="openGenDialog" icon="MagicStick">一键生成</el-button>
        </template>
      </div>
      <p v-if="assertionMode === 'flat'" class="section-hint">
        断言针对<strong>响应</strong>：可选状态码、响应体或响应头；选响应头时「目标」填 Header 名（如 Content-Type）。JSON 路径可点输入框右侧图标对照示例取值。
      </p>
      <AssertionGroupsEditor
        v-if="assertionMode === 'conditional'"
        v-model="form.assertion_groups"
        :sample-json="jsonPathSample"
      />
      <el-table v-else :data="form.assertions" size="small" border class="config-table">
        <el-table-column label="断言方式" min-width="168">
          <template #default="{ $index }">
            <HttpAssertionTypeSelect
              v-model="form.assertions[$index].type"
              size="small"
              :include-ws="isWsApi"
              @update:model-value="onAssertionTypeChange(form.assertions[$index])"
            />
          </template>
        </el-table-column>
        <el-table-column label="目标" min-width="200">
          <template #default="{ $index }">
            <JsonPathField
              v-if="isJsonPathAssertionType(form.assertions[$index].type)"
              v-model="form.assertions[$index].target"
              size="small"
              :sample-json="jsonPathSample"
              :placeholder="assertionTargetPlaceholder(form.assertions[$index].type, { includeWs: isWsApi })"
            />
            <el-input
              v-else-if="assertionNeedsTarget(form.assertions[$index].type, { includeWs: isWsApi })"
              v-model="form.assertions[$index].target"
              size="small"
              :placeholder="assertionTargetPlaceholder(form.assertions[$index].type, { includeWs: isWsApi })"
            />
            <span v-else class="target-na">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作符" width="120">
          <template #default="{ $index }">
            <el-select
              v-if="!['contains', 'not_contains', 'ws_contains'].includes(form.assertions[$index].type)"
              v-model="form.assertions[$index].operator"
              size="small"
            >
              <el-option label="等于" value="equals"/>
              <el-option label="不等于" value="not_equals"/>
              <el-option label="包含" value="contains"/>
              <el-option label="不包含" value="not_contains"/>
              <el-option label="大于" value="gt"/>
              <el-option label="大于等于" value="gte"/>
              <el-option label="小于" value="lt"/>
              <el-option label="小于等于" value="lte"/>
              <el-option label="在列表中" value="in"/>
              <el-option label="不在列表中" value="not_in"/>
              <el-option label="正则匹配" value="regex"/>
            </el-select>
            <span v-else class="operator-fixed">{{ form.assertions[$index].type === 'not_contains' ? '不包含' : '包含' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期望值">
          <template #default="{ $index }">
            <el-input v-model="form.assertions[$index].expected" size="small" placeholder="200"/>
          </template>
        </el-table-column>
        <el-table-column label="描述" width="120">
          <template #default="{ $index }">
            <el-input v-model="form.assertions[$index].description" size="small"/>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="removeAssertion($index)" icon="Delete"/>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 变量提取 -->
      <div class="section-title">
        <span>
          变量提取
          <el-tooltip placement="top" :show-after="300">
            <template #content>
              <div class="help-popover">
                <p><b>变量提取</b>从<strong>响应</strong>中取值，供后续接口使用（不是请求头/请求体）</p>
                <p class="mt-5"><b>来源说明：</b></p>
                <p>• <b>响应体 · JSON 路径</b>：如 <code>$.data.token</code></p>
                <p>• <b>响应体 · 正则</b>：匹配响应文本，建议用捕获组</p>
                <p>• <b>响应头 · Header 名</b>：如 <code>Set-Cookie</code>、<code>Authorization</code></p>
                <p class="mt-5"><b>使用方式：</b></p>
                <p>• 后续请求中写 <code v-pre>${{变量名}}</code>，名称须与此处变量名一致</p>
              </div>
            </template>
            <el-icon class="section-help-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </span>
        <el-button type="primary" link size="small" @click="addExtractor" icon="Plus">添加</el-button>
      </div>
      <p class="section-hint">
        从<strong>响应体</strong>或<strong>响应头</strong>提取；Cookie 一般在登录响应的 <code>Set-Cookie</code> 响应头。JSON 路径可点右侧图标打开提取工具。
      </p>
      <el-table :data="form.extractors" size="small" border class="config-table">
        <el-table-column label="变量名" width="140">
          <template #default="{ $index }">
            <el-input v-model="form.extractors[$index].name" size="small" placeholder="token"/>
          </template>
        </el-table-column>
        <el-table-column label="提取来源" width="180">
          <template #default="{ $index }">
            <HttpExtractorSourceSelect v-model="form.extractors[$index].source" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="提取表达式" min-width="220">
          <template #default="{ $index }">
            <JsonPathField
              v-if="isJsonPathExtractorSource(form.extractors[$index].source)"
              v-model="form.extractors[$index].path"
              size="small"
              :sample-json="jsonPathSample"
              :placeholder="extractorPathPlaceholder(form.extractors[$index].source)"
            />
            <el-input
              v-else
              v-model="form.extractors[$index].path"
              size="small"
              :placeholder="extractorPathPlaceholder(form.extractors[$index].source)"
            />
          </template>
        </el-table-column>
        <el-table-column label="描述" width="120">
          <template #default="{ $index }">
            <el-input v-model="form.extractors[$index].description" size="small"/>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="removeExtractor($index)" icon="Delete"/>
          </template>
        </el-table-column>
      </el-table>

      <!-- 前置/后置脚本 -->
      <el-collapse v-model="activeCollapse" class="request-config-collapse">
      <el-collapse-item name="pre_script">
        <template #title>
          <span class="collapse-title">
            前置脚本
            <el-tooltip placement="top" :show-after="300">
              <template #content>
                <div class="help-popover">
                  <p><b>前置脚本</b>在发送请求<b>之前</b>执行</p>
                  <p class="mt-5"><b>可用变量：</b></p>
                  <p>• 脚本语言：<b>Python</b>（RestrictedPython 受限沙箱，非完整 Python）</p>
                  <p>• <code>variables</code> — 字典，可读写；修改后在当前请求中生效</p>
                  <p>• <code>timestamp()</code> — 当前 Unix 时间戳；<b>不可用</b> <code>__import__</code></p>
                  <p>• <code>print(...)</code> — 输出到脚本日志，可在报告中查看</p>
                  <p class="mt-5"><b>典型场景：</b></p>
                  <p>1. 签名生成：把 timestamp、nonce 等动态参数写入 variables</p>
                  <p>2. 时间戳注入：<code>variables['ts'] = str(timestamp())</code></p>
                  <p>3. Token 刷新/加密：先判断 token 是否过期，重新获取后再赋值</p>
                  <p class="mt-5">在 URL / Header / Body 中引用变量请使用 <code v-pre>${{变量名}}</code>（如 <code v-pre>Authorization: Bearer ${{token}}</code>）</p>
                </div>
              </template>
              <el-icon class="section-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
            <el-tag v-if="form.pre_script" type="success" size="small" class="count-tag">已配置</el-tag>
          </span>
        </template>
        <el-input
          v-model="form.pre_script"
          type="textarea"
          :rows="10"
          :placeholder="PRE_SCRIPT_PLACEHOLDER"
          style="font-family: 'Courier New', Courier, monospace; font-size: 13px;"
        />
      </el-collapse-item>

      <!-- 后置脚本 -->
      <el-collapse-item name="post_script">
        <template #title>
          <span class="collapse-title">
            后置脚本
            <el-tooltip placement="top" :show-after="300">
              <template #content>
                <div class="help-popover">
                  <p><b>后置脚本</b>在收到响应<b>之后</b>执行</p>
                  <p class="mt-5"><b>可用变量：</b></p>
                  <p>• 脚本语言：<b>Python</b>（RestrictedPython 受限沙箱）</p>
                  <p>• <code>variables</code> — 字典，可读写；修改后传递给后续用例</p>
                  <p>• <code>response</code> — <code>&#123;status_code, body, headers&#125;</code></p>
                  <p>• <code>print(...)</code> — 输出到脚本日志</p>
                  <p class="mt-5"><b>典型场景：</b></p>
                  <p>1. 从响应体中提取变量传递给下游用例</p>
                  <p>2. 响应数据清洗/转换后再赋值</p>
                  <p>3. 条件判断：根据响应状态决定后续变量值</p>
                </div>
              </template>
              <el-icon class="section-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
            <el-tag v-if="form.post_script" type="success" size="small" class="count-tag">已配置</el-tag>
          </span>
        </template>
        <el-input
          v-model="form.post_script"
          type="textarea"
          :rows="10"
          :placeholder="POST_SCRIPT_PLACEHOLDER"
          style="font-family: 'Courier New', Courier, monospace; font-size: 13px;"
        />
      </el-collapse-item>
    </el-collapse>

    <!-- 数据库断言 -->
    <div class="dataset-section">
      <div class="section-header">
        <span class="section-title-text">
          数据库断言
          <el-tooltip placement="top" :show-after="200">
            <template #content>
              <div class="help-popover">
                <p>执行后按 SQL 查库做断言，适合校验落库结果。</p>
                <p class="mt-5">字段等于/包含等<strong>只看首行</strong>（字段缺失回退首列）；数据源须与顶部调试环境一致。</p>
                <p class="mt-5">完整案例与操作符说明：点下方工具栏「使用帮助」展开。</p>
              </div>
            </template>
            <el-icon class="section-help-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
          <el-tag v-if="form.db_assertions.length" type="success" size="small" style="margin-left: 6px;">{{ form.db_assertions.length }} 条</el-tag>
        </span>
        <el-button
          size="small"
          type="primary"
          link
          :disabled="!form.db_assertions.length || !refEnvId"
          :loading="testingDbAssertions"
          @click="handleTestDbAssertions"
        >
          调试断言
        </el-button>
      </div>
      <DbAssertionsEditor
        v-model="form.db_assertions"
        :datasources="datasources"
        :environment-id="refEnvId"
      />
      <DbAssertionTestResult :result="dbAssertionTestResult" />
    </div>

    <!-- 数据集（数据驱动） -->
    <div class="dataset-section">
      <div class="section-header">
        <span class="section-title-text">
          数据集
          <el-tooltip placement="top" :show-after="300">
            <template #content>
              <div class="help-popover">
                <p><b>数据驱动</b>：配置多行数据后，执行时每行数据独立运行一次</p>
                <p class="mt-5">每行数据中的变量名（列名）在请求中可用 <code v-pre>${{变量名}}</code> 引用</p>
                <p class="mt-5">行数据的<b>优先级最高</b>，会覆盖同名环境变量和传入变量</p>
                <p class="mt-5"><b>典型场景：</b>多用户登录、批量接口参数校验</p>
              </div>
            </template>
            <el-icon class="section-help-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
          <el-tag v-if="form.data_set.length > 0" type="warning" size="small" style="margin-left: 6px;">
            {{ form.data_set.length }} 行 · 执行时独立运行每行
          </el-tag>
        </span>
      </div>

      <!-- 列名管理 -->
      <div class="dataset-columns">
        <span style="color: #909399; font-size: 13px; margin-right: 8px;">列名：</span>
        <el-tag
          v-for="(col, ci) in datasetColumns"
          :key="ci"
          closable
          size="small"
          style="margin-right: 4px; margin-bottom: 4px;"
          @close="removeDatasetColumn(ci)"
        >{{ col }}</el-tag>
        <el-input
          v-model="newColumnName"
          size="small"
          placeholder="输入列名回车添加"
          style="width: 130px; display: inline-block;"
          @keyup.enter="addDatasetColumn"
        />
        <el-button size="small" type="primary" link @click="addDatasetColumn" style="margin-left: 4px;">添加列</el-button>
        <el-button size="small" type="primary" link @click="addDataRow" style="margin-left: 8px;">+ 添加行</el-button>
      </div>

      <!-- 数据行表格 -->
      <el-table
        v-if="datasetColumns.length > 0"
        :data="form.data_set"
        border
        size="small"
        style="margin-top: 8px;"
      >
        <el-table-column
          v-for="col in datasetColumns"
          :key="col"
          :label="col"
          min-width="120"
        >
          <template #default="{ row }">
            <el-input v-model="row[col]" size="small" :placeholder="col"/>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" fixed="right">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="removeDataRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-else
        :image-size="40"
        description="先添加列名，再添加数据行"
        style="padding: 10px 0;"
      />
    </div>

    </el-form>
    
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
    </template>
  </el-dialog>

  <!-- 断言生成弹窗 -->
  <el-dialog v-model="genDialog.visible" title="一键生成断言" width="700px" destroy-on-close>
    <div class="gen-dialog-content">
      <el-alert type="info" :closable="false" show-icon class="gen-hint">
        <template #title>
          <span>粘贴 JSON 响应示例，系统会根据字段类型和值智能推荐断言。打开时优先预填接口「响应示例」；若未维护示例则留空，请自行粘贴。</span>
        </template>
      </el-alert>

      <div class="gen-input-row">
        <JsonTextarea
          v-model="genDialog.jsonInput"
          :rows="6"
          placeholder='{"code": 0, "data": {"id": 1, "name": "test"}}'
        />
        <el-button type="primary" @click="generateAssertions" style="margin-top: 10px;">解析并生成</el-button>
      </div>

      <div v-if="genDialog.generatedAssertions.length > 0" class="gen-preview">
        <div class="gen-preview-header">
          <el-checkbox :model-value="genAllChecked" @update:model-value="toggleGenAll">全选</el-checkbox>
          <span class="gen-count">共 {{ genDialog.generatedAssertions.length }} 条</span>
        </div>
        <el-table :data="genDialog.generatedAssertions" size="small" border>
          <el-table-column width="55" align="center">
            <template #default="{ $index }">
              <el-checkbox v-model="genDialog.checkedItems[$index]">&nbsp;</el-checkbox>
            </template>
          </el-table-column>
          <el-table-column label="类型" min-width="140">
            <template #default="{ row }">
              <el-tag size="small" :type="row.type === 'status_code' ? 'warning' : 'primary'">
                {{ assertionTypeLabel(row.type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="目标" width="150" prop="target"/>
          <el-table-column label="操作符" width="100">
            <template #default="{ row }">
              {{ formatOperatorLabel(row.operator) }}
            </template>
          </el-table-column>
          <el-table-column label="期望值" width="100">
            <template #default="{ row }">
              {{ row.expected === null ? 'null' : row.expected }}
            </template>
          </el-table-column>
          <el-table-column label="描述" prop="description"/>
        </el-table>
      </div>
    </div>
    <template #footer>
      <el-button @click="genDialog.visible = false">取消</el-button>
      <el-button type="primary" @click="confirmAddGenerated" :disabled="genDialog.checkedItems.filter(v => v).length === 0">添加选中断言</el-button>
    </template>
  </el-dialog>

  <DataFactoryTagPicker
    v-model="tagPickerVisible"
    :project-id="proStore.projectInfo?.id"
    @insert="onDfTagInsert"
  />
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, provide } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'

import { catalogApi, buildCatalogTree } from '@/api/modules/catalog'
import { dataFactoryApi } from '@/api/modules/dataFactory'
import VarInsertButton from '@/components/VarInsertButton.vue'
import ApiCaseUsedVarsPanel from '@/components/ApiCaseUsedVarsPanel.vue'
import ToolInsertButton from '@/components/ToolInsertButton.vue'
import DbAssertionsEditor from './DbAssertionsEditor.vue'
import DbAssertionTestResult from './DbAssertionTestResult.vue'
import AssertionGroupsEditor from './AssertionGroupsEditor.vue'
import HttpExtractorSourceSelect from './HttpExtractorSourceSelect.vue'
import HttpAssertionTypeSelect from './HttpAssertionTypeSelect.vue'
import JsonPathField from '@/components/JsonPathField.vue'
import JsonTextarea from '@/components/JsonTextarea.vue'
import HeaderEditorPanel from '@/components/HeaderEditorPanel.vue'
import DataFactoryTagPicker from './DataFactoryTagPicker.vue'
import WsStepsEditor from './WsStepsEditor.vue'
import ApiTestFilePicker from '@/components/ApiTestFilePicker.vue'
import { insertVarRef } from '@/utils/varInsert.js'
import { buildAssertionsFromJson } from '@/utils/assertionSuggest'
import {
  assertionNeedsTarget,
  assertionTargetPlaceholder,
  assertionTypeLabel,
  extractorPathPlaceholder,
  isJsonPathAssertionType,
  isJsonPathExtractorSource,
} from '../utils/httpExtractAssertUi.js'
import { sampleJsonTextFromApi } from '@/utils/jsonPath.js'
import LinkFunctionalCaseButton from '@/views/TestManagement/components/LinkFunctionalCaseButton.vue'

const props = defineProps({
  modelValue: Boolean,
  data: Object,
  apis: Array
})

const emit = defineEmits(['update:modelValue', 'success'])

const proStore = ProjectStore()
const catalogTree = ref([])

const loadCatalogTree = async () => {
  if (!proStore.projectInfo?.id) return
  try {
    const res = await catalogApi.getList({ project_id: proStore.projectInfo.id, tree: true })
    if (res.status === 200) {
      const data = res.data
      catalogTree.value = Array.isArray(data) && data.some(item => item.children?.length)
        ? data
        : buildCatalogTree(data || [])
    }
  } catch (error) {
    catalogTree.value = []
  }
}
const formRef = ref()
const saving = ref(false)
const tagPickerVisible = ref(false)

async function onDfTagInsert(refStr) {
  const m = String(refStr).match(/^\$\{\{(.+)\}\}$/)
  const name = m ? m[1] : refStr
  const result = await insertVarRef(name)
  if (result?.ok) {
    ElMessage.success(result.mode === 'copy' ? `已复制 ${refStr}，请粘贴到输入框` : `已插入 ${refStr}`)
    return
  }
  form.request_params.push({ name: '', value: refStr, type: 'string', required: false, description: '' })
  ElMessage.success(`已添加到请求参数：${refStr}`)
}
const apiLoading = ref(false)
const filteredApis = ref([])
const activeCollapse = ref(['headers', 'params', 'body'])
const refEnvId = ref(null)
provide('varInsertEnvId', refEnvId)

const isEdit = computed(() => !!props.data)

const form = reactive({
  name: '',
  api_id: null,
  catalog_id: null,
  priority: 'P2',
  timeout: 30,
  retry_count: 0,
  tags: [],
  request_headers: [],
  request_params: [],
  request_body: '',
  request_body_type: 'json',
  request_body_fields: [],
  ws_steps: [],
  assertions: [],
  assertion_groups: [],
  extractors: [],
  pre_script: null,
  post_script: null,
  data_set: [],
  db_assertions: [],
})

const extractorVarNames = computed(() =>
  (form.extractors || []).map((e) => e.name).filter(Boolean)
)

const PRE_SCRIPT_PLACEHOLDER = `# 前置脚本：Python 受限沙箱，在发送请求前执行，可读写 variables 字典
# 示例1：注入分页参数（供 Params 中 \${{page}} / \${{size}} 引用）
variables['page'] = '1'
variables['size'] = '10'
variables['request_time'] = str(timestamp())
print('=== 前置脚本执行 ===')
print('page =', variables['page'])
print('size =', variables['size'])

# 示例2：拼接签名
# variables['sign'] = variables.get('token', '') + str(timestamp())

# 注意：不支持 __import__、import os 等；可用 timestamp() 获取时间戳`

const POST_SCRIPT_PLACEHOLDER = `# 后置脚本：Python 受限沙箱，在收到响应后执行
# 可用：variables（读写）、response（status_code/body/headers）、print()、timestamp()

body = response['body']
users = body.get('data') or []

variables['user_total'] = body.get('total')
variables['user_count'] = len(users)

if users:
    first = users[0]
    variables['first_user_id'] = first.get('id')
    variables['first_username'] = first.get('username')

print('=== 后置脚本执行 ===')
print('HTTP状态:', response['status_code'])
print('用户总数:', variables['user_total'])
print('第一个用户:', variables.get('first_username'), 'id=', variables.get('first_user_id'))

# 套件后续用例可引用 \${{first_user_id}}、\${{user_total}} 等`

// 当前选中的接口
const selectedApi = computed(() => {
  if (!form.api_id || !props.apis) return null
  return props.apis.find(api => api.id === form.api_id)
})

const jsonPathSample = computed(() => sampleJsonTextFromApi(selectedApi.value))


// 是否显示请求体覆盖区域
const isWsApi = computed(() => {
  if (selectedApi.value?.protocol === 'websocket') return true
  if (props.data?.api_protocol === 'websocket') return true
  return false
})

const showBodySection = computed(() => {
  if (isWsApi.value) return false
  if (!selectedApi.value) return false
  const method = selectedApi.value.method?.toUpperCase()
  return ['POST', 'PUT', 'PATCH'].includes(method)
})

// 初始化过滤列表
watch(() => props.apis, (val) => {
  filteredApis.value = val || []
}, { immediate: true })

// 过滤接口方法
const filterApis = (query) => {
  if (query) {
    apiLoading.value = true
    const lowerQuery = query.toLowerCase()
    filteredApis.value = (props.apis || []).filter(api => 
      (api.name && api.name.toLowerCase().includes(lowerQuery)) ||
      (api.path && api.path.toLowerCase().includes(lowerQuery)) ||
      (api.method && api.method.toLowerCase().includes(lowerQuery))
    )
    apiLoading.value = false
  } else {
    filteredApis.value = props.apis || []
  }
}

// 获取方法类型
const getMethodType = (method) => {
  const map = { 'GET': 'success', 'POST': 'primary', 'PUT': 'warning', 'DELETE': 'danger', 'PATCH': 'info' }
  return map[method] || ''
}

// ===== 数据格式转换工具 =====

// dict / list 转 {key, value} 数组（用于 headers 编辑）
const normalizeToKvArray = (data) => {
  if (!data) return []
  if (Array.isArray(data)) {
    return data.map(h => ({ key: h.key || h.name || '', value: String(h.value || '') })).filter(h => h.key)
  }
  if (typeof data === 'object') {
    return Object.entries(data).map(([key, value]) => ({ key, value: String(value) }))
  }
  return []
}

// {key, value} 数组转 dict（用于提交 headers）
const kvArrayToDict = (arr) => {
  const result = {}
  for (const item of arr) {
    if (item.key) result[item.key] = item.value
  }
  return result
}

// 标准化 params 为 {name, value, type} 数组
const normalizeParams = (data) => {
  if (!data) return []
  if (Array.isArray(data)) {
    return data.map(p => ({
      name: p.name || p.key || '',
      value: String(p.value !== undefined ? p.value : ''),
      type: p.type || 'string'
    })).filter(p => p.name)
  }
  if (typeof data === 'object') {
    return Object.entries(data).map(([name, value]) => ({
      name,
      value: String(value),
      type: 'string'
    }))
  }
  return []
}

// body 转字符串（用于编辑）
const bodyToString = (data) => {
  if (data === null || data === undefined || data === '') return ''
  if (typeof data === 'object' && !Array.isArray(data) && Object.keys(data).length === 0) return ''
  if (typeof data === 'string') return data
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

const bodyPlaceholder = computed(() => {
  switch (form.request_body_type) {
    case 'form-data':
      return '请通过下方表格编辑 form-data 字段'
    case 'x-www-form-urlencoded':
      return '示例：name=张三&age=18'
    case 'xml':
      return '<xml>...</xml>'
    case 'raw':
      return '任意文本内容'
    default:
      return '{"key": "value"}'
  }
})

const tagSuggestions = [
  { label: '压测', value: 'perf' },
  { label: '业务链路', value: 'journey' },
  { label: '登录', value: 'login' },
  { label: '已隔离（计划默认跳过）', value: 'quarantine' },
]

const rules = {
  name: [{ required: true, message: '请输入用例名称', trigger: 'blur' }],
  api_id: [{ required: true, message: '请选择关联接口', trigger: 'change' }]
}

// resetForm 必须在 watch 之前定义
const assertionMode = ref('flat')

const resetForm = () => {
  form.name = ''
  form.api_id = null
  form.catalog_id = null
  form.priority = 'P2'
  form.timeout = 30
  form.retry_count = 0
  form.tags = []
  form.request_headers = []
  form.request_params = []
  form.request_body = ''
  form.request_body_type = 'json'
  form.request_body_fields = []
  form.ws_steps = []
  form.assertions = []
  form.assertion_groups = []
  assertionMode.value = 'flat'
  form.extractors = []
  form.pre_script = null
  form.post_script = null
  form.data_set = []
  form.db_assertions = []
  dbAssertionTestResult.value = null
  activeCollapse.value = ['headers', 'params', 'body']
}

const datasources = ref([])
const testingDbAssertions = ref(false)
const dbAssertionTestResult = ref(null)
let datasourcesSeq = 0

const loadDatasources = async () => {
  const projectId = proStore.projectInfo?.id
  const envId = refEnvId.value
  const seq = ++datasourcesSeq
  if (!projectId || !envId) {
    // 未选调试环境时不拉全量数据源，避免误选其他环境
    if (seq === datasourcesSeq) datasources.value = []
    return
  }
  try {
    const res = await dataFactoryApi.listDatasources({
      project_id: projectId,
      environment_id: envId,
      size: 100,
    })
    if (seq !== datasourcesSeq) return
    datasources.value = res.data?.list || []
  } catch (e) {
    if (seq !== datasourcesSeq) return
    datasources.value = []
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载数据源失败')
  }
}

const handleTestDbAssertions = async () => {
  if (!refEnvId.value) {
    ElMessage.warning('请先选择调试环境')
    return
  }
  if (!form.db_assertions.length) {
    ElMessage.warning('请先配置数据库断言')
    return
  }
  testingDbAssertions.value = true
  dbAssertionTestResult.value = null
  try {
    const env = proStore.envList.find(e => e.id === refEnvId.value)
    const variables = {
      ...(proStore.projectInfo?.global_vars || {}),
      ...(env?.global_vars || {}),
    }
    const res = await dataFactoryApi.testDbAssertions({
      project_id: proStore.projectInfo.id,
      environment_id: refEnvId.value,
      assertions: form.db_assertions,
      variables,
    })
    dbAssertionTestResult.value = res.data
    if (dbAssertionTestResult.value?.all_passed) {
      ElMessage.success('数据库断言全部通过')
    } else {
      const failed = (dbAssertionTestResult.value?.results || []).find((r) => !r.passed)
      const detail = failed?.error || failed?.message || ''
      if (/环境不一致|绑定在/.test(detail)) {
        ElMessage.error('数据源与调试环境不一致，请查看下方说明')
      } else {
        ElMessage.error('数据库断言存在失败项，请查看下方详情')
      }
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '调试断言失败')
  } finally {
    testingDbAssertions.value = false
  }
}

watch(refEnvId, () => {
  loadDatasources()
  dbAssertionTestResult.value = null
})

watch(() => props.data, (val) => {
  if (val) {
    form.name = val.name
    form.api_id = val.api_id
    form.catalog_id = val.catalog_id ?? val.category_id ?? null
    form.priority = val.priority
    form.timeout = val.timeout
    form.retry_count = val.retry_count
    form.tags = Array.isArray(val.tags) ? [...val.tags] : []
    form.request_headers = normalizeToKvArray(val.request_headers)
    form.request_params = normalizeParams(val.request_params)
    form.request_body = bodyToString(val.request_body)
    form.request_body_type = val.request_body_type || 'json'
    form.request_body_fields = Array.isArray(val.request_body_fields) ? val.request_body_fields.map(f => ({
      name: f.name || '',
      value: f.value || '',
      field_type: f.field_type || 'text',
      file_name: f.file_name || '',
      mime_type: f.mime_type || 'application/octet-stream',
      file_key: f.file_key || '',
      file_bucket: f.file_bucket || '',
      description: f.description || ''
    })) : []
    form.ws_steps = Array.isArray(val.ws_steps) ? val.ws_steps.map(s => ({ ...s })) : []
    form.assertions = val.assertions?.map(a => ({ ...a })) || []
    form.assertion_groups = Array.isArray(val.assertion_groups)
      ? val.assertion_groups.map(g => ({
          ...g,
          condition: g.condition ? { ...g.condition } : null,
          assertions: (g.assertions || []).map(a => ({ ...a })),
        }))
      : []
    assertionMode.value = form.assertion_groups.length > 0 ? 'conditional' : 'flat'
    form.extractors = val.extractors?.map(e => ({ ...e })) || []
    form.pre_script = val.pre_script || null
    form.post_script = val.post_script || null
    form.data_set = Array.isArray(val.data_set) ? val.data_set.map(r => ({ ...r })) : []
    form.db_assertions = Array.isArray(val.db_assertions) ? val.db_assertions.map(a => ({ ...a })) : []
  } else {
    resetForm()
  }
}, { immediate: true })

// 当断言类型为 contains / not_contains 时，自动同步操作符
watch(() => form.assertions, (assertions) => {
  if (!assertions) return
  assertions.forEach(a => {
    if (a.type === 'contains' || a.type === 'ws_contains') {
      a.operator = 'contains'
    } else if (a.type === 'not_contains') {
      a.operator = 'not_contains'
    }
  })
}, { deep: true })

const onAssertionTypeChange = (row) => {
  if (!row) return
  if (row.type === 'contains' || row.type === 'ws_contains') {
    row.operator = 'contains'
  } else if (row.type === 'not_contains') {
    row.operator = 'not_contains'
  } else if (!row.operator) {
    row.operator = 'equals'
  }
  if (!assertionNeedsTarget(row.type, { includeWs: isWsApi.value })) {
    row.target = ''
  }
}

// 弹窗关闭后重置
const handleClosed = () => {
  resetForm()
  filteredApis.value = props.apis || []
}

// 获取用例详情（编辑模式）
const fetchCaseDetail = async (caseId) => {
  try {
    const res = await http.apiModuleApi.getApiCaseDetail(caseId)
    if (res.status === 200 && res.data) {
      const val = res.data
      form.name = val.name
      form.api_id = val.api_id
      form.catalog_id = val.catalog_id ?? val.category_id ?? null
      form.priority = val.priority || 'P2'
      form.timeout = val.timeout ?? 30
      form.retry_count = val.retry_count ?? 0
      form.tags = Array.isArray(val.tags) ? [...val.tags] : []
      form.request_headers = normalizeToKvArray(val.request_headers)
      form.request_params = normalizeParams(val.request_params)
      form.request_body = bodyToString(val.request_body)
      form.request_body_type = val.request_body_type || 'json'
      form.request_body_fields = Array.isArray(val.request_body_fields) ? val.request_body_fields.map(f => ({
        name: f.name || '',
        value: f.value || '',
        field_type: f.field_type || 'text',
        file_name: f.file_name || '',
        mime_type: f.mime_type || 'application/octet-stream',
        file_key: f.file_key || '',
        file_bucket: f.file_bucket || '',
        description: f.description || ''
      })) : []
      form.assertions = Array.isArray(val.assertions) ? val.assertions.map(a => ({ ...a })) : []
      form.assertion_groups = Array.isArray(val.assertion_groups)
        ? val.assertion_groups.map(g => ({
            ...g,
            condition: g.condition ? { ...g.condition } : null,
            assertions: (g.assertions || []).map(a => ({ ...a })),
          }))
        : []
      assertionMode.value = form.assertion_groups.length > 0 ? 'conditional' : 'flat'
      form.extractors = Array.isArray(val.extractors) ? val.extractors.map(e => ({ ...e })) : []
      form.pre_script = val.pre_script || null
      form.post_script = val.post_script || null
      form.data_set = Array.isArray(val.data_set) ? val.data_set.map(r => ({ ...r })) : []
    form.db_assertions = Array.isArray(val.db_assertions) ? val.db_assertions.map(a => ({ ...a })) : []
    }
  } catch (error) {
    ElMessage.error('获取用例详情失败')
  }
}

// 监听弹窗打开，编辑模式下获取详情
watch(() => props.modelValue, (visible) => {
  if (visible) {
    proStore.refreshProjectGlobals()
    dbAssertionTestResult.value = null
    if (!refEnvId.value && proStore.envList.length) {
      refEnvId.value = proStore.envList[0].id
    } else {
      // 环境未变时不会触发 refEnvId watch，需主动刷新数据源
      loadDatasources()
    }
    loadCatalogTree()
    if (props.data?.id) {
      nextTick(() => {
        fetchCaseDetail(props.data.id)
      })
    }
  }
})

// ===== 从接口复制默认配置 =====

const copyApiHeaders = () => {
  const api = selectedApi.value
  if (!api) return
  const apiHeaders = normalizeToKvArray(api.headers)
  if (apiHeaders.length === 0) {
    ElMessage.info('该接口没有定义默认请求头')
    return
  }
  form.request_headers = apiHeaders
  ElMessage.success('已复制接口默认请求头')
}

const copyApiParams = () => {
  const api = selectedApi.value
  if (!api) return
  const apiParams = normalizeParams(api.params)
  if (apiParams.length === 0) {
    ElMessage.info('该接口没有定义默认参数')
    return
  }
  form.request_params = apiParams
  ElMessage.success('已复制接口默认参数')
}

const mapApiBodyFields = (fields) =>
  Array.isArray(fields)
    ? fields.map(f => ({
        name: f.name || '',
        value: f.value || '',
        field_type: f.field_type || 'text',
        file_name: f.file_name || '',
        mime_type: f.mime_type || 'application/octet-stream',
        file_key: f.file_key || '',
        file_bucket: f.file_bucket || '',
        description: f.description || ''
      }))
    : []

const hasApiBodyContent = (api) => {
  const bodyType = api.body_type || 'json'
  if (bodyType === 'form-data') {
    return Array.isArray(api.body_fields) && api.body_fields.some(f => f?.name)
  }
  if (!api.body) return false
  if (typeof api.body === 'string') return api.body.trim().length > 0
  if (typeof api.body === 'object') return Object.keys(api.body).length > 0
  return false
}

const copyApiBody = async () => {
  const api = selectedApi.value
  if (!api) return
  let apiData = api
  try {
    if (api.id && (!Array.isArray(api.body_fields) || api.body_fields.length === 0)) {
      const res = await http.apiModuleApi.getApiDetail(api.id)
      if (res.status === 200 && res.data) apiData = res.data
    }
  } catch {
    ElMessage.error('获取接口详情失败')
    return
  }
  if (!hasApiBodyContent(apiData)) {
    ElMessage.info('该接口没有定义默认请求体')
    return
  }
  form.request_body_type = apiData.body_type || 'json'
  if (form.request_body_type === 'form-data') {
    form.request_body = ''
    form.request_body_fields = mapApiBodyFields(apiData.body_fields)
  } else {
    form.request_body = apiData.body
      ? (typeof apiData.body === 'string' ? apiData.body : JSON.stringify(apiData.body, null, 2))
      : ''
    form.request_body_fields = []
  }
  ElMessage.success('已复制接口默认请求体')
}

// ===== Params 操作 =====

const addParam = () => {
  form.request_params.push({ name: '', value: '', type: 'string' })
}

const removeParam = (index) => {
  form.request_params.splice(index, 1)
}

// ===== Body 操作 =====

const clearBody = () => {
  form.request_body = ''
  form.request_body_fields = []
  form.request_body_type = 'json'
  ElMessage.success('已清空请求体覆盖，将使用接口默认请求体')
}

// ===== 断言操作 =====

const addAssertion = () => {
  form.assertions.push({
    type: 'status_code',
    target: '',
    operator: 'equals',
    expected: '200',
    description: ''
  })
}

const removeAssertion = (index) => {
  form.assertions.splice(index, 1)
}

// ===== 断言辅助生成 =====

const genDialog = reactive({
  visible: false,
  jsonInput: '',
  generatedAssertions: [],
  checkedItems: []
})

const genAllChecked = computed(() => {
  return genDialog.generatedAssertions.length > 0 &&
         genDialog.checkedItems.every(v => v)
})

const toggleGenAll = (val) => {
  genDialog.checkedItems = genDialog.generatedAssertions.map(() => val)
}

const openGenDialog = () => {
  genDialog.visible = true
  genDialog.jsonInput = ''
  genDialog.generatedAssertions = []
  genDialog.checkedItems = []

  // 只预填响应示例（example），不要整包 stringify schema（会导致断言生成失败）
  const sample = sampleJsonTextFromApi(selectedApi.value)
  if (sample) {
    genDialog.jsonInput = sample
  }
}

const generateAssertions = () => {
  const { assertions, error } = buildAssertionsFromJson(genDialog.jsonInput)
  if (error) {
    ElMessage.warning(error)
    return
  }
  genDialog.generatedAssertions = assertions
  genDialog.checkedItems = assertions.map(() => true)
}

const formatOperatorLabel = (op) => {
  const map = {
    equals: '等于',
    not_equals: '不等于',
    contains: '包含',
    not_contains: '不包含',
    gt: '大于',
    gte: '大于等于',
    lt: '小于',
    lte: '小于等于',
    in: '在列表中',
    not_in: '不在列表中',
    regex: '正则匹配',
  }
  return map[op] || op
}

const confirmAddGenerated = () => {
  const toAdd = genDialog.generatedAssertions.filter((_, i) => genDialog.checkedItems[i])
  for (const a of toAdd) {
    form.assertions.push({ ...a })
  }
  genDialog.visible = false
  ElMessage.success(`已添加 ${toAdd.length} 条断言`)
}

// ===== 提取器操作 =====

const addExtractor = () => {
  form.extractors.push({
    name: '',
    source: 'json',
    path: '',
    description: ''
  })
}

const removeExtractor = (index) => {
  form.extractors.splice(index, 1)
}

// ===== 数据集（数据驱动）操作 =====

const newColumnName = ref('')

// 从 data_set 的所有行中提取列名（保持顺序，去重）
const datasetColumns = computed(() => {
  const cols = []
  const seen = new Set()
  for (const row of form.data_set) {
    for (const key of Object.keys(row)) {
      if (!seen.has(key)) {
        cols.push(key)
        seen.add(key)
      }
    }
  }
  return cols
})

const addDatasetColumn = () => {
  const col = newColumnName.value.trim()
  if (!col) return
  if (datasetColumns.value.includes(col)) {
    ElMessage.warning('列名已存在')
    return
  }
  // 给所有行追加该列（默认空字符串）
  form.data_set.forEach(row => { row[col] = '' })
  // 若无数据行，添加一行
  if (form.data_set.length === 0) {
    form.data_set.push({ [col]: '' })
  }
  newColumnName.value = ''
}

const removeDatasetColumn = (colIndex) => {
  const col = datasetColumns.value[colIndex]
  form.data_set.forEach(row => { delete row[col] })
}

const addDataRow = () => {
  const cols = datasetColumns.value
  if (cols.length === 0) {
    ElMessage.warning('请先添加列名')
    return
  }
  const row = {}
  cols.forEach(c => { row[c] = '' })
  form.data_set.push(row)
}

const removeDataRow = (index) => {
  form.data_set.splice(index, 1)
}

const onBodyFieldFileUpdate = (index, patch) => {
  Object.assign(form.request_body_fields[index], patch)
}

const addBodyField = () => {
  form.request_body_fields.push({
    name: '',
    value: '',
    field_type: 'text',
    file_name: '',
    mime_type: 'application/octet-stream',
    file_key: '',
    file_bucket: '',
    description: ''
  })
}

const removeBodyField = (index) => {
  form.request_body_fields.splice(index, 1)
}

const onBodyFieldTypeChange = (index) => {
  const field = form.request_body_fields[index]
  if (!field) return
  if (field.field_type === 'text') {
    field.file_name = ''
    field.mime_type = 'application/octet-stream'
    field.file_key = ''
    field.file_bucket = ''
  } else {
    field.value = ''
  }
}

// ===== 保存 =====

const handleSave = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  if (form.request_body_type === 'form-data') {
    const invalidField = form.request_body_fields.find(f => f.field_type === 'file' && !f.file_key)
    if (invalidField) {
      ElMessage.error(`字段 ${invalidField.name || '未命名'} 需要先上传文件`) 
      return
    }
  }

  // 解析 request_body
  let requestBody = null
  if (form.request_body_type !== 'form-data' && form.request_body && form.request_body.trim()) {
    try {
      requestBody = JSON.parse(form.request_body)
    } catch {
      requestBody = form.request_body
    }
  }

  saving.value = true
  try {
    const payloadGroups = assertionMode.value === 'conditional' ? form.assertion_groups : []
    const data = {
      ...form,
      assertions: assertionMode.value === 'flat' ? form.assertions : [],
      assertion_groups: payloadGroups,
      request_headers: kvArrayToDict(form.request_headers),
      request_params: form.request_params.map(p => ({
        name: p.name,
        value: p.value,
        type: p.type || 'string',
        required: true,
        description: ''
      })),
      request_body: requestBody,
      request_body_type: form.request_body_type,
      request_body_fields: form.request_body_fields.map(f => ({
        name: f.name,
        value: f.value,
        field_type: f.field_type,
        file_name: f.file_name,
        mime_type: f.mime_type,
        file_key: f.file_key,
        file_bucket: f.file_bucket,
        description: f.description
      })),
      project_id: proStore.projectInfo.id
    }
    
    if (isEdit.value) {
      await http.apiModuleApi.updateTestCase(props.data.id, data)
    } else {
      await http.apiModuleApi.createTestCase(data)
    }
    
    ElMessage.success('保存成功')
    emit('success')
    emit('update:modelValue', false)
  } catch (error) {
    const detail = error?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped lang="scss">
.dialog-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.help-icon {
  font-size: 18px;
  color: var(--el-color-primary);
  cursor: pointer;
  transition: transform 0.2s;
  
  &:hover {
    transform: scale(1.1);
    color: var(--el-color-primary-light-3);
  }
}

.help-content {
  max-width: 400px;
  line-height: 1.6;
  
  .help-title {
    font-weight: bold;
    font-size: 14px;
    margin-bottom: 10px;
    color: var(--el-color-primary);
  }
  
  .help-section {
    margin: 8px 0 4px 0;
    font-weight: 500;
  }
  
  .help-item {
    margin: 3px 0;
    padding-left: 8px;
    font-size: 13px;
  }
  
  .help-example {
    margin-top: 10px;
    padding: 8px;
    background: var(--el-fill-color-light);
    border-radius: 4px;
    font-size: 13px;
    color: var(--el-text-color-regular);
  }
}

.section-help-icon {
  font-size: 14px;
  color: var(--el-color-info);
  cursor: pointer;
  margin-left: 4px;
  vertical-align: middle;
  
  &:hover {
    color: var(--el-color-primary);
  }
}

.help-popover {
  max-width: 350px;
  line-height: 1.6;
  
  p {
    margin: 4px 0;
  }
  
  .mt-5 {
    margin-top: 8px;
  }
}

.var-toolbar {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 14px;
  padding: 10px 14px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.var-toolbar-actions {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 8px;
  width: 100%;
  overflow-x: auto;
}

.var-toolbar-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 20px 0 12px;
  padding: 0 2px 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-weight: 500;
  gap: 8px;
}

.config-table {
  width: 100%;

  :deep(.el-table__cell) {
    padding: 8px 10px;
    vertical-align: middle;
  }

  :deep(.el-table .cell) {
    padding: 0 4px;
    line-height: 1.4;
    overflow: hidden;
  }
}
.operator-fixed {
  color: #606266;
  font-size: 13px;
  padding-left: 4px;
}

.section-hint {
  margin: -4px 0 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.target-na {
  color: #909399;
  font-size: 13px;
  padding-left: 4px;
}

// 接口选项样式
.api-option {
  padding: 4px 0;
  
  .api-option-name {
    font-weight: 500;
    color: var(--el-text-color-primary);
    margin-bottom: 2px;
  }
  
  .api-option-path {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}

// 折叠面板样式
.request-config-collapse {
  margin-bottom: 12px;
  width: 100%;
  overflow: hidden;

  :deep(.el-collapse-item) {
    overflow: hidden;
  }

  :deep(.el-collapse-item__header) {
    font-weight: 500;
    font-size: 14px;
    height: auto;
    min-height: 44px;
    line-height: 1.4;
    padding: 8px 12px;
    align-items: center;
    box-sizing: border-box;
  }

  :deep(.el-collapse-item__arrow) {
    margin: 0 0 0 8px;
    flex-shrink: 0;
  }

  :deep(.el-collapse-item__wrap) {
    border-bottom: none;
    overflow: hidden;
  }

  :deep(.el-collapse-item__content) {
    padding: 12px 14px 16px;
    box-sizing: border-box;
    overflow-x: auto;
  }

  .collapse-header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    width: 100%;
    min-width: 0;
    padding-right: 4px;
    box-sizing: border-box;
  }

  .collapse-title {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    flex: 1;
  }

  .count-tag {
    margin-left: 4px;
    flex-shrink: 0;
  }

  .section-actions {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px 8px;
    flex-shrink: 0;
    margin-bottom: 0;
  }

  .body-mode-row {
    margin: 0 0 12px;
    width: 100%;
    overflow-x: auto;
  }

  .body-mode-group {
    display: inline-flex;
    flex-wrap: wrap;
  }

  .form-data-editor {
    margin-top: 8px;
    width: 100%;
    overflow-x: auto;
  }

  .compact-actions {
    margin-bottom: 10px;
  }

  .body-textarea {
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
    width: 100%;
    box-sizing: border-box;
  }

  .file-field-cell {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .file-meta-name {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .hidden-file-input {
    display: none;
  }

  .body-hint {
    margin-top: 10px;
  }
}

:deep(.case-edit-dialog) {
  display: flex;
  flex-direction: column;
  max-height: 85vh;
  width: min(1100px, 96vw) !important;
  overflow: hidden;

  .el-dialog__body {
    flex: 1;
    overflow-x: hidden;
    overflow-y: auto;
    padding: 14px 20px 20px;
    max-height: calc(85vh - 110px);
    box-sizing: border-box;
  }

  .el-dialog__footer {
    padding: 12px 20px 16px;
  }
}

.dataset-section {
  margin-top: 16px;
  padding: 14px 16px 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-fill-color-blank);

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 12px;

    .section-title-text {
      font-size: 14px;
      font-weight: 500;
      color: var(--el-text-color-primary);
      display: flex;
      align-items: center;
      gap: 4px;
      line-height: 1.4;
    }
  }

  .dataset-columns {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    padding: 10px 12px;
    background: var(--el-fill-color-lighter);
    border-radius: 6px;
  }

  :deep(.el-table__cell) {
    padding: 8px 10px;
  }

  :deep(.el-table .cell) {
    padding: 0 4px;
  }
}
</style>
