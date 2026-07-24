import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv
from psycopg import sql

from app.db.database import engine


load_dotenv()


_ROLE_NAME_PATTERN = re.compile(
    r"^[a-z_][a-z0-9_]{0,62}$"
)


@dataclass(frozen=True)
class QueryRoleConfig:
    role_name: str
    password: str
    database_name: str
    schema_name: str
    owner_role_name: str
    connection_limit: int
    statement_timeout_ms: int


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Missing required environment variable: {name}"
        )

    return value


def _validated_role_name(
    value: str,
    *,
    field_name: str,
) -> str:
    if not _ROLE_NAME_PATTERN.fullmatch(value):
        raise RuntimeError(
            f"{field_name} must match "
            "^[a-z_][a-z0-9_]{0,62}$"
        )

    return value


def load_query_role_config() -> QueryRoleConfig:
    role_name = _validated_role_name(
        _required_env("AI_QUERY_POSTGRES_USER"),
        field_name="AI_QUERY_POSTGRES_USER",
    )

    owner_role_name = _validated_role_name(
        _required_env("POSTGRES_USER"),
        field_name="POSTGRES_USER",
    )

    if role_name == owner_role_name:
        raise RuntimeError(
            "AI query role must not reuse POSTGRES_USER."
        )

    connection_limit = int(
        os.getenv("AI_QUERY_CONNECTION_LIMIT", "10")
    )
    statement_timeout_ms = int(
        os.getenv("AI_QUERY_STATEMENT_TIMEOUT_MS", "5000")
    )

    if not 1 <= connection_limit <= 50:
        raise RuntimeError(
            "AI_QUERY_CONNECTION_LIMIT must be between 1 and 50."
        )

    if not 100 <= statement_timeout_ms <= 60_000:
        raise RuntimeError(
            "AI_QUERY_STATEMENT_TIMEOUT_MS must be between "
            "100 and 60000."
        )

    return QueryRoleConfig(
        role_name=role_name,
        password=_required_env(
            "AI_QUERY_POSTGRES_PASSWORD"
        ),
        database_name=_required_env("POSTGRES_DB"),
        schema_name="beauty_bi_v2",
        owner_role_name=owner_role_name,
        connection_limit=connection_limit,
        statement_timeout_ms=statement_timeout_ms,
    )


