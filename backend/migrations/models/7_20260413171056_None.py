from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `aerich` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `version` VARCHAR(255) NOT NULL,
    `app` VARCHAR(100) NOT NULL,
    `content` JSON NOT NULL
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `device` (
    `id` VARCHAR(50) NOT NULL PRIMARY KEY COMMENT '设备id',
    `ip` VARCHAR(50) NOT NULL COMMENT '设备ip',
    `name` VARCHAR(50) NOT NULL COMMENT '设备名称',
    `system` VARCHAR(50) NOT NULL COMMENT '操作系统',
    `status` VARCHAR(20) NOT NULL COMMENT '设备状态' DEFAULT '离线',
    `username` VARCHAR(50) NOT NULL COMMENT '创建人',
    `version` VARCHAR(50) NOT NULL COMMENT '设备版本' DEFAULT '',
    `hostname` VARCHAR(50) NOT NULL COMMENT '设备主机名' DEFAULT '',
    `create_time` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0
) CHARACTER SET utf8mb4 COMMENT='设备表';
CREATE TABLE IF NOT EXISTS `role` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '角色ID',
    `name` VARCHAR(50) NOT NULL COMMENT '角色名称',
    `description` VARCHAR(255) NOT NULL COMMENT '角色描述' DEFAULT '',
    `create_time` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0
) CHARACTER SET utf8mb4 COMMENT='角色列表';
CREATE TABLE IF NOT EXISTS `user` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '用户id',
    `username` VARCHAR(50) NOT NULL COMMENT '用户名',
    `password` VARCHAR(255) NOT NULL COMMENT '密码',
    `nickname` VARCHAR(50) NOT NULL COMMENT '用户昵称',
    `email` VARCHAR(50) NOT NULL COMMENT '邮箱' DEFAULT '',
    `mobile` VARCHAR(11) NOT NULL COMMENT '手机号' DEFAULT '',
    `is_active` BOOL NOT NULL COMMENT '是否激活' DEFAULT 1,
    `is_superuser` BOOL NOT NULL COMMENT '是否超级管理员' DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0
) CHARACTER SET utf8mb4 COMMENT='用户列表';
CREATE TABLE IF NOT EXISTS `project` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '项目id',
    `name` VARCHAR(255) NOT NULL COMMENT '项目名称',
    `create_time` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `username` VARCHAR(50) NOT NULL COMMENT '创建人',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `user_id` INT NOT NULL COMMENT '项目创建人',
    CONSTRAINT `fk_project_user_7cc4fc0f` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='测试项目';
CREATE TABLE IF NOT EXISTS `environment` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '环境id',
    `name` VARCHAR(255) NOT NULL COMMENT '环境名称',
    `create_time` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `host` VARCHAR(255) NOT NULL COMMENT '环境地址',
    `global_vars` JSON NOT NULL COMMENT '全局变量',
    `username` VARCHAR(50) NOT NULL COMMENT '创建人',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_environm_project_a60593de` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='测试环境';
CREATE TABLE IF NOT EXISTS `module` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '模块id',
    `name` VARCHAR(255) NOT NULL COMMENT '模块名称',
    `create_time` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `username` VARCHAR(50) NOT NULL COMMENT '创建人',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `suite_type` VARCHAR(10) NOT NULL COMMENT '模块适用类型' DEFAULT 'web',
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_module_project_f522b57c` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='项目模块';
CREATE TABLE IF NOT EXISTS `case` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '用例id',
    `name` VARCHAR(50) NOT NULL COMMENT '用例名称',
    `create_time` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `steps` JSON NOT NULL COMMENT '用例执行步骤',
    `level` VARCHAR(50) NOT NULL COMMENT '用例等级' DEFAULT '1',
    `username` VARCHAR(50) NOT NULL COMMENT '创建人',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_case_project_4ad4e479` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='测试用例';
CREATE TABLE IF NOT EXISTS `suite` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '套件id',
    `name` VARCHAR(50) NOT NULL COMMENT '套件名称',
    `create_time` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `pre_actions` JSON NOT NULL COMMENT '前置执行步骤',
    `suite_type` VARCHAR(50) NOT NULL COMMENT '套件类型' DEFAULT '1',
    `username` VARCHAR(50) NOT NULL COMMENT '创建人',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `modules_id` INT COMMENT '所属模块',
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_suite_module_06720dd6` FOREIGN KEY (`modules_id`) REFERENCES `module` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_suite_project_a661d395` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='测试套件';
CREATE TABLE IF NOT EXISTS `step` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '用例id',
    `sort` INT NOT NULL COMMENT '用例执行顺序' DEFAULT 0,
    `skip` BOOL NOT NULL COMMENT '是否跳过' DEFAULT 0,
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `cases_id` INT NOT NULL COMMENT '所属用例',
    `suite_id` INT NOT NULL COMMENT '所属套件',
    CONSTRAINT `fk_step_case_7024e2f7` FOREIGN KEY (`cases_id`) REFERENCES `case` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_step_suite_92de0ee4` FOREIGN KEY (`suite_id`) REFERENCES `suite` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='套件中的用例';
