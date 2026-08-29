import http from './request'

/**
 * 测试管理 Phase 1 API — /test-management/*
 */
export const testPremiumApi = {
  async status() {
    return await http.get('/test-management/premium-status', { skipErrorHandler: true })
  },
}

export const testReleaseApi = {
  async list(params = {}) {
    return await http.get('/test-management/releases', { params })
  },
  async create(data) {
    return await http.post('/test-management/releases', data, {
      params: { project_id: data.project_id }
    })
  },
  async get(id, projectId) {
    return await http.get(`/test-management/releases/${id}`, {
      params: { project_id: projectId }
    })
  },
  async update(id, projectId, data) {
    return await http.patch(`/test-management/releases/${id}`, data, {
      params: { project_id: projectId }
    })
  },
  async transition(id, projectId, status) {
    return await http.post(
      `/test-management/releases/${id}/transition`,
      { status },
      { params: { project_id: projectId } }
    )
  },
  async remove(id, projectId) {
    return await http.delete(`/test-management/releases/${id}`, {
      params: { project_id: projectId }
    })
  },
  async overview(id, projectId) {
    return await http.get(`/test-management/releases/${id}/overview`, {
      params: { project_id: projectId }
    })
  },
  async downloadExportPackage(id, projectId) {
    return await http.get(`/test-management/releases/${id}/export-package`, {
      params: { project_id: projectId },
      responseType: 'blob'
    })
  },
  async listRequirements(id, projectId) {
    return await http.get(`/test-management/releases/${id}/requirements`, {
      params: { project_id: projectId }
    })
  },
  async addRequirement(id, projectId, data) {
    return await http.post(`/test-management/releases/${id}/requirements`, data, {
      params: { project_id: projectId }
    })
  },
  async deleteRequirement(id, reqId, projectId) {
    return await http.delete(`/test-management/releases/${id}/requirements/${reqId}`, {
      params: { project_id: projectId }
    })
  },
  async updateRequirement(releaseId, reqId, projectId, data) {
    return await http.put(`/test-management/releases/${releaseId}/requirements/${reqId}`, data, {
      params: { project_id: projectId }
    })
  },
  async getRequirementPreview(releaseId, reqId, projectId) {
    return await http.get(`/test-management/releases/${releaseId}/requirements/${reqId}/preview`, {
      params: { project_id: projectId }
    })
  },
  async upgradeRequirementToAi(releaseId, reqId, projectId, data) {
    return await http.post(
      `/test-management/releases/${releaseId}/requirements/${reqId}/upgrade-to-ai`,
      data,
      { params: { project_id: projectId } }
    )
  },
  async listScopes(id, projectId, params = {}) {
    return await http.get(`/test-management/releases/${id}/scopes`, {
      params: { project_id: projectId, ...params }
    })
  },
  async addScopes(id, projectId, data) {
    return await http.post(`/test-management/releases/${id}/scopes`, data, {
      params: { project_id: projectId }
    })
  },
  async updateScope(id, scopeId, projectId, data) {
    return await http.patch(`/test-management/releases/${id}/scopes/${scopeId}`, data, {
      params: { project_id: projectId }
    })
  },
  async batchUpdateScopes(id, projectId, data) {
    return await http.post(`/test-management/releases/${id}/scopes/batch-update`, data, {
      params: { project_id: projectId }
    })
  },
  async notifyScopeOwners(id, projectId) {
    return await http.post(`/test-management/releases/${id}/scopes/notify-owners`, null, {
      params: { project_id: projectId }
    })
  },
  async removeScope(id, scopeId, projectId) {
    return await http.delete(`/test-management/releases/${id}/scopes/${scopeId}`, {
      params: { project_id: projectId }
    })
  },
  async qualityPreview(id, projectId) {
    return await http.get(`/test-management/releases/${id}/quality/preview`, {
      params: { project_id: projectId }
    })
  },
  async listQualitySnapshots(id, projectId, params = {}) {
    return await http.get(`/test-management/releases/${id}/quality/snapshots`, {
      params: { project_id: projectId, ...params }
    })
  },
  async createQualitySnapshot(id, projectId, data = {}) {
    return await http.post(`/test-management/releases/${id}/quality/snapshots`, data, {
      params: { project_id: projectId }
    })
  },
  async qualityReport(id, projectId, params = {}) {
    return await http.get(`/test-management/releases/${id}/quality/report`, {
      params: { project_id: projectId, ...params }
    })
  },
  async approveQualityWaiver(id, projectId, data) {
    return await http.post(`/test-management/releases/${id}/quality/waiver`, data, {
      params: { project_id: projectId }
    })
  },
  async getIntelligence(id, projectId) {
    return await http.get(`/test-management/releases/${id}/intelligence`, {
      params: { project_id: projectId }
    })
  },
  async getAiSummary(id, projectId) {
    /** 仅拉取缓存的 AI 总结（比 getIntelligence 轻量） */
    return await http.get(`/test-management/releases/${id}/intelligence/ai-summary`, {
      params: { project_id: projectId }
    })
  },
  async generateAiSummary(id, projectId, data = {}) {
    return await http.post(`/test-management/releases/${id}/intelligence/ai-summary`, data || {}, {
      params: { project_id: projectId },
      timeout: 120000,
      headers: { 'Content-Type': 'application/json' }
    })
  }
}