def _role_exists(cursor, role_name: str) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_roles
            WHERE rolname = %s
        )
        """,
        (role_name,),
    )

    row = cursor.fetchone()
    return bool(row and row[0])


def _assert_role_owns_no_project_objects(
    cursor,
    config: QueryRoleConfig,
) -> None:
    cursor.execute(
        """
        SELECT
            n.nspname,
            c.relname,
            c.relkind
        FROM pg_class c
        JOIN pg_namespace n
            ON n.oid = c.relnamespace
        JOIN pg_roles r
            ON r.oid = c.relowner
        WHERE r.rolname = %s
          AND n.nspname IN ('public', %s)
        ORDER BY n.nspname, c.relname
        LIMIT 20
        """,
        (
            config.role_name,
            config.schema_name,
        ),
    )

    owned_objects = cursor.fetchall()

    if owned_objects:
        names = ", ".join(
            f"{schema}.{name}"
            for schema, name, _ in owned_objects
        )

        raise RuntimeError(
            "AI query role already owns project objects. "
            f"Ownership must be removed first: {names}"
        )


def _create_or_update_role(
    cursor,
    config: QueryRoleConfig,
) -> str:
    role_identifier = sql.Identifier(config.role_name)

    attributes = sql.SQL(
        """
        LOGIN
        PASSWORD {}
        NOSUPERUSER
        NOCREATEDB
        NOCREATEROLE
        NOREPLICATION
        NOINHERIT
        CONNECTION LIMIT {}
        """
    ).format(
        sql.Literal(config.password),
        sql.Literal(config.connection_limit),
    )

    if _role_exists(cursor, config.role_name):
        cursor.execute(
            sql.SQL("ALTER ROLE {} WITH ").format(
                role_identifier
            )
            + attributes
        )
        action = "updated"
    else:
        cursor.execute(
            sql.SQL("CREATE ROLE {} WITH ").format(
                role_identifier
            )
            + attributes
        )
        action = "created"

    cursor.execute(
        sql.SQL(
            "ALTER ROLE {} "
            "SET default_transaction_read_only TO on"
        ).format(role_identifier)
    )

    cursor.execute(
        sql.SQL(
            "ALTER ROLE {} SET statement_timeout TO {}"
        ).format(
            role_identifier,
            sql.Literal(
                f"{config.statement_timeout_ms}ms"
            ),
        )
    )

    return action


def _apply_database_privileges(
    cursor,
    config: QueryRoleConfig,
) -> None:
    role = sql.Identifier(config.role_name)
    database = sql.Identifier(config.database_name)
    schema = sql.Identifier(config.schema_name)
    owner = sql.Identifier(config.owner_role_name)

    cursor.execute(
        sql.SQL(
            "REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}"
        ).format(database, role)
    )

    cursor.execute(
        sql.SQL(
            "GRANT CONNECT ON DATABASE {} TO {}"
        ).format(database, role)
    )

    # 显式撤销，但注意：若同类权限通过 PUBLIC 授予，
    # PostgreSQL 没有针对单个角色的 DENY 语义。
    # Integration Tests 会验证真实有效权限。
    cursor.execute(
        sql.SQL(
            "REVOKE CREATE, TEMPORARY ON DATABASE {} FROM {}"
        ).format(database, role)
    )

    cursor.execute(
        sql.SQL(
            "REVOKE ALL PRIVILEGES ON SCHEMA public FROM {}"
        ).format(role)
    )

    cursor.execute(
        sql.SQL(
            "REVOKE ALL PRIVILEGES ON ALL TABLES "
            "IN SCHEMA public FROM {}"
        ).format(role)
    )

    cursor.execute(
        sql.SQL(
            "REVOKE ALL PRIVILEGES ON ALL SEQUENCES "
            "IN SCHEMA public FROM {}"
        ).format(role)
    )

    cursor.execute(
        sql.SQL(
            "REVOKE ALL PRIVILEGES ON SCHEMA {} FROM {}"
        ).format(schema, role)
    )

    cursor.execute(
        sql.SQL(
            "GRANT USAGE ON SCHEMA {} TO {}"
        ).format(schema, role)
    )

    cursor.execute(
        sql.SQL(
            "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, "
            "REFERENCES, TRIGGER "
            "ON ALL TABLES IN SCHEMA {} FROM {}"
        ).format(schema, role)
    )

    cursor.execute(
        sql.SQL(
            "GRANT SELECT ON ALL TABLES "
            "IN SCHEMA {} TO {}"
        ).format(schema, role)
    )

    cursor.execute(
        sql.SQL(
            "REVOKE ALL PRIVILEGES ON ALL SEQUENCES "
            "IN SCHEMA {} FROM {}"
        ).format(schema, role)
    )

    # 保护后续由当前项目 Owner 创建的新 V2 表。
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES "
            "FOR ROLE {} "
            "IN SCHEMA {} "
            "GRANT SELECT ON TABLES TO {}"
        ).format(owner, schema, role)
    )

    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES "
            "FOR ROLE {} "
            "IN SCHEMA {} "
            "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, "
            "REFERENCES, TRIGGER ON TABLES FROM {}"
        ).format(owner, schema, role)
    )


def _read_role_summary(
    cursor,
    config: QueryRoleConfig,
) -> dict:
    cursor.execute(
        """
        SELECT
            rolname,
            rolcanlogin,
            rolsuper,
            rolcreatedb,
            rolcreaterole,
            rolreplication,
            rolinherit,
            rolconnlimit
        FROM pg_roles
        WHERE rolname = %s
        """,
        (config.role_name,),
    )

    row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "Query role was not found after provisioning."
        )

    columns = (
        "role_name",
        "can_login",
        "is_superuser",
        "can_create_database",
        "can_create_role",
        "can_replicate",
        "inherits_other_roles",
        "connection_limit",
    )

    return dict(zip(columns, row))


def provision_query_role() -> dict:
    """
    创建或更新 AI Query Runtime 专用 PostgreSQL Role。

    该命令需要使用 POSTGRES_USER 对应的 Owner/Admin 连接。
    密码只从环境变量读取，不打印、不写入代码。
    """

    config = load_query_role_config()

    raw_connection = engine.raw_connection()
    driver_connection = raw_connection.driver_connection

    try:
        with driver_connection.cursor() as cursor:
            action = _create_or_update_role(
                cursor,
                config,
            )

            _assert_role_owns_no_project_objects(
                cursor,
                config,
            )

            _apply_database_privileges(
                cursor,
                config,
            )

            summary = _read_role_summary(
                cursor,
                config,
            )

        driver_connection.commit()

    except Exception:
        driver_connection.rollback()
        raise

    finally:
        raw_connection.close()

    return {
        "action": action,
        "database": config.database_name,
        "schema": config.schema_name,
        "statement_timeout_ms": (
            config.statement_timeout_ms
        ),
        **summary,
    }


def main() -> None:
    result = provision_query_role()

    print("=" * 80)
    print("AI Query PostgreSQL Role Provisioning")
    print(f"Action: {result['action']}")
    print(f"Role: {result['role_name']}")
    print(f"Database: {result['database']}")
    print(f"Schema: {result['schema']}")
    print(f"Can login: {result['can_login']}")
    print(f"Superuser: {result['is_superuser']}")
    print(
        "Create database: "
        f"{result['can_create_database']}"
    )
    print(
        "Create role: "
        f"{result['can_create_role']}"
    )
    print(
        "Replication: "
        f"{result['can_replicate']}"
    )
    print(
        "Inherit: "
        f"{result['inherits_other_roles']}"
    )
    print(
        "Connection limit: "
        f"{result['connection_limit']}"
    )
    print(
        "Default statement timeout: "
        f"{result['statement_timeout_ms']}ms"
    )
    print("Password: [not displayed]")
    print("=" * 80)


if __name__ == "__main__":
    main()
