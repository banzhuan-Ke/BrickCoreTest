<template>
  <div>
    <div class="head-bar">
      <el-button link type="primary" @click="goBack">← 返回文件夹列表</el-button>
      <span v-if="folder" class="folder-title">{{ folder.name }}</span>
      <el-tag v-if="folder?.iteration_label" size="small">{{ folder.iteration_label }}</el-tag>
    </div>

    <el-alert
      v-if="ragStats.needsIndex > 0"
      type="warning"
      :closable="false"
      show-icon
      class="rag-alert"
      :title="`${ragStats.needsIndex} 篇文档已解析但未建立词法索引（${ragStats.indexed}/${ragStats.ready} 已索引）`"
    >
      <template #default>
        <div class="rag-alert-actions">
          <span class="rag-alert-hint">上传后若已开启「上传后重建词法索引」，请稍候刷新；重建词法后会按配置自动尝试向量索引。</span>
          <el-button v-if="canManage" size="small" type="warning" :loading="batchJob.running && batchJob.kind === 'lexical'" @click="batchReindexRag">
            批量重建词法索引
          </el-button>
        </div>
      </template>
    </el-alert>

    <el-alert
      v-if="vectorEmbedEnabled && vectorStats.needsVector > 0"
      type="info"
      :closable="false"
      show-icon
      class="rag-alert"
      :title="`${vectorStats.needsVector} 篇文档词法已就绪但向量未建立（${vectorStats.indexed}/${vectorStats.ready} 已向量化）`"
    >
      <template #default>
        <div class="rag-alert-actions">
          <span class="rag-alert-hint">向量 Embedding 需在「生成配置」中开启；不符合策略的文档会自动跳过。</span>
          <el-button v-if="canManage" size="small" type="primary" :loading="batchJob.running && batchJob.kind === 'vector'" @click="batchReindexVector">
            批量重建向量
          </el-button>
          <el-button v-if="canManage" size="small" :loading="batchJob.running && batchJob.kind === 'all'" @click="batchReindexAll">
            批量全部重建
          </el-button>
        </div>
      </template>
    </el-alert>

    <el-progress
      v-if="batchJob.running"
      :percentage="batchProgressPercent"
      :format="() => batchJob.label"
      style="margin-bottom: 12px;"
    />

    <div class="toolbar">
      <el-select v-model="filters.doc_type" clearable placeholder="文档类型" style="width: 160px;" @change="loadDocs">
        <el-option v-for="t in docTypes" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <el-input v-model="filters.keyword" placeholder="搜索标题" clearable style="width: 200px;" @keyup.enter="loadDocs" />
      <el-button type="primary" @click="loadDocs">查询</el-button>
      <el-button @click="goSearchInFolder">在本文件夹检索</el-button>
      <el-button @click="goQaInFolder">在本文件夹问答</el-button>
      <el-upload
        v-if="canManage"
        :show-file-list="false"
        :auto-upload="false"
        :on-change="onFilePick"
      >
        <el-button type="success">上传文档</el-button>
      </el-upload>
    </div>

    <div v-if="selectedDocs.length && canManage" class="batch-select-bar">
      <span>已选 <b>{{ selectedDocs.length }}</b> 篇文档</span>
      <el-button size="small" :disabled="batchJob.running" @click="batchSelectedReindexRag">重建词法</el-button>
      <el-button v-if="vectorEmbedEnabled" size="small" :disabled="batchJob.running" @click="batchSelectedReindexVector">重建向量</el-button>
      <el-button size="small" :disabled="batchJob.running" @click="batchSelectedReindexAll">全部重建</el-button>
      <el-button size="small" type="primary" :disabled="batchJob.running" :loading="batchJob.running && batchJob.kind === 'digest'" @click="batchSelectedRebuildDigest">
        重建摘要
      </el-button>
      <el-button size="small" :disabled="batchJob.running" :loading="batchJob.running && batchJob.kind === 'reparse'" @click="batchSelectedReparse">
        重新解析(v2)
      </el-button>
      <el-button size="small" type="danger" :disabled="batchJob.running" @click="batchSelectedDelete">删除</el-button>
      <el-button size="small" link @click="clearSelection">取消选择</el-button>
    </div>

    <el-table ref="docTableRef" :data="docs" v-loading="loading" stripe @selection-change="onDocSelectionChange">
      <el-table-column v-if="canManage" type="selection" width="46" fixed="left" />
      <el-table-column prop="title" label="标题" min-width="160" />
      <el-table-column prop="doc_type_label" label="类型" width="120" />
      <el-table-column prop="file_name" label="文件名" min-width="180" show-overflow-tooltip />
      <el-table-column label="解析" width="96" align="center">
        <template #default="{ row }">
          <el-tag :type="parseTag(row.parse_status)" size="small">{{ parseLabel(row.parse_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="char_count" label="字符数" width="88" align="center" />
      <el-table-column label="结构" width="88" align="center">
        <template #default="{ row }">
          <el-tag v-if="(row.sections_version || 1) >= 2" type="success" size="small">v2</el-tag>
          <el-tag v-else type="info" size="small">v1</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="chunk_count" label="分块" width="72" align="center" />
      <el-table-column label="词法索引" width="96" align="center">
        <template #default="{ row }">
          <el-tag :type="lexicalTag(row.embed_status)" size="small">{{ lexicalLabel(row.embed_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="向量" width="88" align="center">
        <template #default="{ row }">
          <el-tag :type="vectorTag(row.vector_status)" size="small">{{ vectorLabel(row.vector_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="AI摘要" width="88" align="center">
        <template #default="{ row }">
          <el-tag :type="digestTag(row.digest_status)" size="small">{{ digestLabel(row.digest_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="默认模板" width="96" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_default_template" type="success" size="small">是</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="create_time" label="上传时间" width="168">
        <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="460" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="previewDoc(row)">文档详情</el-button>
          <el-button link type="primary" @click="downloadDoc(row)">下载</el-button>
          <el-button v-if="canManage && isTemplateType(row.doc_type)" link type="primary" @click="setDefault(row)">
            设为默认
          </el-button>
          <el-button v-if="canManage" link type="primary" @click="reparse(row, 'default')">重新解析</el-button>
          <el-button v-if="canManage" link type="warning" @click="reparse(row, 'enhanced')">加强识图</el-button>
          <el-button v-if="canManage" link type="primary" :loading="reindexingLexicalId === row.id" @click="reindexRag(row)">重建词法索引</el-button>
          <el-button v-if="canManage && vectorEmbedEnabled" link type="primary" :loading="reindexingVectorId === row.id" @click="reindexVector(row)">
            重建向量
          </el-button>
          <el-button v-if="canRunKnowledge" link type="primary" :loading="rebuildingDigestId === row.id" @click="rebuildDigest(row)">重建摘要</el-button>
          <el-button v-if="canManage" link type="danger" @click="removeDoc(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadDocs"
      />
    </div>

    <el-dialog v-model="uploadDialog.visible" title="上传文档" width="480px" destroy-on-close>
      <el-form label-width="88px">
        <el-form-item label="文件">
          <span>{{ uploadDialog.file?.name }}</span>
        </el-form-item>
        <el-form-item label="文档类型" required>
          <el-select v-model="uploadDialog.doc_type" style="width: 100%;">
            <el-option v-for="t in docTypes" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
          <div class="upload-type-hint">
            支持 doc / docx / xls / xlsx / ppt / pptx / pdf / csv 等；报告输出模板请用 <b>.docx</b>（.doc 仅可存档）
          </div>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="uploadDialog.title" placeholder="可选，默认同文件名" />
        </el-form-item>
      </el-form>
      <template #footer>
        <p v-if="uploadDialog.uploading" class="upload-hint">正在上传文件，解析将在后台进行…</p>
        <el-button @click="uploadDialog.visible = false" :disabled="uploadDialog.uploading">取消</el-button>
        <el-button type="primary" :loading="uploadDialog.uploading" @click="confirmUpload">
          {{ uploadDialog.uploading ? '上传中…' : '上传' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="previewDialog.visible"
      :title="previewDialog.title"
      width="920px"
      destroy-on-close
      class="knowledge-doc-preview-dialog"
    >
      <div class="preview-body">
        <div v-if="previewDialog.loading" class="preview-loading-state">
          <el-icon class="preview-loading-icon is-loading" :size="40"><Loading /></el-icon>
          <p class="preview-loading-title">正在加载文档预览</p>
          <p class="preview-loading-hint">{{ previewLoadingHint }}</p>
        </div>
        <template v-else>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="preview-tip"
          title="文档详情：解析原文、分块索引与 AI 摘要；语义检索请用顶部「资料检索」。"
        />
        <div v-if="previewDialog.meta" class="preview-meta">
          <el-tag v-if="previewDialog.refreshing" type="info" size="small" effect="plain">刷新中…</el-tag>
          <el-tag size="small">{{ previewDialog.meta.doc_type_label }}</el-tag>
          <span class="preview-file">{{ previewDialog.meta.file_name }}</span>
          <el-tag :type="parseTag(previewDialog.meta.parse_status)" size="small">
            {{ parseLabel(previewDialog.meta.parse_status) }}
          </el-tag>
          <span v-if="previewDialog.meta.char_count" class="preview-chars">
            约 {{ previewDialog.meta.char_count }} 字
          </span>
          <el-tag v-if="previewDialog.meta.preview_truncated" type="warning" size="small">已截断</el-tag>
          <el-tag :type="lexicalTag(previewDialog.meta.embed_status)" size="small">
            词法 {{ lexicalLabel(previewDialog.meta.embed_status) }}
          </el-tag>
          <el-tag :type="vectorTag(previewDialog.meta.vector_status)" size="small">
            向量 {{ vectorLabel(previewDialog.meta.vector_status) }}
          </el-tag>
          <el-select
            v-if="canManage && previewDialog.row"
            v-model="previewDialog.embedMode"
            size="small"
            style="width: 148px; margin-left: 8px;"
            @change="saveEmbedMode"
          >
            <el-option v-for="opt in embedModeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
          <el-tag v-if="previewDialog.meta.has_digest" type="success" size="small">已有摘要</el-tag>
          <el-tag v-if="(previewDialog.meta.sections_version || 1) >= 2" type="success" size="small">解析 v2</el-tag>
          <el-tag v-else type="info" size="small">解析 v1</el-tag>
          <el-tag v-if="previewDialog.meta.structured_kind === 'tabular'" size="small">表格</el-tag>
          <el-tag v-else-if="previewDialog.meta.structured_kind === 'prose'" size="small">长文档</el-tag>
          <el-tag v-if="previewDialog.meta.structured_profile" size="small" type="warning">
            {{ structuredProfileLabel(previewDialog.meta.structured_profile) }}
          </el-tag>
          <el-tag
            v-if="previewDialog.meta.image_parse?.total"
            :type="imageParseTag(previewDialog.meta.image_parse)"
            size="small"
          >
            {{ imageParseLabel(previewDialog.meta.image_parse) }}
          </el-tag>
        </div>

        <el-alert
          v-for="(warn, wIdx) in previewDialog.parseWarnings"
          :key="wIdx"
          type="warning"
          :closable="false"
          show-icon
          class="preview-warn"
          :title="warn"
        />

        <el-tabs v-model="previewDialog.activeTab" class="preview-tabs" @tab-change="onPreviewTabChange">
          <el-tab-pane label="解析内容" name="content">
            <div v-if="previewDialog.format === 'sheets' && previewDialog.sheets.length" class="preview-sheets">
              <div v-for="(sheet, idx) in previewDialog.sheets" :key="idx" class="sheet-block">
                <div class="sheet-name">{{ sheet.name }}</div>
                <el-table :data="sheetTableRows(sheet)" border stripe size="small" max-height="360">
                  <el-table-column
                    v-for="col in sheetTableColumns(sheet)"
                    :key="col.prop"
                    :prop="col.prop"
                    :label="col.label"
                    min-width="100"
                    show-overflow-tooltip
                  />
                </el-table>
                <div v-if="(sheet.total_rows || sheet.rows.length) > sheet.rows.length" class="sheet-more">
                  共 {{ sheet.total_rows || sheet.rows.length }} 行，仅展示前 {{ sheet.rows.length }} 行
                </div>
                <div v-else-if="sheet.rows_truncated" class="sheet-more sheet-warn">
                  源数据共 {{ sheet.total_rows || '—' }} 行，已入库 {{ sheet.stored_row_count ?? '—' }} 行（超出上限已截断）
                </div>
              </div>
            </div>

            <div v-else-if="previewDialog.format === 'sections' && previewDialog.sections.length" class="preview-sections">
              <article v-for="(sec, idx) in previewDialog.sections" :key="idx" class="preview-section">
                <h4 v-if="sec.title" class="section-title">{{ sec.title }}</h4>
                <p v-if="sec.body" class="section-body">{{ sec.body }}</p>
              </article>
            </div>

            <pre v-else-if="previewDialog.text" class="preview-text">{{ previewDialog.text }}</pre>
            <el-empty v-else description="暂无可预览内容（可能尚未解析或文件为空）" />
          </el-tab-pane>
          <el-tab-pane v-if="previewDialog.outline.length" label="文档目录" name="outline">
            <div class="outline-panel">
              <p class="outline-hint">v2 长文档目录（不含正文）；问答「第 X 章讲了什么」会优先命中对应章节。</p>
              <ul class="outline-list">
                <li
                  v-for="(item, idx) in previewDialog.outline"
                  :key="idx"
                  class="outline-item"
                  :style="{ paddingLeft: `${Math.max(0, (Number(item.level) || 1) - 1) * 16}px` }"
                >
                  <span class="outline-title">{{ item.title || '（无标题）' }}</span>
                  <span v-if="item.page != null" class="outline-meta">第 {{ item.page }} 页</span>
                  <span v-if="item.char_count != null" class="outline-meta">约 {{ item.char_count }} 字</span>
                </li>
              </ul>
            </div>
          </el-tab-pane>
          <el-tab-pane :label="chunksTabLabel" name="chunks">
            <div v-loading="previewDialog.chunksLoading">
              <el-alert
                v-if="!previewDialog.chunks.length && !previewDialog.chunksLoading"
                type="info"
                :closable="false"
                show-icon
                title="暂无分块"
                description="文档解析完成后需建立词法分块索引；可关闭弹窗后点击「重建词法索引」，或等待上传后自动索引。"
              />
              <el-table
                v-else
                :data="previewDialog.chunks"
                stripe
                border
                size="small"
                max-height="420"
                row-key="id"
              >
                <el-table-column label="#" width="56" align="center">
                  <template #default="{ row }">{{ (row.chunk_index ?? 0) + 1 }}</template>
                </el-table-column>
                <el-table-column label="章节" width="120" show-overflow-tooltip>
                  <template #default="{ row }">
                    {{ row.section_title || '—' }}
                  </template>
                </el-table-column>
                <el-table-column prop="char_count" label="字数" width="72" align="center" />
                <el-table-column label="分块内容" min-width="280">
                  <template #default="{ row }">
                    <KnowledgeChunkText :text="chunkPreviewText(row)" :max-height="200" />
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="72" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" @click="openChunkDetail(row)">全文</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-tab-pane>
          <el-tab-pane label="AI 摘要" name="digest">
            <el-alert
              v-if="previewDialog.meta?.digest_status === 'indexing'"
              type="warning"
              :closable="false"
              show-icon
              title="摘要生成中"
              description="AI 正在后台生成摘要，可关闭此窗口或刷新页面；完成后列表「AI摘要」列会变为「已有」。"
            />
            <el-alert
              v-else-if="previewDialog.meta?.digest_status === 'failed'"
              type="error"
              :closable="false"
              show-icon
              title="摘要生成失败"
              :description="previewDialog.meta?.digest_error || '请检查 AI 模型配置后重试'"
            />
            <el-alert
              v-else-if="!previewDialog.digestText"
              type="info"
              :closable="false"
              show-icon
              title="暂无 AI 摘要"
              description="长文档（默认 ≥12000 字）上传后会自动生成；也可点击「重建摘要」手动生成。短文档生成报告时直接全文引用，通常无需摘要。"
            />
            <div v-else class="digest-panel">
              <div class="digest-meta">
                约 {{ previewDialog.digestCharCount || previewDialog.digestText.length }} 字
                <span v-if="previewDialog.digestUpdatedAt"> · 更新于 {{ formatTime(previewDialog.digestUpdatedAt) }}</span>
              </div>
              <KnowledgeDigestView :content="previewDialog.digestText" />
            </div>
          </el-tab-pane>
          <el-tab-pane v-if="imageParseTabVisible" :label="imageParseTabLabel" name="image_parse">
            <div class="image-parse-panel">
              <el-alert
                v-if="previewDialog.imageParseDetails?.summary?.status === 'parsing'"
                type="warning"
                :closable="false"
                show-icon
                title="识图进行中"
                :description="imageParseLabel(previewDialog.imageParseDetails.summary)"
              />
              <el-alert
                v-else-if="!previewDialog.imageParseDetails?.has_full_results"
                type="info"
                :closable="false"
                show-icon
                title="暂无完整识图明细"
                description="该文档在升级明细功能前已完成识图。可点击「重新解析」或「加强识图」后查看每张图的 OCR / Vision 结果。"
              />
              <div v-if="imageParseSummaryText" class="image-parse-summary">
                {{ imageParseSummaryText }}
              </div>
              <div v-if="imageParseJobRunning && canManage" class="image-parse-actions">
                <el-button type="danger" plain size="small" :loading="stoppingImageParse" @click="stopImageParse">
                  停止识图
                </el-button>
              </div>
              <el-table
                v-if="previewDialog.imageParseDetails?.items?.length"
                :data="previewDialog.imageParseDetails.items"
                stripe
                border
                size="small"
                max-height="420"
                row-key="index"
              >
                <el-table-column label="#" width="52" align="center">
                  <template #default="{ row }">{{ row.display_index ?? (row.index + 1) }}</template>
                </el-table-column>
                <el-table-column label="图片" width="92" align="center">
                  <template #default="{ row }">
                    <div
                      class="image-parse-thumb-wrap"
                      :class="{ clickable: !!imageThumbUrl(row.index) }"
                      @click.stop="imageThumbUrl(row.index) && openImageParseDetail(row)"
                    >
                      <img
                        v-if="imageThumbUrl(row.index)"
                        :src="imageThumbUrl(row.index)"
                        class="image-parse-thumb"
                        alt="文档图片"
                      />
                      <span v-else-if="previewDialog.imageThumbnailsLoading" class="image-parse-thumb-loading">…</span>
                      <span v-else class="image-parse-thumb-empty">—</span>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="页码" width="72" align="center">
                  <template #default="{ row }">{{ row.page != null ? row.page : '—' }}</template>
                </el-table-column>
                <el-table-column label="所属章节" min-width="120" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.section_title || '—' }}</template>
                </el-table-column>
                <el-table-column label="OCR" width="80" align="center">
                  <template #default="{ row }">
                    <el-tag v-bind="imageParseStatusTag(row, 'ocr')" size="small">{{ imageParseStatusText(row, 'ocr') }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="Vision" width="88" align="center">
                  <template #default="{ row }">
                    <el-tag v-bind="imageParseStatusTag(row, 'vision')" size="small">{{ imageParseStatusText(row, 'vision') }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="识别摘要" min-width="220">
                  <template #default="{ row }">
                    <span class="image-parse-preview">{{ imageParseRowPreview(row) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="130" align="center">
                  <template #default="{ row }">
                    <el-button link type="primary" @click="openImageParseDetail(row)">详情</el-button>
                    <el-button
                      v-if="canManage && !imageParseJobRunning"
                      link
                      type="warning"
                      :loading="reparsingImageIndex === row.index"
                      @click.stop="reparseSingleImage(row)"
                    >
                      重识
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty
                v-else-if="previewDialog.imageParseDetails?.summary?.status !== 'parsing'"
                description="暂无识图结果"
              />
            </div>
          </el-tab-pane>
        </el-tabs>
        </template>
      </div>
      <template #footer>
        <el-button @click="previewDialog.visible = false">关闭</el-button>
        <el-button
          v-if="canManage && previewDialog.row"
          @click="reparse(previewDialog.row, 'default')"
        >
          重新解析(v2)
        </el-button>
        <el-button
          v-if="canManage && previewDialog.row"
          type="warning"
          plain
          @click="reparse(previewDialog.row, 'enhanced')"
        >
          加强识图(Vision)
        </el-button>
        <el-button
          v-if="canManage && previewDialog.row && previewDialog.activeTab === 'digest'"
          type="primary"
          plain
          :loading="rebuildingDigestId === previewDialog.row?.id"
          @click="rebuildDigest(previewDialog.row)"
        >
          重建摘要
        </el-button>
        <el-button v-if="canManage && previewDialog.row" @click="reindexRag(previewDialog.row)">重建词法索引</el-button>
        <el-button
          v-if="canManage && vectorEmbedEnabled && previewDialog.row"
          @click="reindexAll(previewDialog.row)"
        >
          重建全部索引
        </el-button>
        <el-button
          v-if="canManage && vectorEmbedEnabled && previewDialog.row"
          @click="reindexVector(previewDialog.row)"
        >
          重建向量
        </el-button>
        <el-button v-if="previewDialog.row" type="primary" @click="downloadDoc(previewDialog.row)">下载原文件</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="chunkDrawer.visible" :title="chunkDrawer.title" size="82%" destroy-on-close>
      <div v-if="chunkDrawer.meta" class="chunk-drawer-meta">
        <el-tag size="small" type="info">约 {{ chunkDrawer.meta.char_count || 0 }} 字</el-tag>
        <el-tag v-if="chunkDrawer.meta.has_vector" size="small" type="success">含向量</el-tag>
        <el-tag v-else size="small">仅词法</el-tag>
      </div>
      <KnowledgeChunkText :text="chunkDrawer.text" :max-height="0" />
    </el-drawer>

    <el-drawer
      v-model="imageParseDrawer.visible"
      :title="imageParseDrawer.title"
      size="72%"
      destroy-on-close
    >
        <div v-if="imageParseDrawer.row" class="image-parse-drawer">
        <div class="image-parse-drawer-meta">
          <el-tag size="small">第 {{ imageParseDrawer.row.display_index ?? (imageParseDrawer.row.index + 1) }} 张</el-tag>
          <el-tag v-if="imageParseDrawer.row.page != null" size="small" type="info">第 {{ imageParseDrawer.row.page }} 页</el-tag>
          <el-tag v-if="imageParseDrawer.row.section_title" size="small">{{ imageParseDrawer.row.section_title }}</el-tag>
        </div>
        <div v-if="imageThumbUrl(imageParseDrawer.row.index)" class="image-parse-drawer-preview">
          <img
            :src="imageThumbUrl(imageParseDrawer.row.index)"
            class="image-parse-drawer-img"
            alt="文档原图"
          />
        </div>
        <div v-if="imageParseDrawer.row.ocr_preview && !imageParseDrawer.row.ocr_low_quality" class="image-parse-block">
          <h4>OCR 结果</h4>
          <pre class="image-parse-text">{{ imageParseDrawer.row.ocr_preview }}</pre>
        </div>
        <el-alert
          v-else-if="imageParseDrawer.row.ocr_low_quality && imageParseDrawer.row.vision_preview"
          type="info"
          :closable="false"
          show-icon
          title="已忽略低质量 OCR"
          description="该图 OCR 结果过短或无有效文字，已忽略；复杂界面以 Vision 读图为准。"
          class="image-parse-ocr-hint"
        />
        <div v-if="imageParseDrawer.row.vision_preview" class="image-parse-block">
          <h4>Vision 读图</h4>
          <pre class="image-parse-text">{{ imageParseDrawer.row.vision_preview }}</pre>
        </div>
        <div v-if="imageParseDrawer.row.merged_preview" class="image-parse-block">
          <h4>入库正文（合并）</h4>
          <pre class="image-parse-text">{{ imageParseDrawer.row.merged_preview }}</pre>
        </div>
        <el-alert
          v-if="imageParseDrawer.row.ocr_error || imageParseDrawer.row.vision_error"
          type="error"
          :closable="false"
          show-icon
          title="识图错误"
          :description="[imageParseDrawer.row.ocr_error, imageParseDrawer.row.vision_error].filter(Boolean).join('；')"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { knowledgeApi } from '@/api/modules/knowledge.js'
import KnowledgeChunkText from '@/modules/knowledge/components/KnowledgeChunkText.vue'
import KnowledgeDigestView from '@/modules/knowledge/components/KnowledgeDigestView.vue'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { useKnowledgePermissions } from '@/modules/knowledge/composables/useKnowledgePermissions.js'

const TEMPLATE_TYPES = new Set(['report_template', 'plan_template', 'quality_pptx_template'])

const route = useRoute()
const router = useRouter()
const folderId = computed(() => Number(route.params.folderId))
const projectId = computed(() => ProjectStore().projectInfo?.id)
const { canEdit: canManage, canExecute: canRunKnowledge } = useKnowledgePermissions()

const folder = ref(null)
const docTypes = ref([])
const vectorEmbedEnabled = ref(false)
const loading = ref(false)
const docs = ref([])
const page = ref(1)
const size = ref(20)
const total = ref(0)
const filters = ref({ doc_type: '', keyword: '' })
const uploadDialog = ref({ visible: false, file: null, doc_type: 'other', title: '', uploading: false })
const PARSE_POLL_INTERVAL_MS = 5000

const previewDialog = ref({
  visible: false,
  loading: false,
  refreshing: false,
  title: '',
  activeTab: 'content',
  text: '',
  format: 'plain',
  sections: [],
  sheets: [],
  outline: [],
  parseWarnings: [],
  meta: null,
  row: null,
  digestText: '',
  digestCharCount: 0,
  digestUpdatedAt: null,
  chunks: [],
  chunksLoading: false,
  chunksLoaded: false,
  chunkTotal: 0,
  embedMode: 'inherit',
  imageParseDetails: null,
  imageThumbnails: {},
  imageThumbnailsLoading: false,
  imageThumbnailsLoadedFor: null
})
const chunkDrawer = ref({ visible: false, title: '', text: '', meta: null })
const imageParseDrawer = ref({ visible: false, title: '', row: null })
const reparsingImageIndex = ref(null)
const stoppingImageParse = ref(false)
const embedModeOptions = ref([
  { value: 'inherit', label: '跟随项目' },
  { value: 'lexical_only', label: '仅词法索引' },
  { value: 'vector', label: '启用向量' },
  { value: 'none', label: '不建索引' }
])
let parsePollTimer = null
const batchJob = ref({ running: false, kind: '', current: 0, total: 0, label: '' })
const reindexingLexicalId = ref(null)
const reindexingVectorId = ref(null)
const rebuildingDigestId = ref(null)
const docTableRef = ref(null)
const selectedDocs = ref([])
const deleteMode = ref('logical')

const batchProgressPercent = computed(() => {
  if (!batchJob.value.total) return 0
  return Math.min(100, Math.round((batchJob.value.current / batchJob.value.total) * 100))
})

const previewLoadingHint = computed(() => {
  const row = previewDialog.value.row
  const chars = Number(row?.char_count || 0)
  const images = Number(row?.image_parse?.total || 0)
  if (chars >= 12000 || images >= 20) {
    return '文档较大或含较多图片，首次加载可能需要 10～30 秒，请稍候…'
  }
  if (row?.parse_status === 'parsing' || row?.parse_status === 'pending') {
    return '文档仍在后台解析中，加载完成后将展示已解析部分…'
  }
  return '正在读取解析结果与分块信息…'
})

const ragStats = computed(() => {
  const ready = docs.value.filter(d => d.parse_status === 'ready')
  const indexed = ready.filter(d => d.embed_status === 'ready')
  const needsIndex = ready.filter(d => d.embed_status !== 'ready' && d.embed_status !== 'indexing')
  const indexing = ready.filter(d => d.embed_status === 'indexing')
  return {
    ready: ready.length,
    indexed: indexed.length,
    needsIndex: needsIndex.length,
    indexing: indexing.length
  }
})

const vectorStats = computed(() => {
  if (!vectorEmbedEnabled.value) {
    return { ready: 0, indexed: 0, needsVector: 0 }
  }
  const ready = docs.value.filter(
    (d) => d.parse_status === 'ready' && d.embed_status === 'ready'
  )
  const indexed = ready.filter((d) => d.vector_status === 'ready')
  const needsVector = ready.filter(
    (d) => d.vector_status !== 'ready' && d.vector_status !== 'indexing'
  )
  return {
    ready: ready.length,
    indexed: indexed.length,
    needsVector: needsVector.length
  }
})

function lexicalLabel(s) {
  return { none: '未索引', ready: '已索引', indexing: '索引中' }[s] || s || '—'
}

function lexicalTag(s) {
  return { ready: 'success', indexing: 'warning' }[s] || 'info'
}

function vectorLabel(s) {
  return { none: '未启用', ready: '已索引', indexing: '索引中', pending: '待索引', failed: '失败' }[s] || s || '—'
}

function vectorTag(s) {
  return { ready: 'success', indexing: 'warning', failed: 'danger', pending: 'info' }[s] || 'info'
}

async function saveEmbedMode() {
  const row = previewDialog.value.row
  if (!row?.id || !projectId.value) return
  try {
    const res = await knowledgeApi.updateDocumentEmbedMode(row.id, previewDialog.value.embedMode, projectId.value)
    const data = res.data || {}
    previewDialog.value.meta = { ...previewDialog.value.meta, ...data }
    previewDialog.value.embedMode = data.embed_mode || previewDialog.value.embedMode
    ElMessage.success(res.message || 'Embedding 策略已更新')
    await loadDocs(true)
  } catch (e) {
    ElMessage.error(e?.message || '更新 Embedding 策略失败')
    previewDialog.value.embedMode = previewDialog.value.meta?.embed_mode || 'inherit'
  }
}

function digestLabel(s) {
  return { ready: '已有', none: '无', indexing: '生成中', failed: '失败' }[s] || '无'
}

function digestTag(s) {
  return { ready: 'success', indexing: 'warning', failed: 'danger' }[s] || 'info'
}

const chunksTabLabel = computed(() => {
  const n = previewDialog.value.chunkTotal || previewDialog.value.chunks.length
  return n ? `分块 (${n})` : '分块'
})

const imageParseTabVisible = computed(() => {
  const total = previewDialog.value.imageParseDetails?.summary?.total
    || previewDialog.value.meta?.image_parse?.total
  return Number(total) > 0
})

const imageParseTabLabel = computed(() => {
  const total = previewDialog.value.imageParseDetails?.summary?.total
    || previewDialog.value.meta?.image_parse?.total
    || 0
  return total ? `识图 (${total})` : '识图'
})

const imageParseJobRunning = computed(() => {
  const st = previewDialog.value.imageParseDetails?.summary?.status
    || previewDialog.value.meta?.image_parse?.status
  return st === 'parsing'
})

const imageParseSummaryText = computed(() => {
  const s = previewDialog.value.imageParseDetails?.summary
  if (!s?.total) return ''
  const engineLabel = s.ocr_engine_label || s.ocr_engine
  const parts = [
    s.mode_label ? `模式：${s.mode_label}` : '',
    s.ocr_ok != null ? `OCR 成功 ${s.ocr_ok}/${s.total}` : '',
    s.vision_ok != null ? `Vision 成功 ${s.vision_ok}/${s.total}` : '',
    engineLabel ? `引擎：${engineLabel}` : ''
  ].filter(Boolean)
  return parts.join(' · ')
})

function imageParseStatusText(row, kind) {
  const parsing = imageParseJobRunning.value
  const status = kind === 'ocr' ? row?.ocr_status : row?.vision_status
  const ok = kind === 'ocr' ? row?.ocr_ok : row?.vision_ok
  if (ok === true || status === 'success') return '成功'
  if (status === 'skipped') return '跳过'
  if (parsing && status !== 'success' && status !== 'skipped' && ok !== true) return '识别中'
  if (ok === false || status === 'failed') return '失败'
  if (status === 'processing' || status === 'pending') return '识别中'
  return '—'
}

function imageParseStatusTag(row, kind) {
  const text = imageParseStatusText(row, kind)
  if (text === '成功') return { type: 'success' }
  if (text === '跳过') return { type: 'info' }
  if (text === '识别中') return { type: 'warning' }
  if (text === '失败') return { type: 'danger' }
  return { type: 'info', effect: 'plain' }
}

async function stopImageParse() {
  const docId = previewDialog.value.row?.id
  if (!docId) return
  stoppingImageParse.value = true
  try {
    await knowledgeApi.stopDocumentImageParse(docId, projectId.value)
    ElMessage.success('已请求停止识图')
    await loadDocs()
    await syncPreviewFromDocs()
  } catch (e) {
    ElMessage.error(e?.message || '停止识图失败')
  } finally {
    stoppingImageParse.value = false
  }
}

async function reparseSingleImage(row) {
  const docId = previewDialog.value.row?.id
  if (!docId || row?.index == null) return
  reparsingImageIndex.value = row.index
  try {
    await knowledgeApi.reparseDocumentImage(docId, row.index, projectId.value)
    ElMessage.success('已提交单张识图，请稍候刷新')
    await loadDocs()
    startParsePolling()
    await syncPreviewFromDocs()
  } catch (e) {
    ElMessage.error(e?.message || '单张识图失败')
  } finally {
    reparsingImageIndex.value = null
  }
}

function imageParseRowPreview(row) {
  const text = row?.merged_preview || row?.vision_preview || row?.ocr_preview || ''
  if (!text) return row?.has_result ? '（无预览文本）' : '—'
  return text.length > 120 ? `${text.slice(0, 120)}…` : text
}

function imageThumbUrl(index) {
  if (index == null) return ''
  return previewDialog.value.imageThumbnails?.[index] || ''
}

async function loadImageThumbnails(force = false) {
  const docId = previewDialog.value.row?.id
  if (!docId || !projectId.value) return
  const total = previewDialog.value.imageParseDetails?.summary?.total
    || previewDialog.value.meta?.image_parse?.total
    || 0
  if (!total) return
  if (!force && previewDialog.value.imageThumbnailsLoadedFor === docId) return
  previewDialog.value.imageThumbnailsLoading = true
  try {
    const res = await knowledgeApi.fetchDocumentImageThumbnails(docId, projectId.value, { maxEdge: 480 })
    const map = {}
    for (const item of res.data?.items || []) {
      if (item?.index != null && item.data_url) {
        map[item.index] = item.data_url
      }
    }
    previewDialog.value.imageThumbnails = map
    previewDialog.value.imageThumbnailsLoadedFor = docId
  } catch {
    previewDialog.value.imageThumbnails = {}
  } finally {
    previewDialog.value.imageThumbnailsLoading = false
  }
}

function openImageParseDetail(row) {
  if (!imageThumbUrl(row.index)) {
    loadImageThumbnails()
  }
  const n = row.display_index ?? (row.index + 1)
  imageParseDrawer.value = {
    visible: true,
    title: `识图详情 · 第 ${n} 张`,
    row
  }
}

function chunkPreviewText(row) {
  const full = row.text || row.chunk_text || row.text_preview || ''
  return full.length > 1200 ? `${full.slice(0, 1200)}…` : full
}

function openChunkDetail(row) {
  chunkDrawer.value = {
    visible: true,
    title: `分块 #${(row.chunk_index ?? 0) + 1}${row.section_title ? ` · ${row.section_title}` : ''}`,
    text: row.text || row.text_preview || '',
    meta: {
      char_count: row.char_count,
      has_vector: row.has_vector
    }
  }
}

async function loadDocumentChunks(force = false) {
  const row = previewDialog.value.row
  if (!row?.id || !projectId.value) return
  if (previewDialog.value.chunksLoaded && !force) return
  previewDialog.value.chunksLoading = true
  try {
    const res = await knowledgeApi.listDocumentChunks(row.id, projectId.value, { size: 100 })
    const data = res.data || {}
    previewDialog.value.chunks = data.items || []
    previewDialog.value.chunkTotal = data.total || data.chunk_count || previewDialog.value.chunks.length
    previewDialog.value.chunksLoaded = true
    if (previewDialog.value.meta) {
      previewDialog.value.meta.embed_status = data.embed_status || previewDialog.value.meta.embed_status
    }
  } catch (e) {
    previewDialog.value.chunks = []
    ElMessage.error(e?.message || '加载分块失败')
  } finally {
    previewDialog.value.chunksLoading = false
  }
}

function onPreviewTabChange(name) {
  if (name === 'chunks') {
    loadDocumentChunks()
  }
}

function goSearchInFolder() {
  router.push({
    path: '/ai-knowledge/search',
    query: { folder_id: String(folderId.value) }
  })
}

function goQaInFolder() {
  router.push({
    path: '/ai-knowledge/qa',
    query: { folder_id: String(folderId.value), mode: 'smart' }
  })
}

async function runBatchJob(kind, targets, runner, successLabel) {
  if (!targets.length) {
    ElMessage.info(`没有需要${successLabel}的文档`)
    return
  }
  try {
    await ElMessageBox.confirm(`将为 ${targets.length} 篇文档${successLabel}，是否继续？`, `批量${successLabel}`)
  } catch {
    return
  }
  batchJob.value = {
    running: true,
    kind,
    current: 0,
    total: targets.length,
    label: `0/${targets.length}`
  }
  let ok = 0
  try {
    for (let i = 0; i < targets.length; i += 1) {
      const row = targets[i]
      batchJob.value.current = i
      batchJob.value.label = `${i}/${targets.length} · ${row.title || row.file_name || row.id}`
      try {
        await runner(row)
        ok += 1
      } catch {
        /* continue next */
      }
    }
    batchJob.value.current = targets.length
    batchJob.value.label = `${ok}/${targets.length} 完成`
    ElMessage.success(`已处理 ${ok}/${targets.length} 篇文档（${successLabel}）`)
    await loadDocs(true)
    startParsePolling()
  } finally {
    setTimeout(() => {
      batchJob.value = { running: false, kind: '', current: 0, total: 0, label: '' }
    }, 800)
  }
}

function hasParsingDocs() {
  return (
    docs.value.some((d) => d.parse_status === 'parsing' || d.parse_status === 'pending') ||
    docs.value.some(isImageParsingDoc)
  )
}

function hasIndexingDocs() {
  return docs.value.some(
    (d) =>
      d.parse_status === 'ready' &&
      (d.embed_status === 'indexing' ||
        d.vector_status === 'indexing' ||
        d.digest_status === 'indexing')
  )
}

function startParsePolling() {
  if (parsePollTimer) return
  parsePollTimer = setInterval(async () => {
    if (!hasParsingDocs() && !hasIndexingDocs()) {
      stopParsePolling()
      return
    }
    await loadDocs(true)
  }, PARSE_POLL_INTERVAL_MS)
}

function stopParsePolling() {
  if (parsePollTimer) {
    clearInterval(parsePollTimer)
    parsePollTimer = null
  }
}

async function syncPreviewFromDocs() {
  if (!previewDialog.value.visible || !previewDialog.value.row?.id) return
  if (previewDialog.value.loading || previewDialog.value.refreshing) return
  const fresh = docs.value.find((d) => d.id === previewDialog.value.row.id)
  if (!fresh) return
  const prevDigest = previewDialog.value.meta?.digest_status
  const prevParse = previewDialog.value.meta?.parse_status
  previewDialog.value.row = fresh
  if (previewDialog.value.meta) {
    previewDialog.value.meta = {
      ...previewDialog.value.meta,
      parse_status: fresh.parse_status,
      digest_status: fresh.digest_status,
      digest_error: fresh.digest_error,
      embed_status: fresh.embed_status,
      vector_status: fresh.vector_status,
      sections_version: fresh.sections_version ?? previewDialog.value.meta.sections_version,
      structured_kind: fresh.structured_kind ?? previewDialog.value.meta.structured_kind,
      structured_profile: fresh.structured_profile ?? previewDialog.value.meta.structured_profile,
      image_parse: fresh.image_parse ?? previewDialog.value.meta.image_parse
    }
  }
  const prevImageParse = previewDialog.value.meta?.image_parse?.status
  const freshImageParse = fresh.image_parse?.status
  const shouldLiveRefreshImageParse =
    previewDialog.value.visible &&
    freshImageParse === 'parsing' &&
    (previewDialog.value.activeTab === 'image_parse' || imageParseTabVisible.value)
  const shouldRefreshPreview =
    (prevDigest === 'indexing' && (fresh.digest_status === 'ready' || fresh.digest_status === 'failed')) ||
    (prevParse === 'parsing' && fresh.parse_status === 'ready') ||
    (prevImageParse === 'parsing' && freshImageParse && freshImageParse !== 'parsing') ||
    shouldLiveRefreshImageParse
  if (shouldRefreshPreview) {
    previewDialog.value.refreshing = true
    try {
      const res = await knowledgeApi.previewDocument(fresh.id, projectId.value)
      const data = res.data || {}
      previewDialog.value.digestText = data.digest_text || ''
      previewDialog.value.digestCharCount = data.digest_char_count || 0
      previewDialog.value.digestUpdatedAt = data.digest_updated_at || null
      previewDialog.value.outline = data.outline || []
      previewDialog.value.parseWarnings = data.parse_warnings || []
      previewDialog.value.text = data.preview_text || previewDialog.value.text
      previewDialog.value.format = data.preview_format || previewDialog.value.format
      previewDialog.value.sections = data.preview_sections || previewDialog.value.sections
      previewDialog.value.sheets = data.preview_sheets || previewDialog.value.sheets
      previewDialog.value.imageParseDetails = data.image_parse_details || null
      previewDialog.value.meta = { ...previewDialog.value.meta, ...data }
      previewDialog.value.imageThumbnails = {}
      previewDialog.value.imageThumbnailsLoadedFor = null
      if (previewDialog.value.activeTab === 'image_parse') {
        await loadImageThumbnails(true)
      }
    } catch {
      /* 轮询刷新预览失败可忽略 */
    } finally {
      previewDialog.value.refreshing = false
    }
  }
}

function structuredProfileLabel(profile) {
  return {
    zentao_bug: '禅道 Bug',
    iteration_plan: '迭代计划',
    generic_table: '通用表格'
  }[profile] || profile
}

function sheetTableColumns(sheet) {
  const rows = sheet?.rows || []
  if (!rows.length) return []
  const colCount = Math.max(...rows.map((r) => r.length))
  const header = rows[0] || []
  return Array.from({ length: colCount }, (_, i) => ({
    prop: `c${i}`,
    label: header[i] != null && String(header[i]).trim() !== '' ? String(header[i]) : `列${i + 1}`
  }))
}

function sheetTableRows(sheet) {
  const rows = sheet?.rows || []
  if (rows.length <= 1) {
    return rows.map((r) => {
      const row = {}
      r.forEach((cell, i) => { row[`c${i}`] = cell })
      return row
    })
  }
  return rows.slice(1).map((r) => {
    const row = {}
    r.forEach((cell, i) => { row[`c${i}`] = cell })
    return row
  })
}

function guessDocType(fileName) {
  const lower = (fileName || '').toLowerCase()
  if (/bug|缺陷|zentao|禅道/.test(lower)) return 'bug_export'
  if (/测试计划|test.?plan/.test(lower)) return 'test_plan'
  if (/迭代|iteration/.test(lower) && /\.xlsx?$/i.test(lower)) return 'iteration_plan'
  if (/需求|requirement/.test(lower)) return 'requirement'
  return 'other'
}
const maxFileMb = ref(20)

function formatFileSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatTime(v) {
  if (!v) return '-'
  return String(v).replace('T', ' ').slice(0, 19)
}

function parseLabel(s) {
  return { pending: '待解析', parsing: '解析中', ready: '就绪', failed: '失败' }[s] || s
}

function parseTag(s) {
  return { ready: 'success', failed: 'danger', parsing: 'warning' }[s] || 'info'
}

function imageParseLabel(ip) {
  if (!ip?.status) return ''
  const total = ip.total || 0
  const done = ip.completed || 0
  const map = {
    pending: `识图排队 ${total} 张`,
    parsing: `识图中 ${done}/${total}`,
    ready: `识图完成 ${total} 张`,
    partial: `识图部分 ${done}/${total}`,
    cancelled: `识图已停止 ${done}/${total}`,
    skipped: '未识图',
    failed: '识图失败'
  }
  return map[ip.status] || ip.status
}

function imageParseTag(ip) {
  const s = ip?.status
  return { ready: 'success', partial: 'warning', failed: 'danger', parsing: 'warning', pending: 'info', cancelled: 'info' }[s] || 'info'
}

function isImageParsingDoc(row) {
  const s = row?.image_parse?.status
  return s === 'pending' || s === 'parsing'
}

function isTemplateType(t) {
  return TEMPLATE_TYPES.has(t)
}

function goBack() {
  router.push('/ai-knowledge/folders')
}

async function loadMeta() {
  try {
    const res = await knowledgeApi.getMeta()
    docTypes.value = res.data?.doc_types || []
    maxFileMb.value = res.data?.max_file_mb || 20
    if (res.data?.knowledge_delete_mode) {
      deleteMode.value = res.data.knowledge_delete_mode
    }
  } catch {
    docTypes.value = []
  }
}

async function loadProjectSettings() {
  if (!projectId.value) {
    vectorEmbedEnabled.value = false
    return
  }
  try {
    const res = await knowledgeApi.getSettings(projectId.value)
    vectorEmbedEnabled.value = res.data?.values?.vector_embed_enabled === true
  } catch {
    vectorEmbedEnabled.value = false
  }
}

async function loadFolder() {
  if (!projectId.value || !folderId.value) return
  const res = await knowledgeApi.listFolders(projectId.value)
  folder.value = (res.data?.items || []).find((f) => f.id === folderId.value) || null
}

async function loadDocs(silent = false) {
  if (!projectId.value || !folderId.value) {
    if (!silent) ElMessage.warning('请先选择项目')
    return
  }
  if (!silent) loading.value = true
  try {
    const params = { folder_id: folderId.value, page: page.value, size: size.value }
    if (filters.value.doc_type) params.doc_type = filters.value.doc_type
    if (filters.value.keyword) params.keyword = filters.value.keyword
    const res = await knowledgeApi.listDocuments(projectId.value, params)
    docs.value = res.data?.items || []
    total.value = res.data?.total || 0
    if (res.data?.delete_mode) {
      deleteMode.value = res.data.delete_mode
    }
    await syncPreviewFromDocs()
    if (hasParsingDocs() || hasIndexingDocs()) startParsePolling()
    else stopParsePolling()
  } catch (e) {
    if (!silent) ElMessage.error(e?.message || '加载失败')
  } finally {
    if (!silent) loading.value = false
  }
}

function onFilePick(uploadFile) {
  const raw = uploadFile.raw
  const limit = maxFileMb.value * 1024 * 1024
  if (raw && raw.size > limit) {
    ElMessage.warning(`文件超过 ${maxFileMb.value}MB 限制（当前 ${formatFileSize(raw.size)}）`)
    return
  }
  uploadDialog.value = {
    visible: true,
    file: uploadFile.raw,
    doc_type: guessDocType(raw?.name),
    title: '',
    uploading: false
  }
}

async function confirmUpload() {
  const file = uploadDialog.value.file
  if (!file) return
  if (!uploadDialog.value.doc_type) {
    ElMessage.warning('请选择文档类型')
    return
  }
  uploadDialog.value.uploading = true
  try {
    const res = await knowledgeApi.uploadDocument(projectId.value, file, {
      doc_type: uploadDialog.value.doc_type,
      folder_id: folderId.value,
      title: uploadDialog.value.title || undefined
    })
    if (res.message && res.message !== '上传成功') {
      ElMessage.warning(res.message)
    } else {
      ElMessage.success('上传成功，正在后台解析并建立词法索引')
    }
    uploadDialog.value.visible = false
    await loadDocs()
    await loadFolder()
    startParsePolling()
  } catch (e) {
    const msg = e?.message || '上传失败'
    if (/timeout/i.test(msg)) {
      ElMessage.error('上传超时：文件较大或网络较慢，请稍后刷新列表确认是否已成功；或重新上传')
    } else {
      ElMessage.error(msg)
    }
  } finally {
    uploadDialog.value.uploading = false
  }
}

async function batchSelectedReparse() {
  if (!selectedDocs.value.length || !projectId.value) return
  try {
    await ElMessageBox.confirm(
      `将对已选 ${selectedDocs.value.length} 篇文档提交 v2 重新解析（解析与索引在后台进行），是否继续？`,
      '批量重新解析',
      { type: 'warning' }
    )
    batchJob.value = { running: true, kind: 'reparse', current: 0, total: 1, label: '提交批量重新解析…' }
    const ids = selectedDocs.value.map((d) => d.id)
    await knowledgeApi.reparseDocumentsBatch({ folderId: folderId.value, documentIds: ids }, projectId.value)
    batchJob.value = { running: true, kind: 'reparse', current: 1, total: 1, label: '已提交，后台解析中…' }
    ElMessage.success('已提交批量重新解析')
    await loadDocs()
    startParsePolling()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.message || '批量重新解析失败')
  } finally {
    setTimeout(() => {
      batchJob.value = { running: false, kind: '', current: 0, total: 0, label: '' }
    }, 800)
  }
}

async function reparse(row, imageMode = 'default') {
  try {
    await knowledgeApi.reparseDocument(row.id, projectId.value, { imageMode })
    const tip = imageMode === 'enhanced' ? '已提交加强识图解析' : '已提交重新解析'
    ElMessage.success(tip)
    await loadDocs()
    startParsePolling()
  } catch (e) {
    ElMessage.error(e?.message || '解析失败')
  }
}

async function reindexRag(row) {
  reindexingLexicalId.value = row.id
  try {
    const res = await knowledgeApi.reindexDocumentRag(row.id, projectId.value)
    ElMessage.success(res.message || '词法索引已在后台处理')
    await loadDocs(true)
    if (previewDialog.value.visible && previewDialog.value.row?.id === row.id) {
      previewDialog.value.chunksLoaded = false
      previewDialog.value.meta = {
        ...previewDialog.value.meta,
        embed_status: res.data?.embed_status || 'indexing',
        vector_status: res.data?.vector_status || previewDialog.value.meta?.vector_status
      }
      if (previewDialog.value.activeTab === 'chunks') {
        await loadDocumentChunks(true)
      }
    }
    startParsePolling()
  } catch (e) {
    ElMessage.error(e?.message || '重建词法索引失败')
  } finally {
    reindexingLexicalId.value = null
  }
}

async function reindexVector(row) {
  reindexingVectorId.value = row.id
  try {
    const res = await knowledgeApi.reindexDocumentVector(row.id, projectId.value)
    ElMessage.success(res.message || '向量索引已在后台处理')
    await loadDocs(true)
    if (previewDialog.value.visible && previewDialog.value.row?.id === row.id) {
      previewDialog.value.meta = {
        ...previewDialog.value.meta,
        vector_status: res.data?.vector_status || 'indexing',
        vector_model: res.data?.vector_model
      }
      previewDialog.value.chunksLoaded = false
      if (previewDialog.value.activeTab === 'chunks') {
        await loadDocumentChunks(true)
      }
    }
    startParsePolling()
  } catch (e) {
    ElMessage.error(e?.message || '重建向量索引失败')
  } finally {
    reindexingVectorId.value = null
  }
}

async function reindexAll(row) {
  try {
    const res = await knowledgeApi.reindexDocumentAll(row.id, projectId.value)
    ElMessage.success(res.message || '全部索引已在后台处理')
    await loadDocs(true)
    if (previewDialog.value.visible && previewDialog.value.row?.id === row.id) {
      previewDialog.value.chunksLoaded = false
      previewDialog.value.meta = {
        ...previewDialog.value.meta,
        embed_status: res.data?.embed_status || 'indexing',
        vector_status: res.data?.vector_status || previewDialog.value.meta?.vector_status
      }
      if (previewDialog.value.activeTab === 'chunks') {
        await loadDocumentChunks(true)
      }
    }
    startParsePolling()
  } catch (e) {
    ElMessage.error(e?.message || '重建全部索引失败')
  }
}

async function batchReindexRag() {
  const targets = docs.value.filter(
    (d) => d.parse_status === 'ready' && d.embed_status !== 'ready' && d.embed_status !== 'indexing'
  )
  await runBatchJob(
    'lexical',
    targets,
    (row) => knowledgeApi.reindexDocumentRag(row.id, projectId.value),
    '重建词法索引'
  )
}

async function batchReindexVector() {
  const targets = docs.value.filter(
    (d) =>
      d.parse_status === 'ready' &&
      d.embed_status === 'ready' &&
      d.vector_status !== 'ready' &&
      d.vector_status !== 'indexing'
  )
  await runBatchJob(
    'vector',
    targets,
    (row) => knowledgeApi.reindexDocumentVector(row.id, projectId.value),
    '重建向量索引'
  )
}

async function batchReindexAll() {
  const targets = docs.value.filter((d) => d.parse_status === 'ready')
  await runBatchJob(
    'all',
    targets,
    (row) => knowledgeApi.reindexDocumentAll(row.id, projectId.value),
    '重建全部索引'
  )
}

function onDocSelectionChange(rows) {
  selectedDocs.value = rows || []
}

function clearSelection() {
  docTableRef.value?.clearSelection?.()
  selectedDocs.value = []
}

async function batchSelectedReindexRag() {
  await runBatchJob(
    'lexical',
    selectedDocs.value.filter((d) => d.parse_status === 'ready'),
    (row) => knowledgeApi.reindexDocumentRag(row.id, projectId.value),
    '重建词法索引'
  )
}

async function batchSelectedReindexVector() {
  await runBatchJob(
    'vector',
    selectedDocs.value.filter((d) => d.parse_status === 'ready' && d.embed_status === 'ready'),
    (row) => knowledgeApi.reindexDocumentVector(row.id, projectId.value),
    '重建向量索引'
  )
}

async function batchSelectedReindexAll() {
  await runBatchJob(
    'all',
    selectedDocs.value.filter((d) => d.parse_status === 'ready'),
    (row) => knowledgeApi.reindexDocumentAll(row.id, projectId.value),
    '重建全部索引'
  )
}

async function batchSelectedRebuildDigest() {
  await runBatchJob(
    'digest',
    selectedDocs.value.filter(
      (d) => d.parse_status === 'ready' && d.digest_status !== 'indexing'
    ),
    (row) => knowledgeApi.rebuildDocumentDigest(row.id, projectId.value),
    '重建摘要'
  )
}

function getDeleteConfirmMessage(title, count = 1) {
  const subject = count > 1 ? `选中的 ${count} 篇文档` : `文档「${title}」`
  if (deleteMode.value === 'physical') {
    return `将永久删除${subject}及其源文件、分块与向量索引，此操作不可恢复，确定继续吗？`
  }
  return `将从列表中隐藏${subject}（逻辑删除，源文件仍保留在存储中），确定继续吗？`
}

async function batchSelectedDelete() {
  const targets = [...selectedDocs.value]
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage('', targets.length), '批量删除', { type: 'warning' })
  } catch {
    return
  }
  let ok = 0
  for (const row of targets) {
    try {
      await knowledgeApi.deleteDocument(row.id, projectId.value)
      ok += 1
    } catch {
      /* next */
    }
  }
  ElMessage.success(`已删除 ${ok}/${targets.length} 篇`)
  clearSelection()
  await loadDocs(true)
}

async function rebuildDigest(row) {
  if (!row?.id || rebuildingDigestId.value === row.id) return
  rebuildingDigestId.value = row.id
  try {
    const res = await knowledgeApi.rebuildDocumentDigest(row.id, projectId.value)
    ElMessage.success(res.message || '摘要已在后台生成')
    await loadDocs(true)
    if (previewDialog.value.visible && previewDialog.value.row?.id === row.id) {
      previewDialog.value.meta = {
        ...previewDialog.value.meta,
        digest_status: res.data?.digest_status || 'indexing',
        digest_error: null
      }
    }
    startParsePolling()
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.data?.detail
    ElMessage.error(typeof detail === 'string' && detail ? detail : (e?.message || '重建摘要失败'))
  } finally {
    rebuildingDigestId.value = null
  }
}

async function previewDoc(row, tab = 'content') {
  previewDialog.value = {
    visible: true,
    loading: true,
    refreshing: false,
    title: `文档详情：${row.title || row.file_name}`,
    activeTab: tab,
    text: '',
    format: 'plain',
    sections: [],
    sheets: [],
    outline: [],
    parseWarnings: [],
    meta: null,
    row,
    digestText: '',
    digestCharCount: 0,
    digestUpdatedAt: null,
    chunks: [],
    chunksLoading: false,
    chunksLoaded: false,
    chunkTotal: row.chunk_count || 0,
    embedMode: row.embed_mode || 'inherit',
    imageParseDetails: null,
    imageThumbnails: {},
    imageThumbnailsLoading: false,
    imageThumbnailsLoadedFor: null
  }
  try {
    const res = await knowledgeApi.previewDocument(row.id, projectId.value)
    const data = res.data || {}
    previewDialog.value.meta = data
    previewDialog.value.imageParseDetails = data.image_parse_details || null
    previewDialog.value.text = data.preview_text || ''
    previewDialog.value.format = data.preview_format || 'plain'
    previewDialog.value.sections = data.preview_sections || []
    previewDialog.value.sheets = data.preview_sheets || []
    previewDialog.value.outline = data.outline || []
    previewDialog.value.parseWarnings = data.parse_warnings || []
    previewDialog.value.digestText = data.digest_text || ''
    previewDialog.value.digestCharCount = data.digest_char_count || 0
    previewDialog.value.digestUpdatedAt = data.digest_updated_at || null
    previewDialog.value.imageParseDetails = data.image_parse_details || null
    previewDialog.value.embedMode = data.embed_mode || previewDialog.value.embedMode
    if (previewDialog.value.meta) {
      previewDialog.value.meta.vector_status = data.vector_status || previewDialog.value.meta.vector_status
      previewDialog.value.meta.embed_mode = data.embed_mode || previewDialog.value.meta.embed_mode
    }
    if (tab === 'chunks') {
      await loadDocumentChunks(true)
    }
    if (tab === 'image_parse' || imageParseTabVisible.value) {
      await loadImageThumbnails()
    }
  } catch (e) {
    ElMessage.error(e?.message || '预览失败')
    previewDialog.value.visible = false
  } finally {
    previewDialog.value.loading = false
  }
}

function triggerBlobDownload(blob, fileName) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName || 'download'
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadDoc(row) {
  try {
    const blob = await knowledgeApi.downloadDocument(row.id, projectId.value)
    triggerBlobDownload(blob, row.file_name || `${row.title || 'document'}`)
  } catch (e) {
    ElMessage.error(e?.message || '下载失败')
  }
}

async function setDefault(row) {
  try {
    await knowledgeApi.setDefaultTemplate(row.id, projectId.value)
    ElMessage.success('已设为默认模板')
    await loadDocs()
  } catch (e) {
    ElMessage.error(e?.message || '操作失败')
  }
}

async function removeDoc(row) {
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage(row.title), '确认', { type: 'warning' })
    await knowledgeApi.deleteDocument(row.id, projectId.value)
    ElMessage.success('已删除')
    await loadDocs()
    await loadFolder()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.message || '删除失败')
  }
}

watch(folderId, async () => {
  page.value = 1
  await loadFolder()
  await loadDocs()
})

watch(projectId, loadProjectSettings)

watch(
  () => previewDialog.value.activeTab,
  (tab) => {
    if (tab === 'image_parse' && previewDialog.value.visible) {
      loadImageThumbnails()
    }
  }
)

onMounted(async () => {
  await loadMeta()
  await loadProjectSettings()
  await loadFolder()
  await loadDocs()
})

onUnmounted(() => {
  stopParsePolling()
})
</script>

<style scoped>
.head-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.folder-title {
  font-weight: 600;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.batch-select-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  font-size: 13px;
}
.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.upload-hint {
  font-size: 12px;
  color: var(--el-color-warning);
  margin: 0 0 8px;
  text-align: left;
}
.upload-type-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  line-height: 1.4;
}
.preview-body {
  min-height: 280px;
}
.preview-loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 320px;
  padding: 48px 24px;
  text-align: center;
}
.preview-loading-icon {
  color: var(--el-color-primary);
  margin-bottom: 16px;
}
.preview-loading-title {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.preview-loading-hint {
  margin: 0;
  max-width: 360px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}
.preview-tip {
  margin-bottom: 12px;
}
.preview-warn {
  margin-bottom: 10px;
}
.outline-panel {
  padding: 4px 0;
}
.outline-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.55;
}
.outline-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 480px;
  overflow: auto;
}
.outline-item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-extra-light);
  font-size: 13px;
  line-height: 1.5;
}
.outline-title {
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.outline-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.sheet-warn {
  color: var(--el-color-warning);
}
.preview-sheets {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.sheet-block {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px;
}
.sheet-name {
  font-weight: 600;
  margin-bottom: 8px;
  font-size: 13px;
}
.sheet-more {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.preview-sections {
  /* 由弹窗 body 统一滚动，避免嵌套滚动条 */
}
.preview-section {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.preview-section:last-child {
  border-bottom: none;
}
.section-title {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.section-body {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}
.preview-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.preview-file {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.preview-chars {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.preview-text {
  margin: 0;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
}
.preview-tabs {
  margin-top: 4px;
}
.digest-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.digest-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.chunk-drawer-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.rag-alert {
  margin-bottom: 12px;
}
.rag-alert-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}
.rag-alert-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.image-parse-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.image-parse-summary {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.image-parse-actions {
  margin-bottom: 10px;
}
.image-parse-preview {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
}
.image-parse-thumb-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 54px;
  margin: 0 auto;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  overflow: hidden;
}
.image-parse-thumb-wrap.clickable {
  cursor: pointer;
}
.image-parse-thumb-wrap.clickable:hover {
  box-shadow: 0 0 0 1px var(--el-color-primary-light-5);
}
.image-parse-thumb {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  display: block;
}
.image-parse-thumb-loading,
.image-parse-thumb-empty {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.image-parse-drawer-preview {
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  text-align: center;
}
.image-parse-drawer-img {
  max-width: 100%;
  max-height: min(52vh, 520px);
  object-fit: contain;
  border-radius: 6px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}
.image-parse-drawer-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.image-parse-block h4 {
  margin: 0 0 8px;
  font-size: 13px;
}
.image-parse-text {
  margin: 0;
  padding: 12px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

<style>
.knowledge-doc-preview-dialog .el-dialog__body {
  max-height: min(78vh, 860px);
  overflow-y: auto;
}
</style>