CREATE TABLE IF NOT EXISTS `task` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '任务id',
    `name` VARCHAR(255) NOT NULL COMMENT '任务名称',
    `create_time` DATETIME(6) NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `username` VARCHAR(50) NOT NULL COMMENT '创建人',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_task_project_9f778443` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='测试计划';
CREATE TABLE IF NOT EXISTS `ui_plan_execution` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '计划执行id',
    `cronjob_id` VARCHAR(100) COMMENT '关联的定时任务ID',
    `env` JSON NOT NULL COMMENT '执行环境',
    `start_time` DATETIME(6) NOT NULL COMMENT '开始执行时间' DEFAULT CURRENT_TIMESTAMP(6),
    `duration` DOUBLE NOT NULL COMMENT '执行时间' DEFAULT 0,
    `status` VARCHAR(255) NOT NULL COMMENT '运行状态' DEFAULT '执行中',
    `case_count` INT NOT NULL COMMENT '总用例数' DEFAULT 0,
    `run_all` INT NOT NULL COMMENT '执行用例数' DEFAULT 0,
    `no_run` INT NOT NULL COMMENT '未执行用例数' DEFAULT 0,
    `success` INT NOT NULL COMMENT '成功用例数' DEFAULT 0,
    `pass_rate` DOUBLE NOT NULL COMMENT '通过率' DEFAULT 0,
    `execution_log` JSON COMMENT '任务执行日志',
    `fail` INT NOT NULL COMMENT '失败用例数' DEFAULT 0,
    `error` INT NOT NULL COMMENT '错误用例数' DEFAULT 0,
    `skip` INT NOT NULL COMMENT '跳过用例数' DEFAULT 0,
    `username` VARCHAR(50) NOT NULL COMMENT '创建人',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `project_id` INT NOT NULL COMMENT '所属项目',
    `task_id` INT NOT NULL COMMENT '执行的任务',
    CONSTRAINT `fk_ui_plan__project_8126ab79` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ui_plan__task_9cdb91ca` FOREIGN KEY (`task_id`) REFERENCES `task` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='测试计划运行记录';
