# 修正已导入数据的显示名称（乱码或旧中文名 -> BrickCore）
# 用法: docker exec -i fastapi_mysql mysql --default-character-set=utf8mb4 -uadmin -pBrickCore123456 fastapi < database-demo-fix-labels.sql
UPDATE `user` SET `nickname` = 'BrickCore' WHERE `id` = 1;
UPDATE `project` SET `name` = 'BrickCore' WHERE `id` IN (1, 2);
UPDATE `environment` SET `name` = 'BrickCore' WHERE `id` IN (1, 2);
UPDATE `test_catalog` SET `name` = 'BrickCore' WHERE `id` IN (1, 2);
UPDATE `case` SET `name` = 'BrickCore' WHERE `id` IN (1, 2);
UPDATE `suite` SET `name` = 'BrickCore' WHERE `id` IN (1, 2);
UPDATE `task` SET `name` = 'BrickCore' WHERE `id` IN (1, 2);
