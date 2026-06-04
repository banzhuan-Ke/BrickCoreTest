-- CE 演示机：清除内置文档在 platform_doc 中的正文/标题覆盖（保留隐藏、排序）
-- 原因：曾在文档中心编辑保存会把 Pro 版 Markdown 写入 DB，覆盖 docs-site 文件。
-- 用法（在服务器）：
--   docker exec -i fastapi_mysql mysql -uadmin -p"$MYSQL_PASSWORD" fastapi < scripts/ce-stubs/clear-builtin-doc-overrides.sql

UPDATE platform_doc
SET content = NULL,
    title = CASE builtin_id
        WHEN 'runner-packaging' THEN '执行器获取与发布'
        ELSE title
    END,
    update_time = NOW()
WHERE builtin_id IS NOT NULL
  AND is_del = 0
  AND (content IS NOT NULL OR (builtin_id = 'runner-packaging' AND title = '执行器打包说明'));