CREATE TABLE IF NOT EXISTS `ui_suite_execution` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '执行记录id',
    `status` VARCHAR(255) NOT NULL COMMENT '运行状态' DEFAULT '执行中',
    `case_count` INT NOT NULL COMMENT '总用例数' DEFAULT 0,
    `run_all` INT NOT NULL COMMENT '执行用例数' DEFAULT 0,
    `no_run` INT NOT NULL COMMENT '未执行用例数' DEFAULT 0,
    `success` INT NOT NULL COMMENT '成功用例数' DEFAULT 0,
    `fail` INT NOT NULL COMMENT '失败用例数' DEFAULT 0,
    `error` INT NOT NULL COMMENT '错误用例数' DEFAULT 0,
    `skip` INT NOT NULL COMMENT '跳过用例数' DEFAULT 0,
    `start_time` DATETIME(6) NOT NULL COMMENT '开始执行时间' DEFAULT CURRENT_TIMESTAMP(6),
    `duration` DOUBLE NOT NULL COMMENT '执行时间' DEFAULT 0,
    `execution_log` JSON NOT NULL COMMENT '套件执行日志',
    `pass_rate` DOUBLE NOT NULL COMMENT '通过率' DEFAULT 0,
    `env` JSON COMMENT '执行环境',
    `username` VARCHAR(50) NOT NULL COMMENT '创建人',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `plan_execution_id` INT COMMENT '关联的运行计划记录',
    `suite_id` INT NOT NULL COMMENT '执行的套件',
    CONSTRAINT `fk_ui_suite_ui_plan__2be50665` FOREIGN KEY (`plan_execution_id`) REFERENCES `ui_plan_execution` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ui_suite_suite_11a39ca4` FOREIGN KEY (`suite_id`) REFERENCES `suite` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='测试套件运行记录';
CREATE TABLE IF NOT EXISTS `ui_case_execution` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '用例执行id',
    `status` VARCHAR(255) NOT NULL COMMENT '运行状态' DEFAULT 'running',
    `result_data` JSON NOT NULL COMMENT '用例执行详情',
    `start_time` DATETIME(6) NOT NULL COMMENT '开始执行时间' DEFAULT CURRENT_TIMESTAMP(6),
    `env` JSON NOT NULL COMMENT '执行环境',
    `username` VARCHAR(50) NOT NULL COMMENT '创建人',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `case_id` INT NOT NULL COMMENT '执行的用例',
    `suite_execution_id` INT COMMENT '关联的运行套件记录',
    CONSTRAINT `fk_ui_case__case_833213c9` FOREIGN KEY (`case_id`) REFERENCES `case` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ui_case__ui_suite_5f3c96ba` FOREIGN KEY (`suite_execution_id`) REFERENCES `ui_suite_execution` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='测试用例运行记录';
