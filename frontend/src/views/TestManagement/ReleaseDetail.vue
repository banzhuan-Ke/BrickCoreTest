<template>
  <div class="tm-release-detail" v-loading="loading">
    <TmPremiumBanner />
    <div class="header" v-if="release">
      <div class="title-row">
        <TmBackButton @click="$router.push('/test-releases')" />
        <h2>{{ release.name }}</h2>
        <el-tag :type="releaseStatusTagType(release.status)">{{ releaseStatusLabel(release.status) }}</el-tag>
        <el-tag
          v-if="release.quality_status"
          :type="qualityStatusTagType(release.quality_status)"
        >
          质量：{{ qualityStatusLabel(release.quality_status) }}
        </el-tag>
        <span class="key">{{ release.release_key }}</span>
        <span v-if="release.owner_id" class="owner-chip">
          版本负责人：{{ formatMemberName(release.owner_id, memberNames) }}
        </span>
      </div>
      <div class="actions">
        <el-button @click="goTraceability">追溯矩阵</el-button>
        <el-button
          v-if="canQualityView"
          :loading="exportingPackage"
          @click="downloadExportPackage"
        >导出发布包</el-button>
        <template v-if="canEdit">
          <el-button @click="openEditRelease">编辑</el-button>
          <el-dropdown
            v-if="allowedReleaseTransitions(release.status).length"
            trigger="click"
            @command="doTransition"
          >
            <el-button plain class="status-btn">
              变更状态
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="t in allowedReleaseTransitions(release.status)"
                  :key="t"
                  :command="t"
                >
                  <span class="status-dd-item">
                    <el-tag size="small" :type="releaseStatusTagType(t)" effect="plain">
                      {{ releaseStatusLabel(t) }}
                    </el-tag>
                    <span class="status-dd-hint">从「{{ releaseStatusLabel(release.status) }}」迁入</span>
                  </span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button @click="seedLinks">从已有导入回填映射</el-button>
          <el-button
            v-if="releaseDeletable(release.status)"
            type="danger"
            plain
            @click="removeRelease"
          >删除版本</el-button>
        </template>
      </div>
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="概览" name="overview">
        <ReleaseAgileWorkflow
          v-if="release"
          :release="release"
          :requirements="requirements"
          :scopes="allScopesForWorkflow"
          :reviews="reviews"
          :requirement-review-done="requirementReviewDone"
          :functional-cases-ack="workflowMarks.functional_cases"
          :quality-previewed-ack="workflowMarks.quality_preview"
          :phase2="workflowPhase2"
          :phase3="workflowPhase3"
          :quality-metrics="workflowQualityMetrics"
          :quality-preview="qualityPreview"
          :workflow-mark-times="workflowMarkTimes"
          :primary-plan-id="primaryPlanId"
          :can-edit="canEdit"
          @action="onWorkflowAction"
        />
        <ReleasePublishChecklist
          v-if="canQualityView && release"
          :quality-preview="qualityPreview"
          :can-edit="canEdit"
          :loading="qualityLoading"
          :snapshot-loading="snapshotSaving"
          @refresh="onChecklistRefresh"
          @snapshot="createSnapshot"
          @goto="onChecklistGoto"
        />
        <ReleaseAutomationProgress
          v-if="release && allScopesForWorkflow.length"
          :scopes="allScopesForWorkflow"
          :phase3-progress="workflowPhase3Progress"
          :primary-plan-id="primaryPlanId"
          :can-edit="canPlanEdit && scopeEditable"
          @map="openLinks"
          @scopes="goTab('scopes')"
          @gen-automation="genAutomationForPrimaryPlan"
        />
        <div class="stat-row" v-if="overview">
          <el-card shadow="hover" class="stat-card clickable" @click="goTab('scopes')">
            <div class="stat-num">{{ overview.scope_count }}</div>
            <div class="stat-label">范围用例</div>
            <div class="stat-hint">点击查看测试范围</div>
          </el-card>
          <el-card shadow="hover" class="stat-card clickable" @click="goTab('requirements')">
            <div class="stat-num">{{ overview.requirement_count }}</div>
            <div class="stat-label">关联需求</div>
            <div class="stat-hint">点击管理需求</div>
          </el-card>
          <el-card shadow="hover" class="stat-card wide clickable" @click="goTab('scopes')">
            <div class="stat-label">风险分布</div>
            <div class="chips">
              <el-tag
                v-for="(v, k) in overview.risk_distribution"
                :key="k"
                size="small"
                :type="riskTagType(k)"
                effect="light"
              >
                {{ riskLabel(k) }}: {{ v }}
              </el-tag>
            </div>
            <div class="stat-hint">点击查看范围</div>
          </el-card>
          <el-card
            shadow="hover"
            class="stat-card clickable"
            v-if="defectStats"
            @click="goTab('defects')"
          >
            <div class="stat-num danger">{{ defectStats.open_count || 0 }}</div>
            <div class="stat-label">未关闭缺陷</div>
            <div class="stat-hint">点击查看缺陷</div>
          </el-card>
          <el-card shadow="hover" class="stat-card wide clickable" @click="goTab('scopes')">
            <div class="stat-label">自动化覆盖</div>
            <div class="chips">
              <el-tag
                v-for="(v, k) in visibleCoverage(overview.coverage_distribution)"
                :key="k"
                size="small"
                :type="coverageTagType(k)"
                effect="light"
              >
                {{ coverageLabel(k) }}: {{ v }}
              </el-tag>
            </div>
            <div class="stat-hint">点击查看范围映射</div>
          </el-card>
          <el-card shadow="hover" class="stat-card clickable" @click="goTab('plans')">
            <div class="stat-num">{{ plans.length }}</div>
            <div class="stat-label">测试计划</div>
            <div class="stat-hint">点击进入计划</div>
          </el-card>
          <el-card shadow="hover" class="stat-card clickable" @click="goTab('quality')">
            <div class="stat-label">质量门禁</div>
            <el-tag
              v-if="release.quality_status"
              :type="qualityStatusTagType(release.quality_status)"
              size="large"
            >
              {{ qualityStatusLabel(release.quality_status) }}
            </el-tag>
            <span v-else class="muted">尚未评估</span>
            <div class="stat-hint">点击打开质量</div>
          </el-card>
        </div>
        <el-empty v-if="overview && !overview.scope_count" description="尚未纳入功能用例">
          <el-button v-if="canEdit && scopeEditable" type="primary" @click="goTab('scopes'); openPickCases()">
            去纳入用例
          </el-button>
        </el-empty>
      </el-tab-pane>

      <el-tab-pane label="需求" name="requirements">
        <div class="pane-toolbar" v-if="canEdit && scopeEditable">
          <el-button type="primary" @click="openReqDialog">关联需求</el-button>
        </div>
        <el-empty v-if="!requirements.length" description="暂无关联需求">
          <el-button v-if="canEdit && scopeEditable" type="primary" @click="reqDialog = true">添加需求</el-button>
        </el-empty>
        <el-table v-else :data="requirements" border stripe>
          <el-table-column prop="requirement_key" label="编号" width="160">
            <template #default="{ row }">
              <router-link v-if="reqInternalLink(row)" :to="reqInternalLink(row)" class="inner-link">
                {{ row.requirement_key }}
              </router-link>
              <span v-else>{{ row.requirement_key }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="标题" min-width="180" />
          <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
          <el-table-column prop="url" label="链接" min-width="200">
            <template #default="{ row }">
              <a v-if="safeExternalUrl(row.url)" :href="safeExternalUrl(row.url)" target="_blank" rel="noopener noreferrer">{{ row.url }}</a>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90">
            <template #default="{ row }">
              {{ requirementTypeLabel(row) }}
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ formatTime(row.update_time) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="220" v-if="canEdit && scopeEditable">
            <template #default="{ row }">
              <el-button link type="primary" @click="openReqPreview(row)">预览</el-button>
              <el-button link type="primary" @click="openReqEdit(row)">编辑</el-button>
              <el-button
                v-if="!isProjectRequirement(row) && !reqInternalLink(row)"
                link
                type="success"
                @click="openReqUpgrade(row)"
              >升级</el-button>
              <el-button link type="danger" @click="removeReq(row)">删除</el-button>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" v-else>
            <template #default="{ row }">
              <el-button link type="primary" @click="openReqPreview(row)">预览</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="需求评审" name="req-reviews" v-if="canReviewView">
        <RequirementReview
          ref="reqReviewRef"
          embedded
          :release-id-override="releaseId"
          :project-id-override="projectId"
        />
      </el-tab-pane>

      <el-tab-pane label="测试范围" name="scopes">
        <div class="pane-toolbar">
          <el-input v-model="scopeFilters.keyword" clearable placeholder="用例标题" style="width: 180px" />
          <el-input v-model="scopeFilters.module" clearable placeholder="模块" style="width: 140px" />
          <el-select v-model="scopeFilters.risk_level" clearable placeholder="风险" style="width: 120px">
            <el-option v-for="r in riskOptions" :key="r" :label="riskLabel(r)" :value="r" />
          </el-select>
          <el-select v-model="scopeFilters.automation_status" clearable placeholder="覆盖" style="width: 120px">
            <el-option v-for="c in coverageOptions" :key="c" :label="coverageLabel(c)" :value="c" />
          </el-select>
          <ProjectMemberSelect
            v-if="projectId"
            v-model="scopeFilters.owner_id"
            :project-id="projectId"
            placeholder="负责人"
            width="160px"
          />
          <el-button type="primary" @click="loadScopes">查询</el-button>
          <el-button v-if="canEdit && scopeEditable" type="success" @click="openPickCases">纳入用例</el-button>
          <el-button
            v-if="canEdit && scopeEditable"
            :disabled="!selectedScopeIds.length"
            @click="batchDialog = true"
          >批量设置（{{ selectedScopeIds.length }}）</el-button>
          <el-button
            v-if="canEdit"
            :loading="notifyingOwners"
            @click="notifyScopeOwners"
          >通知负责人</el-button>
        </div>
        <el-empty v-if="!scopes.length" description="测试范围为空，请先纳入功能用例">
          <el-button v-if="canEdit && scopeEditable" type="primary" @click="openPickCases">纳入用例</el-button>
        </el-empty>
        <el-table
          v-else
          :data="scopes"
          border
          stripe
          row-key="id"
          @selection-change="onScopeSelectionChange"
        >
          <el-table-column
            v-if="canEdit && scopeEditable"
            type="selection"
            width="48"
            fixed="left"
          />
          <el-table-column prop="functional_case_id" label="用例ID" width="90" />
          <el-table-column prop="case_title" label="标题" min-width="200" show-overflow-tooltip />
          <el-table-column prop="case_module" label="模块" width="120" show-overflow-tooltip />
          <el-table-column prop="requirement_key" label="关联需求" min-width="140">
            <template #default="{ row }">
              <el-button
                v-if="row.requirement_key"
                link
                type="primary"
                @click="openScopeReqPreview(row)"
              >{{ row.requirement_key }}</el-button>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column prop="risk_level" label="风险" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="riskTagType(row.risk_level)" effect="light">
                {{ riskLabel(row.risk_level) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="automation_status" label="自动化" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="coverageTagType(row.automation_status)" effect="light">
                {{ coverageLabel(row.automation_status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="review_decision" label="评审" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="reviewDecisionTagType(row.review_decision)" effect="light">
                {{ reviewDecisionLabel(row.review_decision) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="owner_id" label="负责人" width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ formatMemberName(row.owner_id, memberNames) }}</template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ formatTime(row.update_time) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openLinks(row)">映射</el-button>
              <el-button
                v-if="canEdit && scopeEditable"
                link
                type="primary"
                @click="openScopeEdit(row)"
              >编辑</el-button>
              <el-button
                v-if="canEdit && scopeEditable"
                link
                type="danger"
                @click="removeScope(row)"
              >移除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="用例评审" name="reviews">
        <div class="pane-toolbar" v-if="canReviewManage && scopeEditable">
          <el-button type="primary" @click="openCreateReview">发起评审</el-button>
        </div>
        <el-empty v-if="!reviews.length" description="暂无用例评审">
          <el-button v-if="canReviewManage && scopeEditable" type="primary" @click="openCreateReview">
            发起评审
          </el-button>
        </el-empty>
        <el-table v-else :data="reviews" border stripe>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">{{ reviewStatusLabel(row.status) }}</template>
          </el-table-column>
          <el-table-column prop="create_by" label="发起人" width="100">
            <template #default="{ row }">{{ formatMemberByUsername(row.create_by, memberNames) }}</template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ formatTime(row.update_time) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button link type="primary" @click="$router.push(`/case-reviews/${row.id}`)">
                打开
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="测试计划" name="plans">
        <div class="pane-toolbar" v-if="canPlanEdit && scopeEditable">
          <el-button type="primary" @click="openCreatePlan">从范围创建计划</el-button>
          <el-button @click="createPlanFromTemplate('smoke', false)">一键冒烟计划</el-button>
          <el-button @click="createPlanFromTemplate('regression', false)">一键回归计划</el-button>
          <el-button plain @click="createPlanFromTemplate('regression', true)">回归（含自动化）</el-button>
        </div>
        <el-empty v-if="!plans.length" description="暂无测试计划">
          <el-button v-if="canPlanEdit && scopeEditable" type="primary" @click="openCreatePlan">
            从范围创建计划
          </el-button>
          <el-button v-if="canPlanEdit && scopeEditable" @click="createPlanFromTemplate('smoke', false)">
            一键冒烟
          </el-button>
        </el-empty>
        <el-table v-else :data="plans" border stripe>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="plan_type" label="类型" width="100">
            <template #default="{ row }">{{ planTypeLabel(row.plan_type) }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">{{ planStatusLabel(row.status) }}</template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ formatTime(row.update_time) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button link type="primary" @click="$router.push(`/test-plans/${row.id}`)">
                打开
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="缺陷" name="defects">
        <div class="pane-toolbar">
          <el-button
            v-if="canDefectView"
            type="primary"
            @click="$router.push({ path: '/test-defects', query: { release_id: String(releaseId) } })"
          >
            打开缺陷台账
          </el-button>
          <el-button v-if="canDefectView" @click="loadDefects">刷新</el-button>
        </div>
        <div class="chips" v-if="defectStats">
          <el-tag type="danger">未关闭: {{ defectStats.open_count || 0 }}</el-tag>
          <el-tag
            v-for="(v, k) in defectStats.by_severity || {}"
            :key="k"
            size="small"
            style="margin-left: 6px"
          >{{ defectSeverityLabel(k) }}: {{ v }}</el-tag>
        </div>
        <el-empty v-if="!defects.length" description="本版本暂无缺陷">
          <el-button
            v-if="canDefectView"
            type="primary"
            @click="$router.push({ path: '/test-defects', query: { release_id: String(releaseId) } })"
          >去缺陷台账新建</el-button>
        </el-empty>
        <el-table
          v-else
          :data="defects"
          border
          stripe
          style="margin-top: 12px"
          class="clickable-rows"
          @row-click="openDefect"
        >
          <el-table-column prop="defect_key" label="编号" width="110" />
          <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
          <el-table-column prop="severity" label="严重度" width="100">
            <template #default="{ row }">
              <el-tag :type="DEFECT_SEVERITY_TAG_TYPE[row.severity] || 'info'" size="small" effect="light">
                {{ defectSeverityLabel(row.severity) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="DEFECT_STATUS_TAG_TYPE[row.status] || 'info'" size="small">
                {{ defectStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="assignee_id" label="负责人" width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ formatMemberName(row.assignee_id, memberNames) }}</template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ formatTime(row.update_time) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="质量" name="quality" v-if="canQualityView">
        <ReleasePublishChecklist
          :quality-preview="qualityPreview"
          :can-edit="canEdit"
          :loading="qualityLoading"
          :snapshot-loading="snapshotSaving"
          @refresh="onChecklistRefresh"
          @snapshot="createSnapshot"
          @goto="onChecklistGoto"
        />
        <div class="pane-toolbar">
          <el-button type="primary" :loading="qualityLoading" @click="loadQuality">刷新预览</el-button>
          <el-button
            v-if="canEdit"
            type="success"
            :loading="snapshotSaving"
            @click="createSnapshot"
          >生成快照</el-button>
          <el-button
            v-if="canQualityApprove && qualityPreview?.can_reapprove_waiver"
            type="warning"
            @click="waiverDialog = true"
          >{{ qualityPreview?.latest_snapshot?.conclusion === 'conditional_pass' && !qualityPreview?.has_valid_waiver ? '重新批准豁免' : '批准豁免' }}</el-button>
          <el-button link type="primary" @click="$router.push({ path: '/project-settings', query: { tab: 'quality-gate' } })">
            配置门禁阈值
          </el-button>
        </div>
        <el-alert
          v-if="qualityPreview?.rules"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
          :title="qualityRulesHint"
        />
        <el-alert
          v-if="qualityPreview"
          :type="qualityPreview.gate_enforce ? 'warning' : 'info'"
          show-icon
          :closable="false"
          :title="qualityPreview.gate_enforce
            ? '强制模式：实时门禁未通过且无有效豁免时禁止发布；陈旧 pass 快照不放行。进入就绪始终需要合格快照或有效豁免'
            : '提示模式：发布时未通过仅警告（陈旧 pass 也会警告）；进入就绪始终强制要求合格快照或有效豁免（豁免 14 天内有效）'"
          style="margin-bottom: 12px"
        />
        <el-alert
          v-if="qualityPreview?.snapshot_stale"
          type="error"
          show-icon
          :closable="false"
          title="最近 pass 快照已过期：实时门禁已回退，请重新生成快照或批准豁免后再进入就绪/发布"
          style="margin-bottom: 12px"
        />
        <el-alert
          v-if="qualityPreview?.latest_snapshot?.conclusion === 'conditional_pass' && !qualityPreview?.has_valid_waiver"
          type="warning"
          show-icon
          :closable="false"
          title="豁免快照已失效或过期（超过 14 天），需重新批准豁免"
          style="margin-bottom: 12px"
        />
        <el-card
          v-if="qualityPreview?.latest_snapshot"
          shadow="never"
          class="snap-compare"
          style="margin-bottom: 12px"
        >
          <div class="snap-compare-row">
            <span>实时结论：
              <el-tag :type="qualityStatusTagType(qualityPreview.conclusion)" size="small">
                {{ qualityStatusLabel(qualityPreview.conclusion) }}
              </el-tag>
            </span>
            <span>最近快照：
              <el-tag :type="qualityStatusTagType(qualityPreview.latest_snapshot.conclusion)" size="small">
                {{ qualityStatusLabel(qualityPreview.latest_snapshot.conclusion) }}
              </el-tag>
              <el-tag v-if="qualityPreview.snapshot_stale" type="danger" size="small" style="margin-left: 6px">已陈旧</el-tag>
              <el-tag
                v-else-if="qualityPreview.has_valid_waiver"
                type="warning"
                size="small"
                style="margin-left: 6px"
              >豁免{{ waiverRemainingLabel(qualityPreview.latest_snapshot) ? ` · ${waiverRemainingLabel(qualityPreview.latest_snapshot)}` : '有效' }}</el-tag>
            </span>
          </div>
        </el-card>
        <div class="stat-row" v-if="qualityPreview?.metrics">
          <el-card shadow="never" class="stat-card">
            <div class="stat-num">{{ qualityPreview.metrics.required_done }}/{{ qualityPreview.metrics.required_total }}</div>
            <div class="stat-label">必测完成</div>
          </el-card>
          <el-card shadow="never" class="stat-card">
            <div class="stat-num">{{ Math.round((qualityPreview.metrics.pass_rate || 0) * 100) }}%</div>
            <div class="stat-label">通过率</div>
          </el-card>
          <el-card shadow="never" class="stat-card">
            <div class="stat-num">{{ qualityPreview.metrics.blocker_open || 0 }}</div>
            <div class="stat-label">阻塞缺陷</div>
          </el-card>
          <el-card shadow="never" class="stat-card">
            <div class="stat-num">{{ qualityPreview.metrics.critical_open || 0 }}</div>
            <div class="stat-label">严重缺陷</div>
          </el-card>
          <el-card shadow="never" class="stat-card">
            <el-tag :type="qualityStatusTagType(qualityPreview.conclusion)" size="large">
              {{ qualityStatusLabel(qualityPreview.conclusion) }}
            </el-tag>
            <div class="stat-label">实时结论</div>
          </el-card>
        </div>
        <el-table
          v-if="qualityPreview?.checks?.length"
          :data="qualityPreview.checks"
          border
          stripe
          style="margin-top: 12px"
        >
          <el-table-column prop="label" label="规则" min-width="160" />
          <el-table-column prop="message" label="说明" min-width="220" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag
                :type="row.status === 'pass' ? 'success' : row.status === 'blocked' ? 'danger' : 'warning'"
                size="small"
              >
                {{ row.status === 'pass' ? '通过' : row.status === 'blocked' ? '阻塞' : '未通过' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <template v-if="qualityReport">
          <h4 style="margin: 16px 0 8px">
            质量报告钻取
            <el-tag size="small" type="info" style="margin-left: 8px">
              未完成 {{ qualityReport.counts?.incomplete_required || 0 }}
              / 失败 {{ qualityReport.counts?.failed_required || 0 }}
              / 未关闭缺陷 {{ qualityReport.counts?.open_defects || 0 }}
              / 高风险无结果 {{ qualityReport.counts?.high_risk_without_result || 0 }}
            </el-tag>
          </h4>
          <el-tabs v-model="qualityDrillTab" type="card">
            <el-tab-pane label="未完成必测" name="incomplete">
              <el-table :data="qualityReport.incomplete_required || []" border stripe size="small" empty-text="无">
                <el-table-column prop="title" label="项" min-width="200" show-overflow-tooltip />
                <el-table-column prop="result_status" label="结果" width="100" />
                <el-table-column prop="plan_id" label="计划ID" width="90" />
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="未通过必测" name="failed">
              <el-table :data="qualityReport.failed_required || []" border stripe size="small" empty-text="无">
                <el-table-column prop="title" label="项" min-width="200" show-overflow-tooltip />
                <el-table-column prop="result_status" label="结果" width="100" />
                <el-table-column prop="plan_id" label="计划ID" width="90" />
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="未关闭缺陷" name="defects">
              <el-table
                :data="qualityReport.open_defects || []"
                border
                stripe
                size="small"
                empty-text="无"
                class="clickable-rows"
                @row-click="openDefect"
              >
                <el-table-column prop="defect_key" label="编号" width="110" />
                <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
                <el-table-column prop="severity" label="严重度" width="90">
                  <template #default="{ row }">{{ defectSeverityLabel(row.severity) }}</template>
                </el-table-column>
                <el-table-column prop="status" label="状态" width="100">
                  <template #default="{ row }">{{ defectStatusLabel(row.status) }}</template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="高风险无结果" name="highrisk">
              <el-table :data="qualityReport.high_risk_without_result || []" border stripe size="small" empty-text="无">
                <el-table-column prop="functional_case_id" label="用例ID" width="100" />
                <el-table-column prop="risk_level" label="风险" width="100">
                  <template #default="{ row }">{{ riskLabel(row.risk_level) }}</template>
                </el-table-column>
                <el-table-column prop="requirement_key" label="需求" min-width="140" />
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="最近运行" name="runs">
              <el-table :data="qualityReport.recent_runs || []" border stripe size="small" empty-text="无">
                <el-table-column prop="id" label="运行ID" width="90" />
                <el-table-column prop="plan_name" label="计划" min-width="160" />
                <el-table-column prop="status" label="状态" width="100">
                  <template #default="{ row }">
                    <el-tag size="small" effect="light">{{ planRunStatusLabel(row.status) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="started_at" label="开始" width="170">
                  <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </template>

        <h4 style="margin: 16px 0 8px">历史快照</h4>
        <el-table :data="qualitySnapshots" border stripe empty-text="暂无快照">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="conclusion" label="结论" width="120">
            <template #default="{ row }">
              <el-tag :type="qualityStatusTagType(row.conclusion)" size="small">
                {{ qualityStatusLabel(row.conclusion) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="create_by" label="创建人" width="100" />
          <el-table-column prop="create_time" label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
          </el-table-column>
          <el-table-column label="豁免人" width="110" show-overflow-tooltip>
            <template #default="{ row }">{{ row.waiver_approved_by || '—' }}</template>
          </el-table-column>
          <el-table-column label="豁免时间" width="170">
            <template #default="{ row }">{{ formatTime(row.waiver_approved_at) }}</template>
          </el-table-column>
          <el-table-column label="豁免有效期" width="110">
            <template #default="{ row }">
              <span v-if="row.conclusion === 'conditional_pass'">{{ waiverRemainingLabel(row) || '—' }}</span>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column prop="waiver_reason" label="豁免原因" min-width="160" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="测试报告" name="defect-report" v-if="canDefectView">
        <ReleaseDefectReport
          ref="defectReportRef"
          :release-id="releaseId"
          :project-id="projectId"
          :can-defect-view="canDefectView"
          @open-defect="openDefect"
        />
      </el-tab-pane>
      <el-tab-pane label="智能化" name="intelligence" v-if="canQualityView">
        <ReleaseIntelligence
          v-if="release"
          :release-id="releaseId"
          :project-id="projectId"
          :tab-active="tab === 'intelligence'"
          @goto="onIntelligenceGoto"
        />
      </el-tab-pane>
    </el-tabs>

    <AddReleaseRequirementDialog
      v-model="reqDialog"
      :release-id="releaseId"
      :project-id="projectId"
      :existing-keys="requirementKeys"
      @done="loadRequirements"
    />

    <RequirementPreviewDrawer
      v-model="reqPreviewVisible"
      :release-req="reqActiveRow"
      :release-id="releaseId"
      :project-id="projectId"
      :can-edit="canEdit && scopeEditable"
      :impact-banner="reqImpactBanner"
      :show-start-review="reqImpactBanner && !!reqReviewAiId"
      @edit="openReqEditFromPreview"
      @replace-doc="openReqReplaceFromPreview"
      @upgrade="openReqUpgradeFromPreview"
      @start-review="promptStartRequirementReview"
    />
    <RequirementUpdateDialog
      v-model="reqUpdateVisible"
      :mode="reqUpdateMode"
      :release-id="releaseId"
      :project-id="projectId"
      :release-req="reqActiveRow"
      @done="onReqUpdated"
    />

    <el-dialog v-model="editReleaseVisible" title="编辑版本" width="520px" destroy-on-close>
      <el-form :model="editForm" label-width="100px">
        <el-form-item v-if="release?.status === 'draft'" label="版本键">
          <el-input v-model="editForm.release_key" maxlength="64" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="editForm.name" maxlength="200" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="外部链接">
          <el-input v-model="editForm.external_url" />
        </el-form-item>
        <el-form-item label="版本负责人">
          <ProjectMemberSelect
            v-if="projectId"
            v-model="editForm.owner_id"
            :project-id="projectId"
            clearable
            placeholder="负责最终定版与跟进"
            width="100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editReleaseVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="submitEditRelease">保存</el-button>
      </template>
    </el-dialog>

    <AddToReleaseDialog
      v-model="pickVisible"
      :release-id="releaseId"
      :project-id="projectId"
      @done="onScopesAdded"
    />
    <AssetLinkDialog
      v-model="linkVisible"
      :project-id="projectId"
      :functional-case-id="linkCaseId"
      :case-title="linkCaseTitle"
    />
    <ScopeEditDialog
      v-model="scopeEditVisible"
      :release-id="releaseId"
      :project-id="projectId"
      :scope="scopeEditRow"
      :requirements="requirements"
      @done="loadAll"
    />

    <el-dialog v-model="reviewDialog" title="发起用例评审" width="520px" destroy-on-close>
      <el-form label-width="100px">
        <el-form-item label="标题" required>
          <el-input v-model="reviewForm.title" maxlength="200" />
        </el-form-item>
        <el-form-item label="评审模板">
          <el-select
            v-model="reviewForm.template_id"
            clearable
            filterable
            placeholder="默认使用项目默认模板"
            style="width: 100%"
          >
            <el-option
              v-for="t in reviewTemplates"
              :key="t.id"
              :label="t.is_default ? `${t.name}（默认）` : t.name"
              :value="t.id"
            />
          </el-select>
          <div class="form-hint">模板检查项会快照到本批评审；可在「评审模板」页维护</div>
        </el-form-item>
        <el-form-item label="评审人" required>
          <ProjectMemberSelect
            v-if="projectId"
            v-model="reviewForm.reviewerIds"
            :project-id="projectId"
            multiple
            placeholder="请至少选择一名评审人"
            width="100%"
          />
        </el-form-item>
        <el-form-item label="用例">
          <span>将纳入版本范围全部 {{ reviewScopeCount }} 条用例（不受列表筛选影响）</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewDialog = false">取消</el-button>
        <el-button type="primary" :loading="reviewSaving" @click="submitCreateReview">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="waiverDialog" title="批准质量豁免" width="520px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="原因" required>
          <el-input v-model="waiverForm.reason" type="textarea" :rows="4" maxlength="2000" show-word-limit />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="waiverForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="waiverDialog = false">取消</el-button>
        <el-button type="primary" :loading="waiverSaving" @click="submitWaiver">确认豁免</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="planDialog" title="创建测试计划" width="520px" destroy-on-close>
      <el-form label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="planForm.name" maxlength="200" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="planForm.plan_type" style="width: 200px">
            <el-option label="回归" value="regression" />
            <el-option label="冒烟" value="smoke" />
            <el-option label="验收" value="acceptance" />
            <el-option label="性能" value="performance" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="执行环境">
          <el-select v-model="planForm.environment_id" clearable placeholder="可选" style="width: 280px">
            <el-option
              v-for="env in proStore.envList"
              :key="env.id"
              :label="env.name"
              :value="env.id"
            />
          </el-select>
          <span class="form-hint">自动化派发与运行快照将引用该环境</span>
        </el-form-item>
        <el-form-item label="含自动化项">
          <el-switch v-model="planForm.include_automation" />
          <span class="form-hint">默认关闭：功能手工为主；有稳定映射后再开启并补齐自动化项</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="planDialog = false">取消</el-button>
        <el-button type="primary" :loading="planSaving" @click="submitCreatePlan">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchDialog" title="批量设置范围" width="460px" destroy-on-close>
      <p class="form-hint" style="margin-top: 0">已选 {{ selectedScopeIds.length }} 项</p>
      <el-form label-width="100px">
        <el-form-item label="风险等级">
          <el-select v-model="batchForm.risk_level" clearable placeholder="不修改" style="width: 240px">
            <el-option v-for="r in riskOptions" :key="r" :label="riskLabel(r)" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人">
          <ProjectMemberSelect
            v-model="batchForm.owner_id"
            :project-id="projectId"
            clearable
            placeholder="不修改"
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item label="清空负责人">
          <el-switch v-model="batchForm.clear_owner" />
          <span class="form-hint">开启后将清除所选负责人（忽略上方负责人选择）</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchDialog = false">取消</el-button>
        <el-button type="primary" :loading="batchSaving" @click="submitBatchUpdate">保存</el-button>
      </template>
    </el-dialog>

    <DefectDetailDrawer
      v-if="projectId"
      ref="defectDrawerRef"
      :project-id="projectId"
      :can-edit="canDefectEdit"
      :default-release-id="releaseId"
      @saved="onDefectSaved"
      @deleted="onDefectSaved"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { testAssetLinkApi, testDefectApi, testPlanApi, testReleaseApi, testReviewApi } from '@/api/testManagement'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import {
  allowedReleaseTransitions,
  qualityStatusLabel,
  qualityStatusTagType,
  releaseDeletable,
  releaseScopeEditable,
  releaseStatusLabel
} from '@/utils/testReleaseStatus'
import { formatMemberByUsername, formatMemberName, loadMemberNameMap, waiverRemainingLabel } from '@/utils/projectMembers'
import { confirmReleaseStatusChange } from '@/utils/releaseQualityConfirm'
import {
  DEFECT_SEVERITY_TAG_TYPE,
  DEFECT_STATUS_TAG_TYPE,
  defectSeverityLabel,
  defectStatusLabel
} from '@/utils/defectDisplay'
import { safeExternalUrl } from '@/utils/safeExternalUrl'
import AddToReleaseDialog from './components/AddToReleaseDialog.vue'
import AddReleaseRequirementDialog from './components/AddReleaseRequirementDialog.vue'
import RequirementPreviewDrawer from './components/RequirementPreviewDrawer.vue'
import RequirementUpdateDialog from './components/RequirementUpdateDialog.vue'
import {
  findReleaseRequirement,
  isProjectRequirement,
  parseAiRequirementId,
  requirementTypeLabel
} from '@/utils/releaseRequirement.js'
import AssetLinkDialog from './components/AssetLinkDialog.vue'
import DefectDetailDrawer from './components/DefectDetailDrawer.vue'
import ReleaseDefectReport from './components/ReleaseDefectReport.vue'
import ProjectMemberSelect from './components/ProjectMemberSelect.vue'
import ReleaseAgileWorkflow from './components/ReleaseAgileWorkflow.vue'
import ReleasePublishChecklist from './components/ReleasePublishChecklist.vue'
import ReleaseAutomationProgress from './components/ReleaseAutomationProgress.vue'
import ReleaseIntelligence from './components/ReleaseIntelligence.vue'
import RequirementReview from './RequirementReview.vue'
import ScopeEditDialog from './components/ScopeEditDialog.vue'
import TmBackButton from './components/TmBackButton.vue'
import TmPremiumBanner from '@/components/TmPremiumBanner.vue'
import { computeAgileWorkflow, listUnmappedScopes, workflowStorageKey, workflowMarkTimeKey } from '@/utils/releaseAgileWorkflow'
import { planRunStatusLabel } from '@/utils/tmDisplay'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()

const canEdit = computed(() => uStore.hasPermission('test_release:edit'))
const canReviewManage = computed(() => uStore.hasPermission('test_review:manage'))
const canReviewView = computed(() => uStore.hasPermission('test_review:view'))
const canPlanEdit = computed(() => uStore.hasPermission('test_plan:edit'))
const canPlanView = computed(() => uStore.hasPermission('test_plan:view'))
const canDefectEdit = computed(() => uStore.hasPermission('test_defect:edit'))
const canDefectView = computed(() => uStore.hasPermission('test_defect:view'))
const canQualityView = computed(() => uStore.hasPermission('test_quality:view'))
const canQualityApprove = computed(() => uStore.hasPermission('test_quality:approve_exception'))
const projectId = computed(() => proStore.projectInfo?.id)
const releaseId = computed(() => Number(route.params.id))

const loading = ref(false)
const tab = ref(route.query.tab || 'overview')
const release = ref(null)
const overview = ref(null)
const requirements = ref([])
const scopes = ref([])
const reviews = ref([])
const plans = ref([])
const defects = ref([])
const defectStats = ref(null)
const scopeFilters = reactive({
  keyword: '',
  module: '',
  risk_level: '',
  automation_status: '',
  owner_id: null
})
const notifyingOwners = ref(false)
const reviewDialog = ref(false)
const reviewSaving = ref(false)
const reviewForm = reactive({ title: '', reviewerIds: [], template_id: null })
const reviewTemplates = ref([])
const reviewScopeCount = ref(0)
const planDialog = ref(false)
const planSaving = ref(false)
const planForm = reactive({ name: '', plan_type: 'regression', include_automation: false, environment_id: null })

const reqDialog = ref(false)
const reqPreviewVisible = ref(false)
const reqUpdateVisible = ref(false)
const reqUpdateMode = ref('edit')
const reqActiveRow = ref(null)
const reqImpactBanner = ref(false)
const reqReviewRef = ref(null)
const reqReviewAiId = ref(null)
const allScopesForWorkflow = ref([])
const workflowMarks = reactive({
  requirement_review: false,
  functional_cases: false,
  quality_preview: false
})
const workflowMarkTimes = reactive({
  requirement_review: null,
  functional_cases: null,
  quality_preview: null
})
const requirementReviewAutoDone = ref(false)
const requirementReviewDone = computed(
  () => requirementReviewAutoDone.value || workflowMarks.requirement_review
)
const exportingPackage = ref(false)
const workflowPhase2 = ref({
  hasManualPlan: false,
  hasPlanEnv: false,
  runsCount: 0,
  blockerOpen: 0,
  criticalOpen: 0,
  firstPlanCreateTime: null,
  firstPlanEnvTime: null,
  firstRunStartedAt: null,
  requiredDoneAt: null,
  defectsTriagedAt: null
})
const workflowPhase3 = ref({
  hasAutomationItems: false,
  hasAutoDispatched: false,
  autoItemsAt: null,
  autoDispatchedAt: null
})
const primaryPlanId = ref(null)
const workflowQualityMetrics = computed(() => qualityPreview.value?.metrics || null)
const qualityRulesHint = computed(() => {
  const r = qualityPreview.value?.rules
  if (!r) return '当前项目门禁阈值'
  const pct = (v) => `${Math.round(Number(v || 0) * 100)}%`
  return `当前项目阈值：必测完成 ≥${pct(r.required_completion_min)}，通过率 ≥${pct(r.required_pass_rate_min)}，阻塞缺陷≤${r.blocker_open_max}，严重缺陷≤${r.critical_open_max}，高风险无结果≤${r.high_risk_without_result_max}`
})
const workflowPhase3Progress = computed(() => {
  const wf = computeAgileWorkflow({
    release: release.value,
    requirements: requirements.value,
    scopes: allScopesForWorkflow.value,
    reviews: reviews.value,
    requirementReviewDone: requirementReviewDone.value,
    functionalCasesAck: workflowMarks.functional_cases,
    qualityPreviewedAck: workflowMarks.quality_preview,
    phase2: workflowPhase2.value,
    phase3: workflowPhase3.value,
    qualityMetrics: workflowQualityMetrics.value,
    qualityPreview: qualityPreview.value,
    workflowMarkTimes: workflowMarkTimes
  })
  return wf.phase3Progress
})
const selectedScopeIds = ref([])
const batchDialog = ref(false)
const batchSaving = ref(false)
const batchForm = reactive({
  risk_level: '',
  owner_id: null,
  clear_owner: false
})
const pickVisible = ref(false)
const linkVisible = ref(false)
const linkCaseId = ref(null)
const linkCaseTitle = ref('')
const editReleaseVisible = ref(false)
const editSaving = ref(false)
const editForm = reactive({
  release_key: '',
  name: '',
  description: '',
  external_url: '',
  owner_id: null
})
const scopeEditVisible = ref(false)
const scopeEditRow = ref(null)
const qualityPreview = ref(null)
const qualitySnapshots = ref([])
const qualityReport = ref(null)
const qualityDrillTab = ref('incomplete')
const qualityLoading = ref(false)
const snapshotSaving = ref(false)
const waiverDialog = ref(false)
const waiverSaving = ref(false)
const waiverForm = reactive({ reason: '', note: '' })
const memberNames = ref(new Map())

const riskOptions = ['low', 'medium', 'high', 'critical']
const coverageOptions = ['none', 'partial', 'covered', 'unstable']

const riskLabel = (s) => ({ low: '低', medium: '中', high: '高', critical: '严重' }[s] || s)
const riskTagType = (s) =>
  ({ low: 'success', medium: 'warning', high: 'danger', critical: 'danger' }[s] || 'info')
const coverageLabel = (s) =>
  ({ none: '未覆盖', partial: '部分', covered: '已覆盖', unstable: '不稳定' }[s] || s)
const coverageTagType = (s) =>
  ({ none: 'info', partial: 'warning', covered: 'success', unstable: 'danger' }[s] || 'info')
const formatTime = (v) => (v ? String(v).replace('T', ' ').slice(0, 19) : '—')
const reviewDecisionLabel = (s) =>
  ({
    pending: '待评',
    approved: '通过',
    changes_requested: '需改',
    rejected: '拒绝'
  }[s] || (s ? s : '—'))
const reviewDecisionTagType = (s) =>
  ({
    pending: 'info',
    approved: 'success',
    changes_requested: 'warning',
    rejected: 'danger'
  }[s] || 'info')
const releaseStatusTagType = (s) =>
  ({
    draft: 'info',
    testing: 'warning',
    ready: 'success',
    released: 'success',
    archived: 'info'
  }[s] || 'info')
const goTab = (name) => {
  tab.value = name
}
const reviewStatusLabel = (s) =>
  ({
    pending: '待开始',
    in_review: '评审中',
    approved: '已通过',
    changes_requested: '需修改',
    cancelled: '已取消'
  }[s] || s)
const planStatusLabel = (s) =>
  ({ draft: '草稿', ready: '就绪', running: '运行中', completed: '已完成', cancelled: '已取消' }[s] || s)
const planTypeLabel = (s) =>
  ({ smoke: '冒烟', regression: '回归', acceptance: '验收', performance: '性能', custom: '自定义' }[s] || s)

const scopeEditable = computed(() => releaseScopeEditable(release.value?.status))
const requirementKeys = computed(() => (requirements.value || []).map((r) => r.requirement_key))

const reqInternalLink = (row) => {
  const m = String(row?.requirement_key || '').match(/^REQ-(\d+)$/i)
  if (m) return `/ai-testing/requirements/${m[1]}`
  return null
}

const loadWorkflowMarks = () => {
  if (!releaseId.value) return
  for (const key of ['requirement_review', 'functional_cases', 'quality_preview']) {
    workflowMarks[key] = localStorage.getItem(workflowStorageKey(releaseId.value, key)) === '1'
    workflowMarkTimes[key] = localStorage.getItem(workflowMarkTimeKey(releaseId.value, key)) || null
  }
}

const saveWorkflowMark = (key) => {
  if (!releaseId.value || !key) return
  const now = new Date().toISOString()
  localStorage.setItem(workflowStorageKey(releaseId.value, key), '1')
  localStorage.setItem(workflowMarkTimeKey(releaseId.value, key), now)
  workflowMarks[key] = true
  workflowMarkTimes[key] = now
}

const markQualityPreviewed = () => {
  saveWorkflowMark('quality_preview')
}

const onChecklistRefresh = async () => {
  await loadQuality()
  markQualityPreviewed()
}

const onChecklistGoto = (action) => {
  if (action === 'quality') goTab('quality')
  else if (action === 'defects') goTab('defects')
  else if (action === 'scopes') goTab('scopes')
}

const onIntelligenceGoto = (action) => {
  if (!action) return
  if (action.tab) goTab(action.tab)
  if (action.drill) qualityDrillTab.value = action.drill
}

const loadAllScopeRows = async () => {
  const res = await testReleaseApi.listScopes(releaseId.value, projectId.value, {})
  return res.data?.data || []
}

const refreshWorkflowScopes = async () => {
  try {
    allScopesForWorkflow.value = await loadAllScopeRows()
  } catch {
    allScopesForWorkflow.value = scopes.value
  }
}

const loadWorkflowPhase2 = async () => {
  let hasManualPlan = false
  let hasPlanEnv = false
  let runsCount = 0
  let firstPlanId = null
  let hasAutomationItems = false
  let hasAutoDispatched = false
  let firstPlanCreateTime = null
  let firstPlanEnvTime = null
  let firstRunStartedAt = null
  let autoItemsAt = null
  let autoDispatchedAt = null
  let requiredDoneAt = workflowPhase2.value.requiredDoneAt
  let defectsTriagedAt = workflowPhase2.value.defectsTriagedAt
  if (canPlanView.value && plans.value.length) {
    for (const p of plans.value) {
      try {
        const res = await testPlanApi.get(p.id, projectId.value)
        const data = res.data?.data || {}
        const plan = data.plan
        const items = data.items || []
        const runs = data.runs || []
        if (!firstPlanId && plan?.id) firstPlanId = plan.id
        if (plan?.create_time) {
          if (!firstPlanCreateTime || plan.create_time < firstPlanCreateTime) {
            firstPlanCreateTime = plan.create_time
          }
        }
        if (items.some((i) => i.item_type === 'functional_manual' || i.execution_mode === 'manual')) {
          hasManualPlan = true
        }
        const autoItems = items.filter((i) => i.execution_mode === 'automation')
        if (autoItems.length) {
          hasAutomationItems = true
          const t = plan?.update_time || plan?.create_time
          if (t && (!autoItemsAt || t < autoItemsAt)) autoItemsAt = t
        }
        if (plan?.environment_id && plan?.update_time) {
          hasPlanEnv = true
          if (!firstPlanEnvTime || plan.update_time < firstPlanEnvTime) {
            firstPlanEnvTime = plan.update_time
          }
        }
        runsCount += runs.length
        for (const run of runs) {
          const t = run.started_at || run.create_time
          if (t && (!firstRunStartedAt || t < firstRunStartedAt)) firstRunStartedAt = t
        }
        if (!hasAutoDispatched && hasAutomationItems && runs.length) {
          const latest = [...runs].sort((a, b) => (b.id || 0) - (a.id || 0))[0]
          if (latest?.id) {
            try {
              const runRes = await testPlanApi.getRun(latest.id, projectId.value)
              const runItems = runRes.data?.data?.items || []
              const dispatched = runItems.some(
                (i) =>
                  i.execution_mode === 'automation' &&
                  i.result_status &&
                  i.result_status !== 'not_run'
              )
              if (dispatched) {
                hasAutoDispatched = true
                autoDispatchedAt =
                  latest.finished_at || latest.started_at || latest.create_time || autoDispatchedAt
              }
            } catch {
              /* ignore */
            }
          }
        }
      } catch {
        /* ignore single plan load failure */
      }
    }
  }
  const metrics = qualityPreview.value?.metrics
  if (metrics?.required_total && metrics.required_done >= metrics.required_total) {
    requiredDoneAt = requiredDoneAt || qualityPreview.value?.previewed_at || new Date().toISOString()
  }
  if (metrics && (metrics.blocker_open || 0) === 0 && (metrics.critical_open || 0) === 0) {
    defectsTriagedAt = defectsTriagedAt || qualityPreview.value?.previewed_at || null
  }
  const sev = defectStats.value?.by_severity || {}
  workflowPhase2.value = {
    hasManualPlan,
    hasPlanEnv,
    runsCount,
    blockerOpen: sev.blocker || qualityPreview.value?.metrics?.blocker_open || 0,
    criticalOpen: sev.critical || qualityPreview.value?.metrics?.critical_open || 0,
    firstPlanCreateTime,
    firstPlanEnvTime,
    firstRunStartedAt,
    requiredDoneAt,
    defectsTriagedAt
  }
  workflowPhase3.value = { hasAutomationItems, hasAutoDispatched, autoItemsAt, autoDispatchedAt }
  primaryPlanId.value = firstPlanId
}

const openReqDialog = () => {
  reqDialog.value = true
}

const onWorkflowAction = async (event, payload) => {
  if (event === 'nav') {
    router.push(payload.path)
    return
  }
  if (event === 'mark' && payload?.key) {
    saveWorkflowMark(payload.key)
    ElMessage.success('已标记完成')
    return
  }
  if (event === 'transition' && payload?.status) {
    await doTransition(payload.status)
    return
  }
  if (event === 'requirements') {
    tab.value = 'requirements'
    if (canEdit.value && scopeEditable.value) openReqDialog()
    return
  }
  if (event === 'scopes_pick') {
    tab.value = 'scopes'
    if (canEdit.value && scopeEditable.value) openPickCases()
    return
  }
  if (event === 'scopes_tab') {
    tab.value = 'scopes'
    return
  }
  if (event === 'reviews') {
    tab.value = 'reviews'
    if (canReviewManage.value && scopeEditable.value && !reviews.value.length) {
      openCreateReview()
    }
    return
  }
  if (event === 'req_reviews') {
    tab.value = 'req-reviews'
    return
  }
  if (event === 'open_review') {
    const approved = reviews.value.find((r) => r.status === 'approved')
    if (approved) router.push(`/case-reviews/${approved.id}`)
    else tab.value = 'reviews'
    return
  }
  if (event === 'create_plan') {
    await openCreatePlan()
    return
  }
  if (event === 'open_plan' && payload?.planId) {
    const q = payload.tab ? `?tab=${payload.tab}` : ''
    router.push(`/test-plans/${payload.planId}${q}`)
    return
  }
  if (event === 'open_run' && payload?.planId) {
    try {
      const res = await testPlanApi.get(payload.planId, projectId.value)
      const runs = res.data?.data?.runs || []
      const running = runs.find((r) => r.status === 'running')
      const target = running || runs[0]
      if (target?.id) router.push(`/test-plan-runs/${target.id}`)
      else router.push(`/test-plans/${payload.planId}?tab=runs`)
    } catch {
      router.push(`/test-plans/${payload.planId}?tab=runs`)
    }
    return
  }
  if (event === 'quality_tab') {
    goTab('quality')
    return
  }
  if (event === 'defects_tab') {
    goTab('defects')
    return
  }
  if (event === 'refresh_quality') {
    await onChecklistRefresh()
    goTab('quality')
    return
  }
  if (event === 'create_snapshot') {
    goTab('quality')
    await createSnapshot()
    return
  }
  if (event === 'create_plan_template' && payload) {
    await createPlanFromTemplate(payload.plan_type || 'regression', !!payload.include_automation)
    return
  }
  if (event === 'unmapped_scopes') {
    scopeFilters.automation_status = 'none'
    goTab('scopes')
    await loadScopes()
    return
  }
  if (event === 'map_next') {
    const rows = listUnmappedScopes(allScopesForWorkflow.value, { highRiskOnly: true })
    const next = rows[0] || listUnmappedScopes(allScopesForWorkflow.value)[0]
    if (next) {
      goTab('scopes')
      openLinks(next)
    } else {
      ElMessage.success('暂无未映射用例')
      goTab('scopes')
    }
    return
  }
  if (event === 'gen_automation') {
    await genAutomationForPrimaryPlan(payload?.planId)
  }
}

const visibleCoverage = (dist) => {
  if (!dist) return {}
  const out = {}
  for (const [k, v] of Object.entries(dist)) {
    if (k === 'unstable' && !v) continue
    out[k] = v
  }
  return out
}

const loadAll = async () => {
  if (!projectId.value || !releaseId.value) return
  loading.value = true
  try {
    applyScopeOwnerFromRoute()
    memberNames.value = await loadMemberNameMap(projectId.value)
    const [r, o] = await Promise.all([
      testReleaseApi.get(releaseId.value, projectId.value),
      testReleaseApi.overview(releaseId.value, projectId.value)
    ])
    release.value = r.data?.data || null
    overview.value = o.data?.data || null
    requirementReviewAutoDone.value = !!overview.value?.requirement_review_done

    const tasks = [loadRequirements(), loadScopes()]
    if (canReviewView.value) {
      tasks.push(loadReviews().catch(() => { reviews.value = [] }))
    } else {
      reviews.value = []
    }
    if (canPlanView.value) {
      tasks.push(loadPlans().catch(() => { plans.value = [] }))
    } else {
      plans.value = []
    }
    if (canDefectView.value) {
      tasks.push(
        loadDefectStats().catch(() => { defectStats.value = null }),
        loadDefects().catch(() => { defects.value = [] })
      )
    } else {
      defectStats.value = null
      defects.value = []
    }
    await Promise.allSettled(tasks)
    loadWorkflowMarks()
    await refreshWorkflowScopes()
    if (canQualityView.value) {
      try {
        const previewRes = await testReleaseApi.qualityPreview(releaseId.value, projectId.value)
        qualityPreview.value = previewRes.data?.data
          ? { ...previewRes.data.data, previewed_at: new Date().toISOString() }
          : null
      } catch {
        qualityPreview.value = null
      }
    }
    await loadWorkflowPhase2()
  } finally {
    loading.value = false
  }
}

const loadRequirements = async () => {
  try {
    const res = await testReleaseApi.listRequirements(releaseId.value, projectId.value)
    requirements.value = res.data?.data || []
  } catch {
    requirements.value = []
  }
}

const loadScopes = async () => {
  try {
    const res = await testReleaseApi.listScopes(releaseId.value, projectId.value, {
      keyword: scopeFilters.keyword || undefined,
      module: scopeFilters.module || undefined,
      risk_level: scopeFilters.risk_level || undefined,
      automation_status: scopeFilters.automation_status || undefined,
      owner_id: scopeFilters.owner_id || undefined
    })
    scopes.value = res.data?.data || []
  } catch {
    scopes.value = []
  }
}

const applyScopeOwnerFromRoute = () => {
  const raw = route.query.owner_id
  if (raw == null || raw === '') return
  const n = Number(raw)
  if (Number.isFinite(n) && n > 0) {
    scopeFilters.owner_id = n
  }
}

const notifyScopeOwners = async () => {
  try {
    await ElMessageBox.confirm(
      '将按当前版本已分配的负责人汇总推送站内信（每人一条，列出其用例）。指派过程中不会再逐条通知。是否继续？',
      '通知负责人',
      { type: 'info', confirmButtonText: '推送', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  notifyingOwners.value = true
  try {
    const res = await testReleaseApi.notifyScopeOwners(releaseId.value, projectId.value)
    const d = res.data?.data || {}
    if (d.reason === 'disabled') {
      ElMessage.warning('项目未开启「测试范围用例指派」通知开关')
      return
    }
    if (d.reason === 'premium_unavailable') {
      ElMessage.warning('扩展包不可用，未能推送')
      return
    }
    ElMessage.success(
      `已通知 ${d.sent || 0} 人（覆盖 ${d.cases || 0} 条用例${d.skipped ? `，跳过 ${d.skipped}` : ''}）`
    )
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '推送失败')
  } finally {
    notifyingOwners.value = false
  }
}

const loadReviews = async () => {
  const res = await testReviewApi.list({
    project_id: projectId.value,
    release_id: releaseId.value
  })
  reviews.value = res.data?.data || []
}

const loadPlans = async () => {
  const res = await testPlanApi.list(projectId.value, releaseId.value)
  plans.value = res.data?.data || []
}

const loadDefectStats = async () => {
  if (!canDefectView.value) return
  try {
    const res = await testDefectApi.releaseStats(releaseId.value, projectId.value)
    defectStats.value = res.data?.data || null
  } catch {
    defectStats.value = null
  }
}

const loadDefects = async () => {
  if (!canDefectView.value) return
  const res = await testDefectApi.list({
    project_id: projectId.value,
    release_id: releaseId.value
  })
  defects.value = res.data?.data || []
}

const openCreateReview = async () => {
  const allScopes = await loadAllScopeRows()
  if (!allScopes.length) {
    ElMessage.warning('请先纳入测试范围用例')
    return
  }
  reviewScopeCount.value = allScopes.length
  reviewForm.title = `${release.value?.name || ''} 用例评审`
  reviewForm.reviewerIds = []
  reviewForm.template_id = null
  try {
    const tres = await testReviewApi.listTemplates(projectId.value)
    reviewTemplates.value = tres.data?.data || []
    const def = reviewTemplates.value.find((t) => t.is_default)
    if (def) reviewForm.template_id = def.id
  } catch {
    reviewTemplates.value = []
  }
  reviewDialog.value = true
}

const submitCreateReview = async () => {
  const title = reviewForm.title.trim()
  if (!title) {
    ElMessage.warning('请填写标题')
    return
  }
  const reviewer_ids = (reviewForm.reviewerIds || [])
    .map((x) => Number(x))
    .filter((n) => Number.isFinite(n) && n > 0)
  if (!reviewer_ids.length) {
    ElMessage.warning('请至少选择一名评审人')
    return
  }
  reviewSaving.value = true
  try {
    const allScopes = await loadAllScopeRows()
    if (!allScopes.length) {
      ElMessage.warning('范围为空，无法创建评审')
      return
    }
    const res = await testReviewApi.create({
      project_id: projectId.value,
      release_id: releaseId.value,
      title,
      reviewer_ids,
      template_id: reviewForm.template_id || undefined,
      functional_case_ids: allScopes.map((s) => s.functional_case_id)
    })
    reviewDialog.value = false
    ElMessage.success('已创建评审')
    const id = res.data?.data?.id
    if (id) router.push(`/case-reviews/${id}`)
    else await loadReviews()
  } finally {
    reviewSaving.value = false
  }
}

const openCreatePlan = async () => {
  const allScopes = await loadAllScopeRows()
  if (!allScopes.length) {
    ElMessage.warning('请先纳入测试范围用例')
    return
  }
  if (!proStore.envList?.length && projectId.value) {
    await proStore.getEnvList(projectId.value)
  }
  planForm.name = `${release.value?.name || ''} 回归计划`
  planForm.plan_type = 'regression'
  planForm.include_automation = false
  planForm.environment_id = proStore.envList[0]?.id ?? null
  planDialog.value = true
}

const createPlanFromTemplate = async (planType = 'regression', includeAutomation = false) => {
  const allScopes = await loadAllScopeRows()
  if (!allScopes.length) {
    ElMessage.warning('请先纳入测试范围用例')
    return
  }
  if (!proStore.envList?.length && projectId.value) {
    try {
      await proStore.getEnvList(projectId.value)
    } catch {
      /* ignore */
    }
  }
  const typeLabel = planTypeLabel(planType)
  const autoLabel = includeAutomation ? '（含自动化）' : ''
  planSaving.value = true
  try {
    const res = await testPlanApi.create({
      project_id: projectId.value,
      release_id: releaseId.value,
      name: `${release.value?.name || ''} ${typeLabel}计划${autoLabel}`.trim(),
      plan_type: planType,
      environment_id: proStore.envList?.[0]?.id || null,
      from_scope: true,
      include_automation: !!includeAutomation
    })
    ElMessage.success(`已创建${typeLabel}计划`)
    const id = res.data?.data?.id
    if (id) router.push(`/test-plans/${id}`)
    else await loadPlans()
  } finally {
    planSaving.value = false
  }
}

const genAutomationForPrimaryPlan = async (planId) => {
  const id = planId || primaryPlanId.value
  if (!id) {
    ElMessage.warning('请先创建测试计划')
    goTab('plans')
    return
  }
  try {
    const res = await testPlanApi.generateAutomationFromScope(id, projectId.value)
    ElMessage.success(`新增自动化项 ${res.data?.data?.created || 0} 个`)
    await loadPlans()
    await loadWorkflowPhase2()
    router.push(`/test-plans/${id}`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '补齐失败')
  }
}

const onScopeSelectionChange = (rows) => {
  selectedScopeIds.value = (rows || []).map((r) => r.id).filter(Boolean)
}

const submitBatchUpdate = async () => {
  if (!selectedScopeIds.value.length) {
    ElMessage.warning('请先勾选范围项')
    return
  }
  if (!batchForm.risk_level && !batchForm.clear_owner && !batchForm.owner_id) {
    ElMessage.warning('请至少选择风险或负责人')
    return
  }
  batchSaving.value = true
  try {
    const payload = {
      scope_ids: selectedScopeIds.value,
      clear_owner: !!batchForm.clear_owner
    }
    if (batchForm.risk_level) payload.risk_level = batchForm.risk_level
    if (!batchForm.clear_owner && batchForm.owner_id) {
      payload.owner_id = batchForm.owner_id
    }
    const res = await testReleaseApi.batchUpdateScopes(releaseId.value, projectId.value, payload)
    const d = res.data?.data || {}
    ElMessage.success(`已更新 ${d.updated || 0} 项`)
    batchDialog.value = false
    batchForm.risk_level = ''
    batchForm.owner_id = null
    batchForm.clear_owner = false
    selectedScopeIds.value = []
    await loadAll()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '批量更新失败')
  } finally {
    batchSaving.value = false
  }
}

const submitCreatePlan = async () => {
  const name = planForm.name.trim()
  if (!name) {
    ElMessage.warning('请填写名称')
    return
  }
  planSaving.value = true
  try {
    const res = await testPlanApi.create({
      project_id: projectId.value,
      release_id: releaseId.value,
      name,
      plan_type: planForm.plan_type,
      environment_id: planForm.environment_id || null,
      from_scope: true,
      include_automation: !!planForm.include_automation
    })
    planDialog.value = false
    ElMessage.success('已创建计划')
    const id = res.data?.data?.id
    if (id) router.push(`/test-plans/${id}`)
    else await loadPlans()
  } finally {
    planSaving.value = false
  }
}

const doTransition = async (target) => {
  const ok = await confirmReleaseStatusChange({
    target,
    releaseId: releaseId.value,
    projectId: projectId.value,
    releaseName: release.value?.name || release.value?.release_key || '',
    canViewQuality: canQualityView.value
  })
  if (!ok) return
  try {
    const res = await testReleaseApi.transition(releaseId.value, projectId.value, target)
    const data = res.data?.data
    const warnings = data?.warnings || []
    ElMessage.success(`已变更为 ${releaseStatusLabel(target)}`)
    if (warnings.length) {
      ElMessage.warning(warnings.join('；'))
    }
    await loadAll()
    if (canQualityView.value) await loadQuality()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '状态变更失败')
  }
}

const loadQuality = async () => {
  if (!canQualityView.value || !projectId.value || !releaseId.value) return
  qualityLoading.value = true
  try {
    const [previewRes, snapRes, reportRes] = await Promise.all([
      testReleaseApi.qualityPreview(releaseId.value, projectId.value),
      testReleaseApi.listQualitySnapshots(releaseId.value, projectId.value),
      testReleaseApi.qualityReport(releaseId.value, projectId.value)
    ])
    qualityPreview.value = previewRes.data?.data
      ? { ...previewRes.data.data, previewed_at: new Date().toISOString() }
      : null
    qualitySnapshots.value = snapRes.data?.data || []
    qualityReport.value = reportRes.data?.data || null
    if (qualityPreview.value) markQualityPreviewed()
  } catch (e) {
    qualityPreview.value = null
    qualitySnapshots.value = []
    qualityReport.value = null
    const detail = e?.response?.data?.detail ?? e?.data?.detail
    const isTm =
      detail &&
      typeof detail === 'object' &&
      (detail.code === 'tm_premium_required' || detail.code === 'tm_premium_incompatible')
    // 扩展包未装：全局拦截器已提示一次，避免再弹「加载质量门禁失败」
    if (!isTm) {
      const msg =
        typeof detail === 'string'
          ? detail
          : detail?.message || e?.message || '加载质量门禁失败'
      ElMessage.error(msg)
    }
  } finally {
    qualityLoading.value = false
    await loadWorkflowPhase2()
  }
}

const createSnapshot = async () => {
  const latest = qualityPreview.value?.latest_snapshot
  let force = false
  // 仅当仍有「有效豁免」时才需 force；过期豁免可直接覆盖
  if (qualityPreview.value?.has_valid_waiver || latest?.waiver_valid) {
    try {
      await ElMessageBox.confirm(
        '最近快照为有条件通过（豁免）。重新生成可能覆盖豁免结论，是否继续？',
        '覆盖豁免确认',
        { type: 'warning', confirmButtonText: '强制覆盖', cancelButtonText: '取消' }
      )
      force = true
    } catch {
      return
    }
  }
  snapshotSaving.value = true
  try {
    await testReleaseApi.createQualitySnapshot(releaseId.value, projectId.value, { force })
    ElMessage.success('质量快照已生成')
    await loadAll()
    await loadQuality()
  } catch (e) {
    const detail = e?.response?.data?.detail || ''
    if (String(detail).includes('force=true')) {
      try {
        await ElMessageBox.confirm(detail, '覆盖豁免确认', {
          type: 'warning',
          confirmButtonText: '强制覆盖'
        })
        await testReleaseApi.createQualitySnapshot(releaseId.value, projectId.value, { force: true })
        ElMessage.success('质量快照已生成')
        await loadAll()
        await loadQuality()
      } catch {
        /* 取消 */
      }
    } else {
      ElMessage.error(detail || '生成失败')
    }
  } finally {
    snapshotSaving.value = false
  }
}

const submitWaiver = async () => {
  if (!waiverForm.reason.trim()) {
    ElMessage.warning('请填写豁免原因')
    return
  }
  waiverSaving.value = true
  try {
    await testReleaseApi.approveQualityWaiver(releaseId.value, projectId.value, {
      reason: waiverForm.reason.trim(),
      note: waiverForm.note || null
    })
    ElMessage.success('已记录有条件通过')
    waiverDialog.value = false
    waiverForm.reason = ''
    waiverForm.note = ''
    await loadAll()
    await loadQuality()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '豁免失败')
  } finally {
    waiverSaving.value = false
  }
}

const goTraceability = () => {
  router.push({
    path: '/test-traceability',
    query: { release_id: String(releaseId.value) }
  })
}

const downloadExportPackage = async () => {
  if (!projectId.value || !releaseId.value) return
  exportingPackage.value = true
  try {
    const res = await testReleaseApi.downloadExportPackage(releaseId.value, projectId.value)
    const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: 'application/zip' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const key = (release.value?.release_key || releaseId.value).toString().replace(/[\\/]/g, '-')
    a.download = `release-export-${key}.zip`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已下载发布导出包')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '导出失败')
  } finally {
    exportingPackage.value = false
  }
}

const seedLinks = async () => {
  const res = await testAssetLinkApi.seedFromImports(projectId.value)
  const d = res.data?.data || {}
  ElMessage.success(`回填完成：新建 ${d.created || 0}，跳过 ${d.skipped || 0}`)
  await loadAll()
}

const openEditRelease = () => {
  if (!release.value) return
  editForm.release_key = release.value.release_key || ''
  editForm.name = release.value.name || ''
  editForm.description = release.value.description || ''
  editForm.external_url = release.value.external_url || ''
  editForm.owner_id = release.value.owner_id ?? null
  editReleaseVisible.value = true
}

const submitEditRelease = async () => {
  if (!editForm.name.trim()) {
    ElMessage.warning('名称不能为空')
    return
  }
  editSaving.value = true
  try {
    const payload = {
      name: editForm.name.trim(),
      description: editForm.description || null,
      external_url: editForm.external_url || null,
      owner_id: editForm.owner_id || null
    }
    if (release.value?.status === 'draft' && editForm.release_key.trim()) {
      payload.release_key = editForm.release_key.trim()
    }
    await testReleaseApi.update(releaseId.value, projectId.value, payload)
    ElMessage.success('已保存')
    editReleaseVisible.value = false
    await loadAll()
  } finally {
    editSaving.value = false
  }
}

const removeRelease = async () => {
  await ElMessageBox.confirm(`删除版本 ${release.value?.release_key}？`, '确认', { type: 'warning' })
  await testReleaseApi.remove(releaseId.value, projectId.value)
  ElMessage.success('已删除')
  router.push('/test-releases')
}

const removeReq = async (row) => {
  await ElMessageBox.confirm(`删除需求 ${row.requirement_key}？`, '确认')
  await testReleaseApi.deleteRequirement(releaseId.value, row.id, projectId.value)
  ElMessage.success('已删除')
  await loadRequirements()
}

const openReqPreview = (row) => {
  reqActiveRow.value = row
  reqImpactBanner.value = false
  reqPreviewVisible.value = true
}

const openReqEdit = (row) => {
  reqActiveRow.value = row
  reqUpdateMode.value = 'edit'
  reqUpdateVisible.value = true
}

const openReqUpgrade = (row) => {
  reqActiveRow.value = row
  reqUpdateMode.value = 'upgrade'
  reqUpdateVisible.value = true
}

const openReqEditFromPreview = () => {
  reqPreviewVisible.value = false
  reqUpdateMode.value = 'edit'
  reqUpdateVisible.value = true
}

const openReqReplaceFromPreview = () => {
  reqPreviewVisible.value = false
  reqUpdateMode.value = 'replace'
  reqUpdateVisible.value = true
}

const openReqUpgradeFromPreview = () => {
  reqPreviewVisible.value = false
  reqUpdateMode.value = 'upgrade'
  reqUpdateVisible.value = true
}

const onReqUpdated = async (payload = {}) => {
  await loadRequirements()
  if (payload.mode === 'replace') {
    reqImpactBanner.value = true
    reqReviewAiId.value = payload.aiRequirementId || parseAiRequirementId(reqActiveRow.value?.requirement_key)
    if (reqActiveRow.value) reqPreviewVisible.value = true
    if (payload.reviewStatusReset && reqReviewAiId.value) {
      await promptStartRequirementReview(reqReviewAiId.value)
    }
  }
}

const openScopeReqPreview = (scopeRow) => {
  const key = scopeRow?.requirement_key
  if (!key) return
  const found = findReleaseRequirement(requirements.value, { requirementKey: key })
  if (found) {
    openReqPreview(found)
    return
  }
  const aiId = parseAiRequirementId(key)
  if (aiId) {
    reqActiveRow.value = { requirement_key: key, title: key, source_type: 'ai', ai_requirement_id: aiId }
    reqImpactBanner.value = false
    reqPreviewVisible.value = true
    return
  }
  reqActiveRow.value = { requirement_key: key, title: key, source_type: 'external' }
  reqPreviewVisible.value = true
}

const promptStartRequirementReview = async (aiRequirementId) => {
  const id = Number(aiRequirementId)
  if (!id) return
  try {
    await ElMessageBox.confirm(
      '需求文档已变更，建议在本版本发起新一轮需求可测性评审。是否现在去发起？',
      '建议重新评审',
      { confirmButtonText: '去发起', cancelButtonText: '稍后', type: 'warning' }
    )
    tab.value = 'req-reviews'
    await nextTick()
    reqReviewRef.value?.openCreateForRequirement(id)
  } catch {
    /* 用户选择稍后 */
  }
}

const openPickCases = () => {
  pickVisible.value = true
}

const onScopesAdded = async () => {
  await loadAll()
}

const openLinks = (row) => {
  linkCaseId.value = row.functional_case_id
  linkCaseTitle.value = row.case_title || `#${row.functional_case_id}`
  linkVisible.value = true
}

const openScopeEdit = (row) => {
  scopeEditRow.value = row
  scopeEditVisible.value = true
}

const removeScope = async (row) => {
  await ElMessageBox.confirm(
    '从范围移除后，将同步移出进行中评审的对应项，以及草稿/就绪计划中的绑定项。已结束的评审与运行记录不受影响。',
    `确认移除用例 #${row.functional_case_id}？`
  )
  const res = await testReleaseApi.removeScope(releaseId.value, row.id, projectId.value)
  const d = res.data?.data || {}
  const parts = ['已从范围移除']
  if (d.review_items_removed) parts.push(`同步评审项 ${d.review_items_removed} 条`)
  if (d.plan_items_removed) parts.push(`同步计划项 ${d.plan_items_removed} 条`)
  ElMessage.success(parts.join('，'))
  await loadAll()
}

const defectDrawerRef = ref(null)
const defectReportRef = ref(null)
const openDefect = (row) => {
  if (!row?.id || !canDefectView.value) return
  defectDrawerRef.value?.open(row.id)
}
const onDefectSaved = async () => {
  await Promise.all([loadDefects(), loadDefectStats(), loadQuality().catch(() => null)])
}

watch([projectId, releaseId], () => loadAll())
watch(tab, (name) => {
  if (name === 'quality') loadQuality()
  const cur = route.query.tab ? String(route.query.tab) : 'overview'
  if (String(name) !== cur) {
    const query = { ...route.query }
    if (name === 'overview') delete query.tab
    else query.tab = name
    router.replace({ query })
  }
})
watch(
  () => route.query.tab,
  (v) => {
    const next = v ? String(v) : 'overview'
    if (tab.value !== next) tab.value = next
  },
  { immediate: true }
)
watch(
  () => route.query.owner_id,
  async () => {
    applyScopeOwnerFromRoute()
    if (tab.value === 'scopes' || route.query.tab === 'scopes') {
      await loadScopes()
    }
  }
)
onMounted(loadAll)
</script>

<style scoped>
.tm-release-detail {
  padding: 16px;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.title-row h2 {
  margin: 0;
  font-size: 20px;
}
.key {
  color: #909399;
  font-size: 13px;
}
.owner-chip {
  font-size: 12px;
  color: #475467;
  padding: 2px 10px;
  border-radius: 999px;
  background: #f2f4f7;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.stat-card {
  min-width: 140px;
}
.stat-card.wide {
  min-width: 260px;
}
.stat-card.clickable {
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.stat-card.clickable:hover {
  border-color: var(--el-color-primary-light-5);
}
.stat-num {
  font-size: 28px;
  font-weight: 600;
}
.stat-num.danger {
  color: var(--el-color-danger);
}
.stat-label {
  color: #909399;
  margin-bottom: 6px;
}
.stat-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #c0c4cc;
}
.muted {
  color: #909399;
  font-size: 13px;
}
.inner-link {
  color: var(--el-color-primary);
  text-decoration: none;
}
.inner-link:hover {
  text-decoration: underline;
}
.status-btn {
  color: var(--el-text-color-regular);
}
.status-dd-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 200px;
}
.status-dd-hint {
  color: #909399;
  font-size: 12px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.form-hint {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
.pane-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}
.clickable-rows :deep(.el-table__row) {
  cursor: pointer;
}
.snap-compare-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px 28px;
  align-items: center;
  font-size: 14px;
}
</style>