export const testAssetLinkApi = {
  async list(params = {}) {
    return await http.get('/test-management/asset-links', { params })
  },
  async create(data) {
    return await http.post('/test-management/asset-links', data, {
      params: { project_id: data.project_id }
    })
  },
  async update(linkId, projectId, data) {
    return await http.patch(`/test-management/asset-links/${linkId}`, data, {
      params: { project_id: projectId }
    })
  },
  async remove(linkId, projectId) {
    return await http.delete(`/test-management/asset-links/${linkId}`, {
      params: { project_id: projectId }
    })
  },
  async seedFromImports(projectId) {
    return await http.post('/test-management/asset-links/seed-from-imports', {
      project_id: projectId
    })
  },
  async previewAsset(projectId, assetType, assetId) {
    return await http.get('/test-management/asset-links/preview', {
      params: { project_id: projectId, asset_type: assetType, asset_id: assetId }
    })
  }
}

/** Phase 2：评审 */
export const testReviewApi = {
  async listTemplates(projectId) {
    return await http.get('/test-management/review-templates', {
      params: { project_id: projectId }
    })
  },
  async createTemplate(data) {
    return await http.post('/test-management/review-templates', data, {
      params: { project_id: data.project_id }
    })
  },
  async list(params = {}) {
    return await http.get('/test-management/reviews', { params })
  },
  async create(data) {
    return await http.post('/test-management/reviews', data, {
      params: { project_id: data.project_id }
    })
  },
  async get(id, projectId) {
    return await http.get(`/test-management/reviews/${id}`, {
      params: { project_id: projectId }
    })
  },
  async submitDecision(reviewId, itemId, projectId, data) {
    return await http.post(
      `/test-management/reviews/${reviewId}/items/${itemId}/decision`,
      data,
      { params: { project_id: projectId } }
    )
  },
  async finalize(reviewId, projectId, data) {
    return await http.post(`/test-management/reviews/${reviewId}/finalize`, data, {
      params: { project_id: projectId }
    })
  },
  async finalizeItem(reviewId, itemId, projectId, data) {
    return await http.post(
      `/test-management/reviews/${reviewId}/items/${itemId}/finalize`,
      data,
      { params: { project_id: projectId } }
    )
  },
  async uploadAttachment(projectId, file, onProgress) {
    const form = new FormData()
    form.append('file', file)
    return await http.post(
      `/test-management/reviews/attachments/upload?project_id=${projectId}`,
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: onProgress,
        timeout: 120000,
      }
    )
  },
  async attachmentUrl(projectId, key, bucket) {
    return await http.get('/test-management/reviews/attachments/url', {
      params: { project_id: projectId, key, bucket: bucket || undefined }
    })
  },
  async cancel(reviewId, projectId) {
    return await http.post(`/test-management/reviews/${reviewId}/cancel`, null, {
      params: { project_id: projectId }
    })
  },
  async updateTemplate(templateId, projectId, data) {
    return await http.patch(`/test-management/review-templates/${templateId}`, data, {
      params: { project_id: projectId }
    })
  },
  async removeTemplate(templateId, projectId) {
    return await http.delete(`/test-management/review-templates/${templateId}`, {
      params: { project_id: projectId }
    })
  }
}