CREATE TABLE IF NOT EXISTS `api_category` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '分类ID',
    `name` VARCHAR(50) NOT NULL COMMENT '分类名称',
    `sort` INT NOT NULL COMMENT '排序' DEFAULT 0,
    `description` LONGTEXT COMMENT '分类描述',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `parent_id` INT COMMENT '父分类',
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_api_cate_api_cate_abe98b62` FOREIGN KEY (`parent_id`) REFERENCES `api_category` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_api_cate_project_b07a315c` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='接口分类';
CREATE TABLE IF NOT EXISTS `api_definition` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '接口ID',
    `name` VARCHAR(100) NOT NULL COMMENT '接口名称',
    `method` VARCHAR(10) NOT NULL COMMENT '请求方法',
    `path` VARCHAR(500) NOT NULL COMMENT '接口路径',
    `description` LONGTEXT COMMENT '接口描述',
    `base_url` VARCHAR(500) COMMENT '基础URL',
    `headers` JSON NOT NULL COMMENT '请求头',
    `params` JSON NOT NULL COMMENT '查询参数列表',
    `body` JSON NOT NULL COMMENT '请求体',
    `body_type` VARCHAR(20) NOT NULL COMMENT '请求体类型' DEFAULT 'json',
    `version` INT NOT NULL COMMENT '版本号' DEFAULT 1,
    `version_history` JSON NOT NULL COMMENT '版本历史',
    `source` VARCHAR(50) COMMENT '来源',
    `source_id` VARCHAR(200) COMMENT '来源ID',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
    `category_id` INT COMMENT '所属分类',
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_api_defi_api_cate_65dde99a` FOREIGN KEY (`category_id`) REFERENCES `api_category` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_api_defi_project_9160b5a0` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='接口定义';
CREATE TABLE IF NOT EXISTS `api_test_case_category` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '分类ID',
    `name` VARCHAR(50) NOT NULL COMMENT '分类名称',
    `sort` INT NOT NULL COMMENT '排序' DEFAULT 0,
    `description` LONGTEXT COMMENT '分类描述',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `parent_id` INT COMMENT '父分类',
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_api_test_api_test_970540fd` FOREIGN KEY (`parent_id`) REFERENCES `api_test_case_category` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_api_test_project_206a27a1` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='测试用例分类';
CREATE TABLE IF NOT EXISTS `api_test_case` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '用例ID',
    `name` VARCHAR(100) NOT NULL COMMENT '用例名称',
    `request_headers` JSON NOT NULL COMMENT '请求头覆盖',
    `request_params` JSON NOT NULL COMMENT '请求参数覆盖',
    `request_body` JSON NOT NULL COMMENT '请求体覆盖',
    `assertions` JSON NOT NULL COMMENT '断言规则',
    `extractors` JSON NOT NULL COMMENT '变量提取规则',
    `depends_on` JSON NOT NULL COMMENT '依赖用例ID列表',
    `timeout` INT NOT NULL COMMENT '超时时间(秒)' DEFAULT 30,
    `retry_count` INT NOT NULL COMMENT '重试次数' DEFAULT 0,
    `tags` JSON NOT NULL COMMENT '标签',
    `priority` VARCHAR(10) NOT NULL COMMENT '优先级 P0/P1/P2/P3' DEFAULT 'P2',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
    `api_id` INT NOT NULL COMMENT '关联接口',
    `category_id` INT COMMENT '所属分类',
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_api_test_api_defi_26006b0a` FOREIGN KEY (`api_id`) REFERENCES `api_definition` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_api_test_api_test_fff1a6fd` FOREIGN KEY (`category_id`) REFERENCES `api_test_case_category` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_api_test_project_f3a162a0` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='接口测试用例';
CREATE TABLE IF NOT EXISTS `api_test_suite` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '套件ID',
    `name` VARCHAR(100) NOT NULL COMMENT '套件名称',
    `env_id` INT COMMENT '默认环境ID',
    `timeout` INT NOT NULL COMMENT '总超时时间(秒)' DEFAULT 300,
    `retry_count` INT NOT NULL COMMENT '失败重试次数' DEFAULT 0,
    `stop_on_failure` BOOL NOT NULL COMMENT '失败时停止' DEFAULT 0,
    `parallel` BOOL NOT NULL COMMENT '并行执行' DEFAULT 0,
    `description` LONGTEXT COMMENT '描述',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
    `module_id` INT COMMENT '所属模块',
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_api_test_module_227333b6` FOREIGN KEY (`module_id`) REFERENCES `module` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_api_test_project_eadaab2c` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='接口测试套件';
CREATE TABLE IF NOT EXISTS `api_cron_job` (
    `id` VARCHAR(100) NOT NULL PRIMARY KEY COMMENT '任务ID',
    `name` VARCHAR(100) NOT NULL COMMENT '任务名称',
    `run_type` VARCHAR(20) NOT NULL COMMENT '类型: Interval/date/crontab',
    `interval` INT NOT NULL COMMENT '间隔(秒)' DEFAULT 3600,
    `run_date` DATETIME(6) COMMENT '固定执行时间',
    `crontab` JSON NOT NULL COMMENT 'cron表达式',
    `env_id` INT NOT NULL COMMENT '执行环境ID',
    `last_run_record_id` INT COMMENT '最后一次执行记录ID',
    `last_run_time` DATETIME(6) COMMENT '最后一次执行时间',
    `last_run_status` VARCHAR(20) COMMENT '最后一次执行状态',
    `state` BOOL NOT NULL COMMENT '是否启用' DEFAULT 0,
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `create_by` VARCHAR(50) NOT NULL COMMENT '创建人',
    `project_id` INT NOT NULL COMMENT '所属项目',
    `suite_id` INT NOT NULL COMMENT '关联套件',
    CONSTRAINT `fk_api_cron_project_bfe81431` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_api_cron_api_test_d7a13b82` FOREIGN KEY (`suite_id`) REFERENCES `api_test_suite` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='接口定时任务';
