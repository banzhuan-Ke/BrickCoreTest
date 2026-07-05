import http from '../request'

const prefix = '/app-module'

export const appCaseApi = {
  list: (params) => http.get(`${prefix}/cases`, { params }),
  detail: (id) => http.get(`${prefix}/cases/${id}`),
  getExecutionHints: (id, params = {}) => http.get(`${prefix}/cases/${id}/execution-hints`, { params }),
  create: (data) => http.post(`${prefix}/cases`, data),
  update: (id, data) => http.put(`${prefix}/cases/${id}`, data),
  remove: (id) => http.delete(`${prefix}/cases/${id}`),
  copy: (id, data) => http.post(`${prefix}/cases/${id}/copy`, data || {}),
}

export const appSuiteApi = {
  list: (params) => http.get(`${prefix}/suites`, { params }),
  detail: (id) => http.get(`${prefix}/suites/${id}`),
  create: (data) => http.post(`${prefix}/suites`, data),
  update: (id, data) => http.put(`${prefix}/suites/${id}`, data),
  remove: (id) => http.delete(`${prefix}/suites/${id}`),
  listCases: (suiteId) => http.get(`${prefix}/suites/${suiteId}/cases`),
  addCase: (suiteId, data) => http.post(`${prefix}/suites/${suiteId}/cases`, data),
  replaceCases: (suiteId, data) => http.put(`${prefix}/suites/${suiteId}/cases`, data),
}

export const appPlanApi = {
  list: (params) => http.get(`${prefix}/plans`, { params }),
  detail: (id) => http.get(`${prefix}/plans/${id}`),
  create: (data) => http.post(`${prefix}/plans`, data),
  update: (id, data) => http.put(`${prefix}/plans/${id}`, data),
  remove: (id) => http.delete(`${prefix}/plans/${id}`),
  updateSuites: (id, data) => http.put(`${prefix}/plans/${id}/suites`, data),
  listSuites: (id) => http.get(`${prefix}/plans/${id}/suites`),
}

export const appExecApi = {
  runCase: (caseId, data) => http.post(`${prefix}/exec/cases/${caseId}`, data),
  debugCase: (caseId, data) => http.post(`${prefix}/exec/cases/${caseId}/debug`, data, { timeout: 300000 }),
  runSuite: (suiteId, data) => http.post(`${prefix}/exec/suites/${suiteId}`, data),
  runPlan: (planId, data) => http.post(`${prefix}/exec/plans/${planId}`, data),
  stopPlan: (recordId) => http.post(`${prefix}/exec/stop/${recordId}`),
  stopSuite: (recordId) => http.post(`${prefix}/exec/stop/suite/${recordId}`),
  stopCase: (recordId) => http.post(`${prefix}/exec/stop/case/${recordId}`),
}

export const appFragmentApi = {
  list: (params) => http.get(`${prefix}/fragments`, { params }),
  detail: (id, projectId) => http.get(`${prefix}/fragments/${id}`, { params: { project_id: projectId } }),
  getDetail: (id, projectId) => http.get(`${prefix}/fragments/${id}`, { params: { project_id: projectId } }),
  create: (data) => http.post(`${prefix}/fragments`, data),
  update: (id, data, projectId) => http.put(`${prefix}/fragments/${id}`, data, { params: { project_id: projectId } }),
  remove: (id, projectId, force = false) => http.delete(`${prefix}/fragments/${id}`, { params: { project_id: projectId, force } }),
  references: (id, projectId) => http.get(`${prefix}/fragments/${id}/references`, { params: { project_id: projectId } }),
  previewExpand: (id, data) => http.post(`${prefix}/fragments/${id}/expand`, data),
}

export const appCronApi = {
  list: (params) => http.get(`${prefix}/cron`, { params }),
  detail: (id) => http.get(`${prefix}/cron/${id}`),
  create: (data) => http.post(`${prefix}/cron`, data),
  update: (id, data) => http.put(`${prefix}/cron/${id}`, data),
  remove: (id) => http.delete(`${prefix}/cron/${id}`),
  toggle: (id) => http.post(`${prefix}/cron/${id}/toggle`),
  runNow: (id) => http.post(`${prefix}/cron/${id}/run-now`),
  records: (id, params) => http.get(`${prefix}/cron/${id}/records`, { params }),
}

