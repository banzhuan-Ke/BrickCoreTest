from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- #20: 软删唯一键改用 delete_seq，避免 (..., is_del=1) 二次软删冲突
        ALTER TABLE `test_release`
            ADD COLUMN `delete_seq` INT NOT NULL DEFAULT 0 COMMENT '软删序号，活跃为0' AFTER `is_del`;
        UPDATE `test_release` SET `delete_seq` = `id` WHERE `is_del` = 1;
        ALTER TABLE `test_release`
            DROP INDEX `uniq_test_release_proj_key_del`,
            ADD UNIQUE KEY `uniq_test_release_proj_key_seq` (`project_id`, `release_key`, `delete_seq`);

        ALTER TABLE `test_release_scope`
            ADD COLUMN `delete_seq` INT NOT NULL DEFAULT 0 COMMENT '软删序号，活跃为0' AFTER `is_del`;
        UPDATE `test_release_scope` SET `delete_seq` = `id` WHERE `is_del` = 1;
        ALTER TABLE `test_release_scope`
            DROP INDEX `uniq_test_scope_release_case_del`,
            ADD UNIQUE KEY `uniq_test_scope_release_case_seq` (`release_id`, `functional_case_id`, `delete_seq`);

        ALTER TABLE `test_asset_link`
            ADD COLUMN `delete_seq` INT NOT NULL DEFAULT 0 COMMENT '软删序号，活跃为0' AFTER `is_del`;
        UPDATE `test_asset_link` SET `delete_seq` = `id` WHERE `is_del` = 1;
        ALTER TABLE `test_asset_link`
            DROP INDEX `uniq_test_asset_link_case_asset_del`,
            ADD UNIQUE KEY `uniq_test_asset_link_case_asset_seq` (`functional_case_id`, `asset_type`, `asset_id`, `delete_seq`);

        ALTER TABLE `case_review_item`
            ADD COLUMN `delete_seq` INT NOT NULL DEFAULT 0 COMMENT '软删序号，活跃为0' AFTER `is_del`;
        UPDATE `case_review_item` SET `delete_seq` = `id` WHERE `is_del` = 1;
        ALTER TABLE `case_review_item`
            DROP INDEX `uniq_case_review_item`,
            ADD UNIQUE KEY `uniq_case_review_item_seq` (`review_id`, `functional_case_id`, `delete_seq`);

        ALTER TABLE `test_defect`
            ADD COLUMN `delete_seq` INT NOT NULL DEFAULT 0 COMMENT '软删序号，活跃为0' AFTER `is_del`;
        UPDATE `test_defect` SET `delete_seq` = `id` WHERE `is_del` = 1;
        ALTER TABLE `test_defect`
            DROP INDEX `uniq_test_defect_key`,
            ADD UNIQUE KEY `uniq_test_defect_key_seq` (`project_id`, `defect_key`, `delete_seq`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_defect`
            DROP INDEX `uniq_test_defect_key_seq`,
            ADD UNIQUE KEY `uniq_test_defect_key` (`project_id`, `defect_key`, `is_del`),
            DROP COLUMN `delete_seq`;

        ALTER TABLE `case_review_item`
            DROP INDEX `uniq_case_review_item_seq`,
            ADD UNIQUE KEY `uniq_case_review_item` (`review_id`, `functional_case_id`, `is_del`),
            DROP COLUMN `delete_seq`;

        ALTER TABLE `test_asset_link`
            DROP INDEX `uniq_test_asset_link_case_asset_seq`,
            ADD UNIQUE KEY `uniq_test_asset_link_case_asset_del` (`functional_case_id`, `asset_type`, `asset_id`, `is_del`),
            DROP COLUMN `delete_seq`;

        ALTER TABLE `test_release_scope`
            DROP INDEX `uniq_test_scope_release_case_seq`,
            ADD UNIQUE KEY `uniq_test_scope_release_case_del` (`release_id`, `functional_case_id`, `is_del`),
            DROP COLUMN `delete_seq`;

        ALTER TABLE `test_release`
            DROP INDEX `uniq_test_release_proj_key_seq`,
            ADD UNIQUE KEY `uniq_test_release_proj_key_del` (`project_id`, `release_key`, `is_del`),
            DROP COLUMN `delete_seq`;
    """
