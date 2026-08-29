from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ai_requirement`
            ADD COLUMN `review_status` VARCHAR(32) NOT NULL DEFAULT 'pending'
                COMMENT '需求可测性评审: pending/in_review/approved/rejected' AFTER `parse_status`;

        UPDATE `ai_requirement` SET `review_status` = 'approved' WHERE `is_del` = 0;

        CREATE TABLE IF NOT EXISTS `requirement_review` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
            `reviewer_ids` JSON NOT NULL,
            `round` INT NOT NULL DEFAULT 1,
            `ai_assist_summary` LONGTEXT NULL,
            `summary` LONGTEXT NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `requirement_id` INT NOT NULL,
            CONSTRAINT `fk_req_review_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            KEY `idx_req_review_req` (`requirement_id`, `is_del`),
            KEY `idx_req_review_project` (`project_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-需求可测性评审';

        CREATE TABLE IF NOT EXISTS `requirement_review_item` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `section_id` VARCHAR(64) NULL,
            `category` VARCHAR(64) NOT NULL DEFAULT 'other',
            `severity` VARCHAR(32) NOT NULL DEFAULT 'medium',
            `comment` LONGTEXT NULL,
            `suggested_fix` LONGTEXT NULL,
            `is_del` BOOL NOT NULL DEFAULT 0,
            `create_by` VARCHAR(50) NOT NULL DEFAULT '',
            `update_by` VARCHAR(50) NULL,
            `create_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `update_time` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `project_id` INT NOT NULL,
            `review_id` INT NOT NULL,
            CONSTRAINT `fk_req_review_item_project` FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_req_review_item_review` FOREIGN KEY (`review_id`) REFERENCES `requirement_review` (`id`) ON DELETE CASCADE,
            KEY `idx_req_review_item_review` (`review_id`, `is_del`)
        ) CHARACTER SET utf8mb4 COMMENT='测试管理-需求评审意见';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `requirement_review_item`;
        DROP TABLE IF EXISTS `requirement_review`;
        ALTER TABLE `ai_requirement` DROP COLUMN `review_status`;
    """