export const appRecordApi = {
  listPlans: (params) => http.get(`${prefix}/records/plans`, { params }),
  listSuites: (params) => http.get(`${prefix}/records/suites`, { params }),
  listCases: (params) => http.get(`${prefix}/records/cases`, { params }),
  planDetail: (id) => http.get(`${prefix}/records/plans/${id}`),
  suiteDetail: (id) => http.get(`${prefix}/records/suites/${id}`),
  caseDetail: (id) => http.get(`${prefix}/records/cases/${id}`),
  exportReport: (recordId, params) => http.get(`${prefix}/records/export/${recordId}`, { params, responseType: 'blob' }),
  exportReportAsync: (recordId, params) => http.post(`${prefix}/records/export-async/${recordId}`, null, { params }),
  exportStatus: (taskId) => http.get(`${prefix}/records/export-status/${taskId}`),
  deletePlan: (id) => http.delete(`${prefix}/records/plans/${id}`),
  deleteSuite: (id) => http.delete(`${prefix}/records/suites/${id}`),
  deleteCase: (id, params = {}) => http.delete(`${prefix}/records/cases/${id}`, { params }),
  batchDeleteCases: (record_ids, permanent = false) =>
    http.post(`${prefix}/records/cases/batch-delete`, { record_ids, permanent }),
  batchRestoreCases: (record_ids) =>
    http.post(`${prefix}/records/cases/batch-restore`, { record_ids, permanent: false }),
  restorePlan: (id) => http.post(`${prefix}/records/plans/${id}/restore`),
  restoreSuite: (id) => http.post(`${prefix}/records/suites/${id}/restore`),
  restoreCase: (id) => http.post(`${prefix}/records/cases/${id}/restore`),
  sendPlanReport: (id, data) => http.post(`${prefix}/records/plans/${id}/send-report`, data || {}),
  sendSuiteReport: (id, data) => http.post(`${prefix}/records/suites/${id}/send-report`, data || {}),
}

export const appElementApi = {
  list: (params) => http.get(`${prefix}/elements`, { params }),
  options: (params) => http.get(`${prefix}/elements/options`, { params }),
  detail: (id) => http.get(`${prefix}/elements/${id}`),
  create: (data) => http.post(`${prefix}/elements`, data, { skipErrorHandler: true }),
  update: (id, data) => http.put(`${prefix}/elements/${id}`, data, { skipErrorHandler: true }),
  remove: (id) => http.delete(`${prefix}/elements/${id}`, { skipErrorHandler: true }),
  references: (id) => http.get(`${prefix}/elements/${id}/references`),
  uploadTemplate: (projectId, file, onProgress) => {
    const form = new FormData()
    form.append('file', file)
    return http.post(`${prefix}/elements/upload-template?project_id=${projectId}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
      onUploadProgress: onProgress,
      skipErrorHandler: true,
    })
  },
  getScreenshot: (sessionId) =>
    http.get(`${prefix}/inspector/sessions/${sessionId}/screenshot`, {
      responseType: 'blob',
      timeout: 120000,
      skipErrorHandler: true,
    }),
  presignTemplates: (projectId, objectKeys) =>
    http.post(`${prefix}/elements/template-presign?project_id=${projectId}`, { object_keys: objectKeys }),
}

export const appInspectorApi = {
  createSession: (data) => http.post(`${prefix}/inspector/sessions`, data),
  getSession: (sessionId) => http.get(`${prefix}/inspector/sessions/${sessionId}`),
  getScreenshot: (sessionId) =>
    http.get(`${prefix}/inspector/sessions/${sessionId}/screenshot`, {
      responseType: 'blob',
      timeout: 120000,
      skipErrorHandler: true,
    }),
  dump: (sessionId) => http.post(`${prefix}/inspector/sessions/${sessionId}/dump`),
  webviewProbe: (sessionId, data) => http.post(`${prefix}/inspector/sessions/${sessionId}/webview-probe`, data),
  explore: (sessionId, data) => http.post(`${prefix}/inspector/sessions/${sessionId}/explore`, data),
  refreshScreenshot: (sessionId) => http.post(`${prefix}/inspector/sessions/${sessionId}/screenshot-refresh`),
  close: (sessionId) => http.delete(`${prefix}/inspector/sessions/${sessionId}`),
}
