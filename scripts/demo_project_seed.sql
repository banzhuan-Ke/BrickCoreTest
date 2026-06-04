-- BrickCore 演示项目种子数据（可选导入）
-- 用法: mysql -u root -p <database_name> < scripts/demo_project_seed.sql
-- 说明: 在已有 database.sql 初始化基础上追加演示说明性配置

-- 演示环境全局变量（project_id=1 为默认示例项目时需根据实际调整）
-- 若环境 id=1 存在则更新 global_vars 中的演示标记
UPDATE `environment`
SET `global_vars` = JSON_SET(
    COALESCE(`global_vars`, JSON_OBJECT()),
    '$.demo_mode', 'true',
    '$.demo_base_url', 'https://www.baidu.com',
    '$.demo_note', 'BrickCore 演示环境 - 可用于 UI 录制与 API 调试'
)
WHERE `id` = 1 AND `is_del` = 0;

-- 插入演示说明（操作日志外的轻量标记，不影响业务）
-- 管理员可在「环境配置」中查看 demo_mode 变量确认导入成功

SELECT '演示种子执行完成。请登录平台，选择示例项目，按 docs-site/demo/index.md 演示路径操作。' AS message;
