"""AI-REQ：工作区用例审核字段；旧 draft 回填为 needs_review。"""
from tortoise import BaseDBAsyncClient


async def _column_exists(db: BaseDBAsyncClient, table: str, column: str) -> bool:
    _, rows = await db.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        [table, column],
    )
    return bool(rows and rows[0]["cnt"])


async def upgrade(db: BaseDBAsyncClient) -> str:
    # aerich 会把本函数返回值再 execute_script 一次，必须是合法 SQL（见 163/164）
    if not await _column_exists(db, "ai_requirement_case", "review_note"):
        await db.execute_script(
            "ALTER TABLE `ai_requirement_case` "
            "ADD COLUMN `review_note` VARCHAR(500) NULL COMMENT '审核备注' AFTER `status`;"
        )
    if not await _column_exists(db, "ai_requirement_case", "reviewed_by"):
        await db.execute_script(
            "ALTER TABLE `ai_requirement_case` "
            "ADD COLUMN `reviewed_by` VARCHAR(50) NULL COMMENT '审核人' AFTER `review_note`;"
        )
    if not await _column_exists(db, "ai_requirement_case", "reviewed_at"):
        await db.execute_script(
            "ALTER TABLE `ai_requirement_case` "
            "ADD COLUMN `reviewed_at` DATETIME(6) NULL COMMENT '审核时间' AFTER `reviewed_by`;"
        )
    await db.execute_script(
        "UPDATE `ai_requirement_case` "
        "SET `status` = 'needs_review' "
        "WHERE `is_del` = 0 AND `status` = 'draft';"
    )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    await db.execute_script(
        "UPDATE `ai_requirement_case` "
        "SET `status` = 'draft' "
        "WHERE `is_del` = 0 AND `status` = 'needs_review';"
    )
    if await _column_exists(db, "ai_requirement_case", "reviewed_at"):
        await db.execute_script("ALTER TABLE `ai_requirement_case` DROP COLUMN `reviewed_at`;")
    if await _column_exists(db, "ai_requirement_case", "reviewed_by"):
        await db.execute_script("ALTER TABLE `ai_requirement_case` DROP COLUMN `reviewed_by`;")
    if await _column_exists(db, "ai_requirement_case", "review_note"):
        await db.execute_script("ALTER TABLE `ai_requirement_case` DROP COLUMN `review_note`;")
    return "SELECT 1;"