/** Phase 2：计划与手工运行 */
export const testPlanApi = {
  async list(projectId, releaseId) {
    return await http.get('/test-management/plans', {
      params: { project_id: projectId, release_id: releaseId }
    })
  },
  async create(data) {
    return await http.post('/test-management/plans', data, {
      params: { project_id: data.project_id }
    })
  },
  async get(id, projectId) {
    return await http.get(`/test-management/plans/${id}`, {
      params: { project_id: projectId }
    })
  },
  async update(id, projectId, data) {
    return await http.patch(`/test-management/plans/${id}`, data, {
      params: { project_id: projectId }
    })
  },
  async remove(id, projectId) {
    return await http.delete(`/test-management/plans/${id}`, {
      params: { project_id: projectId }
    })
  },
  async removeItem(planId, itemId, projectId) {
    return await http.delete(`/test-management/plans/${planId}/items/${itemId}`, {
      params: { project_id: projectId }
    })
  },
  async generateFromScope(id, projectId, scopeIds) {
    return await http.post(
      `/test-management/plans/${id}/generate-from-scope`,
      null,
      {
        params: {
          project_id: projectId,
          scope_ids: scopeIds?.length ? scopeIds.join(',') : undefined
        }
      }
    )
  },
  async createRun(planId, projectId, data = {}) {
    return await http.post(`/test-management/plans/${planId}/runs`, data, {
      params: { project_id: projectId }
    })
  },
  async getRun(runId, projectId) {
    return await http.get(`/test-management/plan-runs/${runId}`, {
      params: { project_id: projectId }
    })
  },
  async submitManualResult(runId, itemId, projectId, data) {
    return await http.post(
      `/test-management/plan-runs/${runId}/items/${itemId}/manual-result`,
      data,
      { params: { project_id: projectId } }
    )
  },
  async updateRunItemAssignee(runId, itemId, projectId, data) {
    return await http.patch(
      `/test-management/plan-runs/${runId}/items/${itemId}/assignee`,
      data,
      { params: { project_id: projectId } }
    )
  },
  async listAttempts(runId, itemId, projectId) {
    return await http.get(
      `/test-management/plan-runs/${runId}/items/${itemId}/attempts`,
      { params: { project_id: projectId } }
    )
  },
  async cancelRun(runId, projectId) {
    return await http.post(`/test-management/plan-runs/${runId}/cancel`, null, {
      params: { project_id: projectId }
    })
  },
  async generateAutomationFromScope(id, projectId, scopeIds) {
    return await http.post(
      `/test-management/plans/${id}/generate-automation-from-scope`,
      null,
      {
        params: {
          project_id: projectId,
          scope_ids: scopeIds?.length ? scopeIds.join(',') : undefined
        }
      }
    )
  },
  async dispatchAutomation(runId, projectId, data = {}) {
    return await http.post(
      `/test-management/plan-runs/${runId}/dispatch-automation`,
      data,
      { params: { project_id: projectId } }
    )
  },
  async syncAutomation(runId, projectId) {
    return await http.post(
      `/test-management/plan-runs/${runId}/sync-automation`,
      null,
      { params: { project_id: projectId } }
    )
  }
}

