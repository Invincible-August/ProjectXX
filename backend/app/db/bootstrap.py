"""
启动期 schema 补丁与一次性数据迁移（从 main 迁出）。

正式环境应改用 Alembic；本模块仅服务本地 SQLite 便利开发。
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base

logger = logging.getLogger(__name__)

# users 表新增列的补丁清单：(列名, SQLite 列类型与默认值 DDL)
_USER_TABLE_COLUMN_PATCHES: tuple[tuple[str, str], ...] = (
    ("email", "VARCHAR(255)"),
    ("phone", "VARCHAR(20)"),
    ("real_name", "VARCHAR(64)"),
    ("id_card_hash", "VARCHAR(128)"),
    ("id_card_masked", "VARCHAR(32)"),
    ("id_verified_level", "VARCHAR(32) NOT NULL DEFAULT 'none'"),
    ("email_verified", "BOOLEAN NOT NULL DEFAULT 0"),
    ("phone_verified", "BOOLEAN NOT NULL DEFAULT 0"),
)

# characters 表 M2 新增列补丁
_CHARACTER_TABLE_COLUMN_PATCHES: tuple[tuple[str, str], ...] = (
    ("realm_progress", "BIGINT NOT NULL DEFAULT 0"),
    ("breakthrough_grade", "VARCHAR(32) NOT NULL DEFAULT 'none'"),
    ("divine_ability_slots", "INTEGER NOT NULL DEFAULT 0"),
    ("membership_tier", "VARCHAR(32) NOT NULL DEFAULT 'free'"),
    ("membership_expires_at", "DATETIME"),
    ("tiandao_points", "INTEGER NOT NULL DEFAULT 0"),
    ("pending_offline_json", "TEXT"),
    ("offline_capped_at", "DATETIME"),
    # M3 体力 / 试炼傀儡
    ("stamina", "INTEGER NOT NULL DEFAULT 120"),
    ("stamina_updated_at", "DATETIME"),
    ("trial_puppet_count", "INTEGER NOT NULL DEFAULT 1"),
    # M4 双线程成长
    ("divine_sense_capacity_bonus", "INTEGER NOT NULL DEFAULT 0"),
    ("array_craft_level", "INTEGER NOT NULL DEFAULT 0"),
    ("divine_sense_backlash", "INTEGER NOT NULL DEFAULT 0"),
    # M5 环境与轮回
    ("reincarnation_points", "INTEGER NOT NULL DEFAULT 0"),
    ("growth_attrs_json", "TEXT"),
    ("story_flags_json", "TEXT"),
    ("ferry_deadline_at", "DATETIME"),
    ("reincarnation_count", "INTEGER NOT NULL DEFAULT 0"),
    ("legacy_items_json", "TEXT"),
    ("fate_luck", "INTEGER NOT NULL DEFAULT 0"),
    ("demonic_nature", "INTEGER NOT NULL DEFAULT 0"),
    ("last_self_rescue_at", "DATETIME"),
    # M5 灵根环境标签（JSON 列表）
    ("spirit_root_tags_json", "TEXT"),
    # 轮回强化：历史最高大境界
    ("peak_major_realm", "VARCHAR(32) NOT NULL DEFAULT 'body_tempering'"),
    # M7 L1：当前宗门 id（散修 null）
    ("sect_id", "INTEGER"),
    # M7 L7：性别 male|female（可空，存量补选）
    ("gender", "VARCHAR(16)"),
)

# inventory_items 表补列
_INVENTORY_ITEM_COLUMN_PATCHES: tuple[tuple[str, str], ...] = (
    ("bag_kind", "VARCHAR(32) NOT NULL DEFAULT 'normal'"),
)

# pets 表 N4/PET-D01/D02/D06 补列
_PET_TABLE_COLUMN_PATCHES: tuple[tuple[str, str], ...] = (
    ("grade", "INTEGER NOT NULL DEFAULT 1"),
    ("affixes_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("value_reroll_counts_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("type_reroll_counts_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("skills_learned_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("skills_equipped_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("racial_talent_id", "VARCHAR(64) NOT NULL DEFAULT ''"),
    ("passives_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("feed_counts_json", "TEXT NOT NULL DEFAULT '{}'"),
)

_M2_CULTIVATION_MIGRATION_ID = "m2_cultivation_to_realm_progress_v1"

# craft_jobs 表 M5 补列
_CRAFT_JOB_COLUMN_PATCHES: tuple[tuple[str, str], ...] = (
    ("env_lock_json", "TEXT"),
)

# avatars 表 AVATAR-D03 体力 / 日行动补列 + 道友助战开关
_AVATAR_TABLE_COLUMN_PATCHES: tuple[tuple[str, str], ...] = (
    ("stamina", "INTEGER NOT NULL DEFAULT 0"),
    ("daily_actions_used", "INTEGER NOT NULL DEFAULT 0"),
    ("daily_actions_day", "VARCHAR(16) NOT NULL DEFAULT ''"),
    ("stamina_recovered_at", "DATETIME"),
    ("assist_friends_enabled", "INTEGER NOT NULL DEFAULT 0"),
)


def _patch_sqlite_missing_craft_job_columns(connection: Connection) -> None:
    """
    为存量 SQLite 库的 craft_jobs 表补齐 M5 env_lock 列。

    Args:
        connection: 同步 SQLAlchemy 连接。
    """
    existing = {
        row[1]
        for row in connection.execute(text("PRAGMA table_info(craft_jobs)")).fetchall()
    }
    if not existing:
        return
    for column_name, column_ddl in _CRAFT_JOB_COLUMN_PATCHES:
        if column_name in existing:
            continue
        connection.execute(
            text(f"ALTER TABLE craft_jobs ADD COLUMN {column_name} {column_ddl}"),
        )
        logger.info("sqlite column patched table=craft_jobs column=%s", column_name)


def _patch_sqlite_missing_avatar_columns(connection: Connection) -> None:
    """
    为存量 SQLite 库的 avatars 表补齐体力 / 日行动列（AVATAR-D03）。

    Args:
        connection: 同步 SQLAlchemy 连接。
    """
    existing = {
        row[1]
        for row in connection.execute(text("PRAGMA table_info(avatars)")).fetchall()
    }
    if not existing:
        return
    for column_name, column_ddl in _AVATAR_TABLE_COLUMN_PATCHES:
        if column_name in existing:
            continue
        connection.execute(
            text(f"ALTER TABLE avatars ADD COLUMN {column_name} {column_ddl}"),
        )
        logger.info("sqlite column patched table=avatars column=%s", column_name)


def _patch_sqlite_missing_user_columns(connection: Connection) -> None:
    """
    为存量 SQLite 库的 users 表补齐核验相关新增列。

    Args:
        connection: `run_sync` 传入的同步 SQLAlchemy 连接。
    """
    existing_columns = {
        row[1] for row in connection.execute(text("PRAGMA table_info(users)")).fetchall()
    }
    for column_name, column_ddl in _USER_TABLE_COLUMN_PATCHES:
        if column_name in existing_columns:
            continue
        connection.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_ddl}"))
        logger.info("sqlite column patched table=users column=%s", column_name)


def _patch_sqlite_missing_character_columns(connection: Connection) -> bool:
    """
    为存量 SQLite 库的 characters 表补齐 M2 新增列。

    Args:
        connection: 同步 SQLAlchemy 连接。

    Returns:
        bool: 若本次运行刚新增 ``realm_progress`` 列则为 True。
    """
    existing_columns = {
        row[1]
        for row in connection.execute(text("PRAGMA table_info(characters)")).fetchall()
    }
    realm_progress_just_added = False
    for column_name, column_ddl in _CHARACTER_TABLE_COLUMN_PATCHES:
        if column_name in existing_columns:
            continue
        connection.execute(
            text(f"ALTER TABLE characters ADD COLUMN {column_name} {column_ddl}"),
        )
        logger.info("sqlite column patched table=characters column=%s", column_name)
        if column_name == "realm_progress":
            realm_progress_just_added = True
    return realm_progress_just_added


def _patch_sqlite_missing_inventory_columns(connection: Connection) -> None:
    """
    为存量 SQLite 库的 inventory_items 表补齐 bag_kind 列。

    Args:
        connection: 同步 SQLAlchemy 连接。
    """
    existing = {
        row[1]
        for row in connection.execute(text("PRAGMA table_info(inventory_items)")).fetchall()
    }
    if not existing:
        return
    for column_name, column_ddl in _INVENTORY_ITEM_COLUMN_PATCHES:
        if column_name in existing:
            continue
        connection.execute(
            text(f"ALTER TABLE inventory_items ADD COLUMN {column_name} {column_ddl}"),
        )
        logger.info(
            "sqlite column patched table=inventory_items column=%s",
            column_name,
        )


def _patch_sqlite_missing_pet_columns(connection: Connection) -> None:
    """
    为存量 SQLite 库的 pets 表补齐 N4/PET-D01/D02/D06 列（含 type_reroll_counts_json）。

    Args:
        connection: 同步 SQLAlchemy 连接。
    """
    existing = {
        row[1]
        for row in connection.execute(text("PRAGMA table_info(pets)")).fetchall()
    }
    if not existing:
        return
    for column_name, column_ddl in _PET_TABLE_COLUMN_PATCHES:
        if column_name in existing:
            continue
        connection.execute(
            text(f"ALTER TABLE pets ADD COLUMN {column_name} {column_ddl}"),
        )
        logger.info("sqlite column patched table=pets column=%s", column_name)


_DAO_CONTEST_COLUMN_PATCHES: tuple[tuple[str, str], ...] = (
    ("phase", "VARCHAR(32)"),
    ("phase_ends_at", "DATETIME"),
    ("current_round_index", "INTEGER NOT NULL DEFAULT 0"),
    ("arena_state_json", "TEXT"),
)

_DAO_CONTEST_ENTRY_COLUMN_PATCHES: tuple[tuple[str, str], ...] = (
    ("rsvp_status", "VARCHAR(16) NOT NULL DEFAULT 'none'"),
    ("rsvp_at", "DATETIME"),
    ("in_arena", "BOOLEAN NOT NULL DEFAULT 0"),
)

_DAO_CONTEST_MATCH_COLUMN_PATCHES: tuple[tuple[str, str], ...] = (
    ("loadout_locked_at", "DATETIME"),
    ("presence_override", "BOOLEAN NOT NULL DEFAULT 0"),
    ("side_a_forfeit", "BOOLEAN NOT NULL DEFAULT 0"),
    ("side_b_forfeit", "BOOLEAN NOT NULL DEFAULT 0"),
)

_FACE_TRADE_SESSION_COLUMN_PATCHES: tuple[tuple[str, str], ...] = (
    ("initiator_locked", "INTEGER NOT NULL DEFAULT 0"),
    ("peer_locked", "INTEGER NOT NULL DEFAULT 0"),
)


def _patch_sqlite_table_columns(
    connection: Connection,
    *,
    table: str,
    patches: tuple[tuple[str, str], ...],
) -> None:
    """通用：为存量 SQLite 表补列。"""
    existing = {
        row[1]
        for row in connection.execute(text(f"PRAGMA table_info({table})")).fetchall()
    }
    if not existing:
        return
    for column_name, column_ddl in patches:
        if column_name in existing:
            continue
        connection.execute(
            text(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_ddl}"),
        )
        logger.info("sqlite column patched table=%s column=%s", table, column_name)


def _patch_sqlite_dao_contest_columns(connection: Connection) -> None:
    """补齐道主之争擂台分阶段列。"""
    _patch_sqlite_table_columns(
        connection,
        table="dao_contests",
        patches=_DAO_CONTEST_COLUMN_PATCHES,
    )
    _patch_sqlite_table_columns(
        connection,
        table="dao_contest_entries",
        patches=_DAO_CONTEST_ENTRY_COLUMN_PATCHES,
    )
    _patch_sqlite_table_columns(
        connection,
        table="dao_contest_matches",
        patches=_DAO_CONTEST_MATCH_COLUMN_PATCHES,
    )


def _patch_sqlite_face_trade_columns(connection: Connection) -> None:
    """
    补齐面交会话锁定列（草稿/锁定分离）。

    Args:
        connection: 同步 SQLAlchemy 连接。
    """
    _patch_sqlite_table_columns(
        connection,
        table="face_trade_sessions",
        patches=_FACE_TRADE_SESSION_COLUMN_PATCHES,
    )


def _backfill_reincarnation_bonus_rows(connection: Connection) -> None:
    """
    为尚无永久加成行的角色补插全 0 行。

    Args:
        connection: 同步 SQLAlchemy 连接。
    """
    # 表可能尚不存在（首次 create_all 前不应调用；本函数在 create_all 后执行）
    tables = {
        row[0]
        for row in connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'"),
        ).fetchall()
    }
    if "character_reincarnation_bonuses" not in tables or "characters" not in tables:
        return
    result = connection.execute(
        text(
            "INSERT OR IGNORE INTO character_reincarnation_bonuses "
            "(character_id, initial_attr_bonus, minor_growth_bonus, major_growth_bonus, "
            "break_rate_bonus, lifetime_applied_growth, constitution_slots_bought, "
            "spirit_root_slots_bought, shop_seed) "
            "SELECT id, 0, 0, 0, 0, 0, 0, 0, 0 FROM characters",
        ),
    )
    if result.rowcount:
        logger.info("backfilled reincarnation bonus rows=%s", result.rowcount)


def _backfill_peak_major_realm(connection: Connection) -> None:
    """
    将 peak_major_realm 为空/缺失语义的角色回填为当前 major_realm。

    Args:
        connection: 同步 SQLAlchemy 连接。
    """
    existing = {
        row[1]
        for row in connection.execute(text("PRAGMA table_info(characters)")).fetchall()
    }
    if "peak_major_realm" not in existing:
        return
    connection.execute(
        text(
            "UPDATE characters SET peak_major_realm = major_realm "
            "WHERE peak_major_realm IS NULL OR peak_major_realm = ''",
        ),
    )


def _migrate_m1_cultivation_to_realm_progress(connection: Connection) -> None:
    """
    M1→M2 一次性迁移：旧号已堆修为视为「已投入境界进度」。

    仅应在 ``realm_progress`` 列**本启动刚补上**时调用。
    """
    result = connection.execute(
        text(
            "UPDATE characters SET realm_progress = cultivation_points, "
            "cultivation_points = 0 "
            "WHERE realm_progress = 0 AND cultivation_points > 0",
        ),
    )
    if result.rowcount:
        logger.info(
            "migrated M1 cultivation_points -> realm_progress rows=%s",
            result.rowcount,
        )


def _ensure_schema_migrations_table(connection: Connection) -> None:
    """创建 schema_migrations 表（记录一次性数据迁移）。"""
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "id VARCHAR(64) PRIMARY KEY NOT NULL, "
            "applied_at DATETIME NOT NULL"
            ")",
        ),
    )


def _schema_migration_applied(connection: Connection, migration_id: str) -> bool:
    """查询迁移是否已登记。"""
    row = connection.execute(
        text("SELECT 1 FROM schema_migrations WHERE id = :id LIMIT 1"),
        {"id": migration_id},
    ).fetchone()
    return row is not None


def _record_schema_migration(connection: Connection, migration_id: str) -> None:
    """登记已执行的一次性迁移。"""
    connection.execute(
        text(
            "INSERT OR IGNORE INTO schema_migrations (id, applied_at) "
            "VALUES (:id, CURRENT_TIMESTAMP)",
        ),
        {"id": migration_id},
    )


def _ensure_performance_indexes(connection: Connection) -> None:
    """
    为已有库补齐复合索引（SQLite create_all 不改已有表索引）。

    与 ORM ``__table_args__`` 对齐；新建库由 metadata.create_all 创建。
    """
    statements = (
        "CREATE INDEX IF NOT EXISTS ix_breakthrough_sessions_character_status "
        "ON breakthrough_sessions (character_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_craft_jobs_character_status "
        "ON craft_jobs (character_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_pet_hatch_jobs_character_status "
        "ON pet_hatch_jobs (character_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_tribulation_sessions_character_phase "
        "ON tribulation_sessions (character_id, phase)",
        "CREATE INDEX IF NOT EXISTS ix_inventory_items_char_item "
        "ON inventory_items (character_id, item_id, item_type, bag_kind)",
        "CREATE INDEX IF NOT EXISTS ix_character_constitution_slots_item_instance_id "
        "ON character_constitution_slots (item_instance_id)",
    )
    for sql in statements:
        try:
            connection.execute(text(sql))
        except Exception:  # noqa: BLE001 — 表尚未创建时忽略
            logger.debug("skip index ensure sql=%s", sql[:80], exc_info=True)


async def prepare_database(engine: AsyncEngine) -> None:
    """
    创建表结构、补齐 SQLite 缺列，并执行已登记的一次性数据迁移。

    Args:
        engine: 异步引擎。
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # 仅 SQLite 需要手动补列；其他数据库应通过 Alembic 迁移管理
        if engine.dialect.name == "sqlite":
            await connection.run_sync(_patch_sqlite_missing_user_columns)
            realm_col_added = await connection.run_sync(
                _patch_sqlite_missing_character_columns,
            )
            await connection.run_sync(_patch_sqlite_missing_craft_job_columns)
            await connection.run_sync(_patch_sqlite_missing_avatar_columns)
            await connection.run_sync(_patch_sqlite_missing_inventory_columns)
            await connection.run_sync(_patch_sqlite_missing_pet_columns)
            await connection.run_sync(_patch_sqlite_dao_contest_columns)
            await connection.run_sync(_patch_sqlite_face_trade_columns)
            await connection.run_sync(_backfill_peak_major_realm)
            await connection.run_sync(_backfill_reincarnation_bonus_rows)
            await connection.run_sync(_ensure_schema_migrations_table)
            await connection.run_sync(_ensure_performance_indexes)

            def _maybe_migrate_m1_pool(conn: Connection) -> None:
                """仅在刚补 realm_progress 列且尚未登记时迁移。"""
                if _schema_migration_applied(conn, _M2_CULTIVATION_MIGRATION_ID):
                    return
                if realm_col_added:
                    _migrate_m1_cultivation_to_realm_progress(conn)
                else:
                    logger.info(
                        "skip M1 pool migration (realm_progress already present); "
                        "mark %s applied",
                        _M2_CULTIVATION_MIGRATION_ID,
                    )
                _record_schema_migration(conn, _M2_CULTIVATION_MIGRATION_ID)

            await connection.run_sync(_maybe_migrate_m1_pool)
        else:
            # 非 SQLite：仍尝试补复合索引（IF NOT EXISTS 方言差异由 except 吞）
            await connection.run_sync(_ensure_performance_indexes)
