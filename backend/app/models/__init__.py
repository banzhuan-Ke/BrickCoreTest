"""
数据模型模块
"""
from .sys import User, Role, Project, Environment, Device, TestCatalog
from .ui import Case, Suite, Step, Task, UiPlanExecution, UiSuiteExecution, UiCaseExecution
from .http import (
    ApiDefinition, ApiTestCase,
    ApiRunRecord, MockApi, ApiTestSuite, ApiSuiteCase, ApiSuiteRunRecord, ApiCronJob,
    ApiTestPlan, ApiPlanItem, ApiPlanRunRecord, ApiAuthConfig,
    EnvDatasource, SqlTemplate,
)
from .schedule import Cronjob
from .perf import PerfScene, PerfRecord

__all__ = [
    # Sys
    'User', 'Role', 'Project', 'Environment', 'Device', 'TestCatalog',
    # UI
    'Case', 'Suite', 'Step', 'Task', 'UiPlanExecution', 'UiSuiteExecution', 'UiCaseExecution',
    # HTTP
    'ApiDefinition', 'ApiTestCase',
    'ApiRunRecord', 'MockApi', 'ApiTestSuite', 'ApiSuiteCase', 'ApiSuiteRunRecord', 'ApiCronJob',
    'ApiTestPlan', 'ApiPlanItem', 'ApiPlanRunRecord', 'ApiAuthConfig',
    'EnvDatasource', 'SqlTemplate',
    # Schedule
    'Cronjob',
    # Perf
    'PerfScene', 'PerfRecord',
]
