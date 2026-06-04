"""Unified TestCatalog migration: module + api_category + api_test_case_category -> test_catalog"""
from tortoise import BaseDBAsyncClient

API_CATEGORY_OFFSET = 1_000_000
API_CASE_CATEGORY_OFFSET = 2_000_000

RUN_IN_TRANSACTION = False

_NOOP_SQL = "SELECT 1;"


async def _is_fully_migrated(db: BaseDBAsyncClient) -> bool:
    if not await _table_exists(db, "test_catalog"):
        return False
    if await _table_exists(db, "module"):
        return False
    if await _table_exists(db, "api_category"):
        return False
    if await _table_exists(db, "api_test_case_category"):
        return False
    if not await _column_exists(db, "case", "catalog_id"):
        return False
    return True


async def _table_exists(db: BaseDBAsyncClient, table: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        [table],
    )
    return bool(rows and rows[0]["cnt"])


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    if await _is_fully_migrated(db):
        return _NOOP_SQL

    await db.execute_script("""
        CREATE TABLE IF NOT EXISTS `test_catalog` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT '目录id',
            `name` VARCHAR(255) NOT NULL COMMENT '目录名称',
            `sort` INT NOT NULL DEFAULT 0 COMMENT '排序',
            `description` LONGTEXT NULL COMMENT '目录描述',
            `username` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '创建人',
            `is_del` BOOL NOT NULL DEFAULT 0 COMMENT '是否删除',
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `parent_id` INT NULL COMMENT '父目录',
            `project_id` INT NOT NULL COMMENT '所属项目',
            CONSTRAINT `fk_test_catalog_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_test_catalog_parent` FOREIGN KEY (`parent_id`) REFERENCES `test_catalog` (`id`) ON DELETE SET NULL
        ) CHARACTER SET utf8mb4 COMMENT='统一测试目录';
    """)

    for table in ("case", "suite", "task", "api_definition", "api_test_case", "api_test_suite", "api_test_plan"):
        if not await _column_exists(db, table, "catalog_id"):
            await db.execute_script(f"ALTER TABLE `{table}` ADD COLUMN `catalog_id` INT NULL COMMENT '所属目录';")

    if await _table_exists(db, "module"):
        _, modules = await db.execute_query(
            "SELECT id, name, project_id, username, is_del, create_time, update_time FROM `module`"
        )
        for row in modules or []:
            await db.execute_query(
                "INSERT INTO `test_catalog` (id, name, project_id, parent_id, sort, description, username, is_del, create_time, update_time) "
                "VALUES (%s, %s, %s, NULL, 0, NULL, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE name=VALUES(name)",
                [
                    row["id"], row["name"], row["project_id"], row["username"] or "",
                    row["is_del"], row["create_time"], row["update_time"],
                ],
            )
        if await _column_exists(db, "suite", "modules_id"):
            await db.execute_script(
                "UPDATE `suite` SET `catalog_id` = `modules_id` WHERE `modules_id` IS NOT NULL"
            )
        if await _column_exists(db, "api_test_suite", "module_id"):
            await db.execute_script(
                "UPDATE `api_test_suite` SET `catalog_id` = `module_id` WHERE `module_id` IS NOT NULL"
            )

    if await _table_exists(db, "api_category"):
        _, api_cats = await db.execute_query(
            "SELECT id, name, project_id, parent_id, sort, description, is_del, create_time, update_time "
            "FROM `api_category` ORDER BY id"
        )
        for row in api_cats or []:
            new_id = row["id"] + API_CATEGORY_OFFSET
            await db.execute_query(
                "INSERT INTO `test_catalog` (id, name, project_id, parent_id, sort, description, username, is_del, create_time, update_time) "
                "VALUES (%s, %s, %s, NULL, %s, %s, '', %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE name=VALUES(name)",
                [
                    new_id, row["name"], row["project_id"], row["sort"] or 0,
                    row["description"], row["is_del"], row["create_time"], row["update_time"],
                ],
            )
        for row in api_cats or []:
            if row["parent_id"]:
                new_id = row["id"] + API_CATEGORY_OFFSET
                new_parent = row["parent_id"] + API_CATEGORY_OFFSET
                await db.execute_query(
                    "UPDATE `test_catalog` SET parent_id = %s WHERE id = %s",
                    [new_parent, new_id],
                )
        if await _column_exists(db, "api_definition", "category_id"):
            await db.execute_script(
                f"UPDATE `api_definition` SET `catalog_id` = `category_id` + {API_CATEGORY_OFFSET} "
                "WHERE `category_id` IS NOT NULL"
            )

    if await _table_exists(db, "api_test_case_category"):
        _, case_cats = await db.execute_query(
            "SELECT id, name, project_id, parent_id, sort, description, is_del, create_time, update_time "
            "FROM `api_test_case_category` ORDER BY id"
        )
        for row in case_cats or []:
            new_id = row["id"] + API_CASE_CATEGORY_OFFSET
            await db.execute_query(
                "INSERT INTO `test_catalog` (id, name, project_id, parent_id, sort, description, username, is_del, create_time, update_time) "
                "VALUES (%s, %s, %s, NULL, %s, %s, '', %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE name=VALUES(name)",
                [
                    new_id, row["name"], row["project_id"], row["sort"] or 0,
                    row["description"], row["is_del"], row["create_time"], row["update_time"],
                ],
            )
        for row in case_cats or []:
            if row["parent_id"]:
                new_id = row["id"] + API_CASE_CATEGORY_OFFSET
                new_parent = row["parent_id"] + API_CASE_CATEGORY_OFFSET
                await db.execute_query(
                    "UPDATE `test_catalog` SET parent_id = %s WHERE id = %s",
                    [new_parent, new_id],
                )
        if await _column_exists(db, "api_test_case", "category_id"):
            await db.execute_script(
                f"UPDATE `api_test_case` SET `catalog_id` = `category_id` + {API_CASE_CATEGORY_OFFSET} "
                "WHERE `category_id` IS NOT NULL"
            )

    # Drop old FK constraints and columns
    drop_ops = []
    if await _column_exists(db, "suite", "modules_id"):
        drop_ops.append("ALTER TABLE `suite` DROP FOREIGN KEY `fk_suite_module_06720dd6`")
        drop_ops.append("ALTER TABLE `suite` DROP COLUMN `modules_id`")
    if await _column_exists(db, "api_test_suite", "module_id"):
        drop_ops.append("ALTER TABLE `api_test_suite` DROP FOREIGN KEY `fk_api_test_module_227333b6`")
        drop_ops.append("ALTER TABLE `api_test_suite` DROP COLUMN `module_id`")
    if await _column_exists(db, "api_definition", "category_id"):
        drop_ops.append("ALTER TABLE `api_definition` DROP FOREIGN KEY `fk_api_defi_api_cate_65dde99a`")
        drop_ops.append("ALTER TABLE `api_definition` DROP COLUMN `category_id`")
    if await _column_exists(db, "api_test_case", "category_id"):
        drop_ops.append("ALTER TABLE `api_test_case` DROP FOREIGN KEY `fk_api_test_api_test_fff1a6fd`")
        drop_ops.append("ALTER TABLE `api_test_case` DROP COLUMN `category_id`")

    for sql in drop_ops:
        try:
            await db.execute_script(sql)
        except Exception:
            pass

    # Add catalog FK constraints
    fk_defs = [
        ("case", "fk_case_test_catalog", "catalog_id"),
        ("suite", "fk_suite_test_catalog", "catalog_id"),
        ("task", "fk_task_test_catalog", "catalog_id"),
        ("api_definition", "fk_api_def_test_catalog", "catalog_id"),
        ("api_test_case", "fk_api_case_test_catalog", "catalog_id"),
        ("api_test_suite", "fk_api_suite_test_catalog", "catalog_id"),
        ("api_test_plan", "fk_api_plan_test_catalog", "catalog_id"),
    ]
    for table, fk_name, col in fk_defs:
        if await _column_exists(db, table, col):
            try:
                await db.execute_script(
                    f"ALTER TABLE `{table}` ADD CONSTRAINT `{fk_name}` "
                    f"FOREIGN KEY (`{col}`) REFERENCES `test_catalog` (`id`) ON DELETE SET NULL"
                )
            except Exception:
                pass

    if await _table_exists(db, "api_category"):
        await db.execute_script("DROP TABLE IF EXISTS `api_category`")
    if await _table_exists(db, "api_test_case_category"):
        await db.execute_script("DROP TABLE IF EXISTS `api_test_case_category`")
    if await _table_exists(db, "module"):
        await db.execute_script("DROP TABLE IF EXISTS `module`")

    return _NOOP_SQL


async def downgrade(db: BaseDBAsyncClient) -> str:
    return _NOOP_SQL
