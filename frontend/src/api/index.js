/**
 * API统一入口 - 新版
 * 兼容旧版API调用方式，同时支持新的模块化导入
 * 
 * 推荐使用方式：
 * import { userApi, uiCaseApi, httpApi } from '@/api'
 * 
 * 兼容旧代码：
 * import api from '@/api'
 * api.userApi.LoginApi(data)
 */

import { 
    userApi, roleApi, inviteCodeApi, projectApi, envApi, deviceApi, moduleApi, catalogApi, dashboardApi, operationLogApi, notificationApi,
    uiCaseApi, uiSuiteApi, uiTaskApi, uiExecApi, uiRecordApi,
    httpApi, httpCaseApi, httpSuiteApi, httpExecApi, httpRecordApi, httpCronApi, httpPlanApi,
    scheduleApi,
    perfSceneApi, perfExecApi, perfRecordApi, perfCronApi, perfWorkerApi,
    aiConfigApi, aiPromptApi, aiGenerateApi, aiRecordApi
} from './modules'

// 统一导出
export {
    userApi, roleApi, inviteCodeApi, projectApi, envApi, deviceApi, moduleApi, catalogApi, dashboardApi, operationLogApi, notificationApi,
    uiCaseApi, uiSuiteApi, uiTaskApi, uiExecApi, uiRecordApi,
    httpApi, httpCaseApi, httpSuiteApi, httpExecApi, httpRecordApi, httpCronApi, httpPlanApi,
    scheduleApi,
    perfSceneApi, perfExecApi, perfRecordApi, perfCronApi, perfWorkerApi,
    aiConfigApi, aiPromptApi, aiGenerateApi, aiRecordApi
}