CREATE TABLE IF NOT EXISTS `api_suite_case` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT 'ID',
    `sort` INT NOT NULL COMMENT '排序' DEFAULT 0,
    `case_id` INT NOT NULL COMMENT '关联用例',
    `suite_id` INT NOT NULL COMMENT '所属套件',
    CONSTRAINT `fk_api_suit_api_test_dcb2e5aa` FOREIGN KEY (`case_id`) REFERENCES `api_test_case` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_api_suit_api_test_b903d955` FOREIGN KEY (`suite_id`) REFERENCES `api_test_suite` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='套件用例关联';
CREATE TABLE IF NOT EXISTS `api_suite_run_record` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
    `status` VARCHAR(20) NOT NULL COMMENT '状态: pending/running/success/failed' DEFAULT 'running',
    `trigger_type` VARCHAR(20) NOT NULL COMMENT '触发方式: manual/cron/api' DEFAULT 'manual',
    `total_cases` INT NOT NULL COMMENT '总用例数' DEFAULT 0,
    `success_cases` INT NOT NULL COMMENT '成功数' DEFAULT 0,
    `failed_cases` INT NOT NULL COMMENT '失败数' DEFAULT 0,
    `skipped_cases` INT NOT NULL COMMENT '跳过数' DEFAULT 0,
    `start_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `end_time` DATETIME(6),
    `duration` DOUBLE NOT NULL COMMENT '执行耗时(秒)' DEFAULT 0,
    `env_id` INT COMMENT '执行环境ID',
    `env_name` VARCHAR(100) COMMENT '环境名称',
    `report_url` VARCHAR(500) COMMENT '报告链接',
    `run_by` VARCHAR(50) NOT NULL COMMENT '执行人',
    `project_id` INT NOT NULL COMMENT '所属项目',
    `suite_id` INT NOT NULL COMMENT '关联套件',
    CONSTRAINT `fk_api_suit_project_641b9195` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_api_suit_api_test_d10c8f3c` FOREIGN KEY (`suite_id`) REFERENCES `api_test_suite` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='接口套件执行记录';
CREATE TABLE IF NOT EXISTS `api_run_record` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
    `status` VARCHAR(20) NOT NULL COMMENT '执行状态' DEFAULT 'pending',
    `request_url` VARCHAR(1000) COMMENT '请求URL',
    `request_method` VARCHAR(10) COMMENT '请求方法',
    `request_headers` JSON NOT NULL COMMENT '请求头',
    `request_body` LONGTEXT COMMENT '请求体',
    `response_status` INT COMMENT '响应状态码',
    `response_headers` JSON NOT NULL COMMENT '响应头',
    `response_body` LONGTEXT COMMENT '响应体',
    `response_time` DOUBLE NOT NULL COMMENT '响应时间(ms)' DEFAULT 0,
    `assertions_result` JSON NOT NULL COMMENT '断言结果',
    `error_msg` LONGTEXT COMMENT '错误信息',
    `extracted_vars` JSON NOT NULL COMMENT '提取的变量',
    `request_detail` JSON NOT NULL COMMENT '请求详情',
    `start_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `end_time` DATETIME(6),
    `run_by` VARCHAR(50) NOT NULL COMMENT '执行人',
    `case_id` INT NOT NULL COMMENT '关联用例',
    `project_id` INT NOT NULL COMMENT '所属项目',
    `suite_run_record_id` INT COMMENT '套件执行记录',
    CONSTRAINT `fk_api_run__api_test_1c488601` FOREIGN KEY (`case_id`) REFERENCES `api_test_case` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_api_run__project_f715d853` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_api_run__api_suit_88ff7f90` FOREIGN KEY (`suite_run_record_id`) REFERENCES `api_suite_run_record` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='接口执行记录';
