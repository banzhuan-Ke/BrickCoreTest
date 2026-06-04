import http from '../request'

// ========== 平台内 AI 助手（Phase 2/3） ==========
export const aiAssistantApi = {
    async getQuickPrompts() {
        return await http.get('/ai/assistant/quick-prompts')
    },
    async listSessions(projectId, keyword = '') {
        return await http.get('/ai/assistant/sessions', {
            params: {
                project_id: projectId ?? null,
                keyword: keyword || undefined
            }
        })
    },
    async createSession(projectId, title = '新对话') {
        return await http.post('/ai/assistant/sessions', {
            project_id: projectId ?? null,
            title
        })
    },
    async renameSession(sessionId, title) {
        return await http.patch(`/ai/assistant/sessions/${sessionId}`, { title })
    },
    async deleteSession(sessionId) {
        return await http.delete(`/ai/assistant/sessions/${sessionId}`)
    },
    async getSession(projectId, sessionId = null) {
        return await http.get('/ai/assistant/session', {
            params: {
                project_id: projectId ?? null,
                session_id: sessionId ?? null
            }
        })
    },
    async clearSession(projectId, sessionId = null) {
        return await http.delete('/ai/assistant/session', {
            params: {
                project_id: projectId ?? null,
                session_id: sessionId ?? null
            }
        })
    },
    /** 一次性返回完整回答（无 SSE） */
    async chat(message, { projectId, history = [], aiConfigId, sessionId, useServerHistory = true, pageContext = null } = {}) {
        return await http.post(
            '/ai/assistant/chat',
            {
                message,
                project_id: projectId ?? null,
                history,
                ai_config_id: aiConfigId ?? null,
                session_id: sessionId ?? null,
                use_server_history: useServerHistory,
                page_context: pageContext || null
            },
            { timeout: 300000 }
        )
    },
    async confirm({ action, confirmToken, confirmArgs = {}, projectId, sessionId } = {}) {
        return await http.post(
            '/ai/assistant/confirm',
            {
                action,
                confirm_token: confirmToken,
                confirm_args: confirmArgs,
                project_id: projectId ?? null,
                session_id: sessionId ?? null
            },
            { timeout: 300000 }
        )
    }
}