// 兼容旧版导出格式
export default {
    // 系统管理
    userApi,
    roleApi,
    inviteCodeApi,
    projectApi,
    envApi,
    environmentApi: envApi,
    moduleApi,
    catalogApi,
    deviceApi,
    dashboardApi,
    operationLogApi,
    notificationApi,
    
    // Web自动化 (兼容旧命名)
    caseApi: uiCaseApi,
    suiteApi: uiSuiteApi,
    taskApi: uiTaskApi,
    runnerApi: uiExecApi,
    uiExecApi,
    resultApi: uiRecordApi,
    
    // API自动化 - 合并为一个对象兼容旧调用
    apiModuleApi: {
        // 接口定义
        getApiList: httpApi.getList,
        createApi: httpApi.create,
        updateApi: httpApi.update,
        deleteApi: httpApi.delete,
        batchDeleteApis: httpApi.batchDelete,
        debugApi: httpApi.debug,
        debugWs: httpApi.debugWs,
        importCurl: httpApi.importCurl,
        parseCurl: httpApi.parseCurl,  // 解析 curl
        uploadBodyFile: httpApi.uploadBodyFile,
        getApiDetail: httpApi.getDetail,
        syncCheck: httpApi.syncCheck,
        // 测试目录（原接口分类，已统一到 catalogApi）
        getCategories(project_id) {
            return catalogApi.getList({ project_id, tree: true })
        },
        getApiCategoryList(params) {
            return catalogApi.getList({ ...params, tree: true })
        },
        createCategory: catalogApi.create,
        createApiCategory: catalogApi.create,
        updateCategory: catalogApi.update,
        updateApiCategory: catalogApi.update,
        deleteCategory(catalog_id, params = {}) {
            return catalogApi.delete(catalog_id, params)
        },
        deleteApiCategory(catalog_id, params = {}) {
            return catalogApi.delete(catalog_id, params)
        },
        // 用例
        getApiCaseList: httpCaseApi.getList,
        getTestCaseList: httpCaseApi.getList,  // 兼容命名
        getApiCaseDetail: httpCaseApi.getDetail,
        getTestCaseDetail: httpCaseApi.getDetail,  // 兼容命名
        createApiCase: httpCaseApi.create,
        createTestCase: httpCaseApi.create,  // 兼容命名
        updateApiCase: httpCaseApi.update,
        updateTestCase: httpCaseApi.update,  // 兼容命名
        deleteApiCase: httpCaseApi.delete,
        deleteTestCase: httpCaseApi.delete,  // 兼容命名
        batchDeleteApiCases: httpCaseApi.batchDelete,
        batchDeleteTestCases: httpCaseApi.batchDelete,
        copyApiCase: httpCaseApi.copy,
        copy: httpCaseApi.copy,
        runTestCase: httpExecApi.runCase,  // 兼容命名
        // 用例目录（已统一到 catalogApi）
        getApiCaseCategoryList(params) {
            return catalogApi.getList({ ...params, tree: true })
        },
        getTestCaseCategories(project_id) {
            return catalogApi.getList({ project_id, tree: true })
        },
        createApiCaseCategory: catalogApi.create,
        createTestCaseCategory: catalogApi.create,
        updateApiCaseCategory: catalogApi.update,
        updateTestCaseCategory: catalogApi.update,
        deleteApiCaseCategory: catalogApi.delete,
        deleteTestCaseCategory: catalogApi.delete,
        // 文件导入
        importSwagger: httpApi.importSwagger,
        importPostman: httpApi.importPostman,
        // 套件
        getApiSuiteList: httpSuiteApi.getList,
        getSuiteList: httpSuiteApi.getList,  // 兼容命名
        createApiSuite: httpSuiteApi.create,
        createSuite: httpSuiteApi.create,  // 兼容命名
        updateApiSuite: httpSuiteApi.update,
        updateSuite: httpSuiteApi.update,  // 兼容命名
        deleteApiSuite: httpSuiteApi.delete,
        deleteSuite: httpSuiteApi.delete,  // 兼容命名
        batchDeleteApiSuites: httpSuiteApi.batchDelete,
        batchDeleteSuites: httpSuiteApi.batchDelete,
        getApiSuiteCases: httpSuiteApi.getCases,
        updateApiSuiteCases: httpSuiteApi.updateCases,
        getSuiteDetail: httpSuiteApi.getDetail,  // 兼容命名
        runSuite: httpExecApi.runSuite,  // 兼容命名
        runSuiteAsync: httpExecApi.runSuiteAsync,  // 异步执行套件
        // 执行
        runApi: httpExecApi.runCase,
        runApiSuite: httpExecApi.runSuite,
        runApiBatch: httpExecApi.runBatch,
        runBatch: httpExecApi.runBatch,
        // 记录
        getApiRunRecords: httpRecordApi.getCaseRecords,
        getApiSuiteRunRecords: httpRecordApi.getSuiteRecords,
        getRunRecords: httpRecordApi.getAllRecords,  // 兼容命名（合并查询）
        getAllRecords: httpRecordApi.getAllRecords,  // 统一查询（套件+计划）
        getRunRecordDetail: httpRecordApi.getSuiteRecordDetail,  // 兼容命名
        getCaseRecordDetail: httpRecordApi.getCaseRecordDetail,
        getSuiteRecordDetail: httpRecordApi.getSuiteRecordDetail,
        getPlanRecordById: httpPlanApi.getPlanRecordById,
        exportApiSuiteReport: httpRecordApi.exportSuiteReport,
        exportPlanReport: httpPlanApi.exportPlanReport,
        sendSuiteReport: httpRecordApi.sendSuiteReport,
        sendPlanReport: httpPlanApi.sendPlanReport,
        batchDeleteSuiteRecords: httpRecordApi.batchDeleteSuiteRecords,
        batchDeletePlanRecords: httpRecordApi.batchDeletePlanRecords,
        // 定时任务
        getApiCronList: httpCronApi.getList,
        getCronJobList: httpCronApi.getList,  // 兼容命名
        createApiCron: httpCronApi.create,
        createCronJob: httpCronApi.create,  // 兼容命名
        updateApiCron: httpCronApi.update,
        updateCronJob: httpCronApi.update,  // 兼容命名
        deleteApiCron: httpCronApi.delete,
        deleteCronJob: httpCronApi.delete,  // 兼容命名
        batchDeleteApiCrons: httpCronApi.batchDelete,
        batchDeleteCronJobs: httpCronApi.batchDelete,
        switchApiCron: httpCronApi.toggle,
        toggleCronJob: httpCronApi.toggle  // 兼容命名
    },
    
    // 定时任务 (Web自动化)
    scheduleApi
}