CREATE TABLE IF NOT EXISTS `mock_api` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT 'Mock ID',
    `name` VARCHAR(100) NOT NULL COMMENT 'Mock名称',
    `method` VARCHAR(10) NOT NULL COMMENT '请求方法',
    `path` VARCHAR(500) NOT NULL COMMENT '匹配路径',
    `match_rules` JSON NOT NULL COMMENT '高级匹配规则',
    `response_status` INT NOT NULL COMMENT '响应状态码' DEFAULT 200,
    `response_headers` JSON NOT NULL COMMENT '响应头',
    `response_body` JSON NOT NULL COMMENT '响应体',
    `response_delay` INT NOT NULL COMMENT '延迟响应(ms)' DEFAULT 0,
    `call_count` INT NOT NULL COMMENT '调用次数' DEFAULT 0,
    `last_call_time` DATETIME(6) COMMENT '最后调用时间',
    `is_enabled` BOOL NOT NULL COMMENT '是否启用' DEFAULT 1,
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `project_id` INT NOT NULL COMMENT '所属项目',
    CONSTRAINT `fk_mock_api_project_7b11dff7` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='Mock接口';
CREATE TABLE IF NOT EXISTS `cronjob` (
    `id` VARCHAR(100) NOT NULL PRIMARY KEY COMMENT '任务id',
    `name` VARCHAR(50) NOT NULL COMMENT '任务名称',
    `create_time` DATETIME(6) NOT NULL COMMENT '创建日期' DEFAULT CURRENT_TIMESTAMP(6),
    `update_time` DATETIME(6) NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `state` BOOL NOT NULL COMMENT '是否启用' DEFAULT 1,
    `run_type` VARCHAR(10) NOT NULL COMMENT '任务类型',
    `interval` INT NOT NULL COMMENT '执行间隔时间' DEFAULT 60,
    `date` DATETIME(6) NOT NULL COMMENT '指定执行的事件' DEFAULT '2030-01-01 00:00:00',
    `crontab` JSON NOT NULL COMMENT '周期性任务规则',
    `username` VARCHAR(50) NOT NULL COMMENT '创建人',
    `is_del` BOOL NOT NULL COMMENT '是否删除' DEFAULT 0,
    `env_id` INT NOT NULL COMMENT '执行环境',
    `project_id` INT NOT NULL COMMENT '所属项目',
    `task_id` INT NOT NULL COMMENT '执行的测试计划',
    CONSTRAINT `fk_cronjob_environm_ce999160` FOREIGN KEY (`env_id`) REFERENCES `environment` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_cronjob_project_145a9738` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_cronjob_task_ecc4784f` FOREIGN KEY (`task_id`) REFERENCES `task` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='定时任务';
CREATE TABLE IF NOT EXISTS `user_role` (
    `user_id` INT NOT NULL,
    `role_id` INT NOT NULL,
    FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`role_id`) REFERENCES `role` (`id`) ON DELETE CASCADE,
    UNIQUE KEY `uidx_user_role_user_id_d0bad3` (`user_id`, `role_id`)
) CHARACTER SET utf8mb4 COMMENT='用户角色';
CREATE TABLE IF NOT EXISTS `task_suite` (
    `task_id` INT NOT NULL,
    `suite_id` INT NOT NULL,
    FOREIGN KEY (`task_id`) REFERENCES `task` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`suite_id`) REFERENCES `suite` (`id`) ON DELETE CASCADE,
    UNIQUE KEY `uidx_task_suite_task_id_c35d3b` (`task_id`, `suite_id`)
) CHARACTER SET utf8mb4 COMMENT='任务中套件';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "eJn5agNacDGFOL1b6vt/AJiMwaw="
)
