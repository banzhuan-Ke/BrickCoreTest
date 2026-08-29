import http from '../request'

export const stabilityApi = {
  async listCases(params) {
    return await http.get('/stability/cases', { params })
  },
  async getCase(caseId, params) {
    return await http.get(`/stability/cases/${caseId}`, { params })
  },
  async setQuarantine(caseId, data) {
    return await http.post(`/stability/cases/${caseId}/quarantine`, data)
  },
}
