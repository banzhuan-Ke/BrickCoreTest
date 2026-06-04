import http from '../request'

/** Backend StandardResponse: { code, message, data } → 解包为业务 data */
function unwrap(res) {
    const body = res?.data
    if (body != null && typeof body === 'object' && body.code === 200 && 'data' in body) {
        return { ...res, data: body.data }
    }
    return res
}

async function apiGet(url, config) {
    return unwrap(await http.get(url, config))
}

async function apiPost(url, data, config) {
    return unwrap(await http.post(url, data, config))
}

async function apiPut(url, data, config) {
    return unwrap(await http.put(url, data, config))
}

async function apiDelete(url, config) {
    return unwrap(await http.delete(url, config))
}

export const dataFactoryApi = {
    listDatasources(params) {
        return apiGet('/api-module/data-factory/datasources', { params })
    },
    createDatasource(data) {
        return apiPost('/api-module/data-factory/datasources', data)
    },
    updateDatasource(id, data) {
        return apiPut(`/api-module/data-factory/datasources/${id}`, data)
    },
    deleteDatasource(id) {
        return apiDelete(`/api-module/data-factory/datasources/${id}`)
    },
    testDatasource(id, data) {
        return apiPost(`/api-module/data-factory/datasources/${id}/test`, data || {})
    },
    testConnectionPreview(data) {
        return apiPost('/api-module/data-factory/datasources/test-connection', data)
    },
    listSqlTemplates(params) {
        return apiGet('/api-module/data-factory/sql-templates', { params })
    },
    createSqlTemplate(data) {
        return apiPost('/api-module/data-factory/sql-templates', data)
    },
    updateSqlTemplate(id, data) {
        return apiPut(`/api-module/data-factory/sql-templates/${id}`, data)
    },
    deleteSqlTemplate(id) {
        return apiDelete(`/api-module/data-factory/sql-templates/${id}`)
    },
    executeSql(data) {
        return apiPost('/api-module/data-factory/sql/execute', data)
    },
    executeTemplate(data) {
        return apiPost('/api-module/data-factory/sql-templates/execute', data)
    },
    testDbAssertions(data) {
        return apiPost('/api-module/data-factory/db-assertions/test', data)
    },
}