/** Phase 3：缺陷 */
export const testDefectApi = {
  async list(params = {}) {
    return await http.get('/test-management/defects', { params })
  },
  async stats(projectId, params = {}) {
    return await http.get('/test-management/defects/stats', {
      params: { project_id: projectId, ...params }
    })
  },
  async create(data) {
    return await http.post('/test-management/defects', data, {
      params: { project_id: data.project_id }
    })
  },
  async get(id, projectId) {
    return await http.get(`/test-management/defects/${id}`, {
      params: { project_id: projectId }
    })
  },
  async update(id, projectId, data) {
    return await http.patch(`/test-management/defects/${id}`, data, {
      params: { project_id: projectId }
    })
  },
  async transition(id, projectId, data) {
    return await http.post(`/test-management/defects/${id}/transition`, data, {
      params: { project_id: projectId }
    })
  },
  async remove(id, projectId) {
    return await http.delete(`/test-management/defects/${id}`, {
      params: { project_id: projectId }
    })
  },
  async createFromRunItem(itemId, projectId, runId, data = {}) {
    return await http.post(
      `/test-management/plan-run-items/${itemId}/defects`,
      data,
      { params: { project_id: projectId, run_id: runId } }
    )
  },
  async releaseStats(releaseId, projectId) {
    return await http.get(`/test-management/releases/${releaseId}/defect-stats`, {
      params: { project_id: projectId }
    })
  },
  async releaseReport(releaseId, projectId, params = {}) {
    return await http.get(`/test-management/releases/${releaseId}/defect-report`, {
      params: { project_id: projectId, ...params }
    })
  },
  async uploadAttachment(projectId, file, onProgress) {
    const form = new FormData()
    form.append('file', file)
    return await http.post(
      `/test-management/defects/attachments/upload?project_id=${projectId}`,
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: onProgress,
        timeout: 120000,
      }
    )
  },
  async attachmentUrl(projectId, key, bucket) {
    return await http.get('/test-management/defects/attachments/url', {
      params: { project_id: projectId, key, bucket: bucket || undefined }
    })
  },
  async addComment(id, projectId, body) {
    return await http.post(
      `/test-management/defects/${id}/comments`,
      { body },
      { params: { project_id: projectId } }
    )
  },
  async removeComment(id, commentId, projectId) {
    return await http.delete(`/test-management/defects/${id}/comments/${commentId}`, {
      params: { project_id: projectId }
    })
  },
  async addLink(id, projectId, data) {
    return await http.post(`/test-management/defects/${id}/links`, data, {
      params: { project_id: projectId }
    })
  },
  async removeLink(id, linkId, projectId) {
    return await http.delete(`/test-management/defects/${id}/links/${linkId}`, {
      params: { project_id: projectId }
    })
  }
}

export const testTraceApi = {
  async matrix(projectId, releaseId, params = {}) {
    return await http.get('/test-management/traceability/matrix', {
      params: {
        project_id: projectId,
        release_id: releaseId || undefined,
        ...params
      }
    })
  },
  async coverage(projectId, releaseId) {
    return await http.get('/test-management/traceability/coverage', {
      params: { project_id: projectId, release_id: releaseId || undefined }
    })
  },
  async caseLifecycle(projectId, caseId) {
    return await http.get(`/test-management/functional-cases/${caseId}/lifecycle`, {
      params: { project_id: projectId }
    })
  }
}

export const testRequirementReviewApi = {
  async list(projectId, opts = {}) {
    const requirementId = typeof opts === 'number' ? opts : opts?.requirementId
    const releaseId = typeof opts === 'object' ? opts?.releaseId : undefined
    return await http.get('/test-management/requirement-reviews', {
      params: {
        project_id: projectId,
        requirement_id: requirementId,
        release_id: releaseId
      }
    })
  },
  async create(data) {
    return await http.post('/test-management/requirement-reviews', data, {
      params: { project_id: data.project_id }
    })
  },
  async get(reviewId, projectId) {
    return await http.get(`/test-management/requirement-reviews/${reviewId}`, {
      params: { project_id: projectId }
    })
  },
  async addItem(reviewId, projectId, data) {
    return await http.post(`/test-management/requirement-reviews/${reviewId}/items`, data, {
      params: { project_id: projectId }
    })
  },
  async submitDecision(reviewId, projectId, data) {
    return await http.post(`/test-management/requirement-reviews/${reviewId}/decision`, data, {
      params: { project_id: projectId }
    })
  },
  async complete(reviewId, projectId, data) {
    return await http.post(`/test-management/requirement-reviews/${reviewId}/complete`, data, {
      params: { project_id: projectId }
    })
  },
  async reopen(requirementId, projectId) {
    return await http.post(
      `/test-management/ai-requirements/${requirementId}/reopen-review`,
      null,
      { params: { project_id: projectId } }
    )
  }
}
