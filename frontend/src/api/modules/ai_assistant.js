import http from '../request'

// ========== 平台内 AI 助手（Phase 2/3） ==========
export const aiAssistantApi = {
    async getQuickPrompts() {
        return await http.get('/ai/assistant/quick-prompts')
    },
    async prepareSkillChipForm({
        chipKey,
        projectId,
        sessionId = null,
        chipLabel = '',
        chipMessage = '',
        pageContext = null
    }) {
        return await http.post('/ai/assistant/skill-chips/prepare', {
            chip_key: chipKey,
            project_id: projectId,
            session_id: sessionId,
            chip_label: chipLabel || '',
            chip_message: chipMessage || '',
            page_context: pageContext
        })
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
    /** 扩展包 / 模式探测（W0） */
    async getCapabilities() {
        return await http.get('/ai/assistant/capabilities')
    },
    async listSkills() {
        return await http.get('/ai/assistant/skills')
    },
    async runSkill({
        skillCode,
        projectId,
        query,
        mode,
        folderIds,
        documentIds,
        targetType,
        targetId,
        requirementId,
        apiDefinitionId,
        count,
        catalogId,
        limit = 3,
        forceRefresh = false,
        aiConfigId,
        sessionId
    } = {}) {
        return await http.post(
            '/ai/assistant/skills/run',
            {
                skill_code: skillCode,
                project_id: projectId,
                query: query ?? null,
                mode: mode ?? null,
                folder_ids: folderIds ?? null,
                document_ids: documentIds ?? null,
                target_type: targetType ?? null,
                target_id: targetId ?? null,
                requirement_id: requirementId ?? null,
                api_definition_id: apiDefinitionId ?? null,
                count: count ?? null,
                catalog_id: catalogId ?? null,
                limit,
                force_refresh: forceRefresh,
                ai_config_id: aiConfigId ?? null,
                session_id: sessionId ?? null
            },
            { timeout: 300000 }
        )
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
    },
    async cancelConfirm({ action, confirmToken, projectId, sessionId } = {}) {
        return await http.post('/ai/assistant/confirm/cancel', {
            action,
            confirm_token: confirmToken,
            project_id: projectId ?? null,
            session_id: sessionId
        })
    },
    /** W2：钉住实体 */
    async pinContext({ sessionId, projectId, entityType, entityId, label = '', meta = {} } = {}) {
        return await http.post('/ai/assistant/context/pin', {
            session_id: sessionId,
            project_id: projectId ?? null,
            entity_type: entityType,
            entity_id: entityId,
            label,
            meta
        })
    },
    async unpinContext({ sessionId, projectId, entityType, entityId } = {}) {
        return await http.post('/ai/assistant/context/unpin', {
            session_id: sessionId,
            project_id: projectId ?? null,
            entity_type: entityType,
            entity_id: entityId
        })
    },
    async getContext(sessionId, projectId = null) {
        return await http.get('/ai/assistant/context', {
            params: {
                session_id: sessionId,
                project_id: projectId ?? null
            }
        })
    },
    /** W2：回答 AskUser 卡片 */
    async answerAskUser({
        sessionId,
        projectId,
        askId,
        answers = {},
        continueChat = true,
        pageContext = null
    } = {}) {
        return await http.post(
            '/ai/assistant/ask-user/answer',
            {
                session_id: sessionId,
                project_id: projectId ?? null,
                ask_id: askId,
                answers,
                continue_chat: continueChat,
                page_context: pageContext || null
            },
            { timeout: 300000 }
        )
    },
    /** W3：会话 Job 列表（轮询刷新 Browser Lab 等） */
    async listJobs(sessionId, projectId = null, refresh = true) {
        return await http.get('/ai/assistant/jobs', {
            params: {
                session_id: sessionId,
                project_id: projectId ?? null,
                refresh
            }
        })
    },
    async cancelJob(linkId) {
        return await http.post(`/ai/assistant/jobs/${linkId}/cancel`)
    },
    async listMemory(projectId) {
        return await http.get('/ai/assistant/memory', {
            params: { project_id: projectId }
        })
    },
    async putMemory({ projectId, key, value }) {
        return await http.put('/ai/assistant/memory', {
            project_id: projectId,
            key,
            value
        })
    },
    async deleteMemory(projectId, key) {
        return await http.delete('/ai/assistant/memory', {
            params: { project_id: projectId, key }
        })
    },
    async clearMemory(projectId) {
        return await http.delete('/ai/assistant/memory/all', {
            params: { project_id: projectId }
        })
    },
    async postFeedback({ sessionId, messageId, score, note = '', projectId = null }) {
        return await http.post('/ai/assistant/feedback', {
            session_id: sessionId,
            message_id: messageId,
            score,
            note,
            project_id: projectId
        })
    },
    async getFeedbackSummary({ days = 30, projectId = null } = {}) {
        return await http.get('/ai/assistant/feedback/summary', {
            params: {
                days,
                project_id: projectId ?? null
            }
        })
    },
    async listTraces({ projectId = null, sessionId = null, userId = null, limit = 50, offset = 0 } = {}) {
        return await http.get('/ai/assistant/traces', {
            params: {
                project_id: projectId ?? null,
                session_id: sessionId ?? null,
                user_id: userId ?? null,
                limit,
                offset
            }
        })
    },
    async getTrace(traceId) {
        return await http.get(`/ai/assistant/traces/${traceId}`)
    },
    async getSkillsOverview({ days = 30, projectId = null, recentLimit = 20 } = {}) {
        return await http.get('/ai/assistant/skills/overview', {
            params: {
                days,
                project_id: projectId ?? null,
                recent_limit: recentLimit
            }
        })
    },
    async getSkillRuns({
        days = 30,
        projectId = null,
        skillCode = null,
        status = null,
        entrySource = null,
        runMode = null,
        page = 1,
        size = 20
    } = {}) {
        return await http.get('/ai/assistant/skills/runs', {
            params: {
                days,
                project_id: projectId ?? null,
                skill_code: skillCode || null,
                status: status || null,
                entry_source: entrySource || null,
                run_mode: runMode || null,
                page,
                size
            }
        })
    }
}
