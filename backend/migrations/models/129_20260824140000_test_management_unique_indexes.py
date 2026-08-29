from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_release`
            DROP INDEX `idx_test_release_key`,
            ADD UNIQUE KEY `uniq_test_release_proj_key_del` (`project_id`, `release_key`, `is_del`);

        ALTER TABLE `test_release_scope`
            DROP INDEX `idx_test_scope_case`,
            ADD UNIQUE KEY `uniq_test_scope_release_case_del` (`release_id`, `functional_case_id`, `is_del`);

        ALTER TABLE `test_asset_link`
            DROP INDEX `idx_test_asset_link_uniq`,
            ADD UNIQUE KEY `uniq_test_asset_link_case_asset_del` (`functional_case_id`, `asset_type`, `asset_id`, `is_del`);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `test_asset_link`
            DROP INDEX `uniq_test_asset_link_case_asset_del`,
            ADD KEY `idx_test_asset_link_uniq` (`functional_case_id`, `asset_type`, `asset_id`, `is_del`);

        ALTER TABLE `test_release_scope`
            DROP INDEX `uniq_test_scope_release_case_del`,
            ADD KEY `idx_test_scope_case` (`release_id`, `functional_case_id`, `is_del`);

        ALTER TABLE `test_release`
            DROP INDEX `uniq_test_release_proj_key_del`,
            ADD KEY `idx_test_release_key` (`project_id`, `release_key`, `is_del`);
    """
