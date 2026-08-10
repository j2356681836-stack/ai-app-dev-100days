from __future__ import annotations

from sqlalchemy import text

from app.db.database import engine


TARGET_SCHEMA = "beauty_bi_v2"


def _quote_identifier(value: str) -> str:
    """
    PostgreSQL identifier quoting for table names returned by pg_catalog.

    The schema is server-owned and fixed; table names come from pg_tables.
    """
    return '"' + value.replace('"', '""') + '"'


def _load_table_names() -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = :schema
                ORDER BY tablename
                """
            ),
            {"schema": TARGET_SCHEMA},
        ).scalars()

        return list(rows)


def _print_statistics() -> None:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    relname,
                    n_live_tup,
                    n_dead_tup,
                    last_analyze,
                    last_autoanalyze
                FROM pg_stat_user_tables
                WHERE schemaname = :schema
                ORDER BY relname
                """
            ),
            {"schema": TARGET_SCHEMA},
        ).fetchall()

    print("=" * 80)
    print("Dataset V2 Planner Statistics")

    for row in rows:
        print(row)


def analyze_dataset_v2() -> None:
    table_names = _load_table_names()

    if not table_names:
        raise RuntimeError(
            f"No tables found in schema: {TARGET_SCHEMA}"
        )

    print("=" * 80)
    print("Day81 Dataset V2 ANALYZE")
    print(f"Schema: {TARGET_SCHEMA}")
    print(f"Tables: {len(table_names)}")

    # ANALYZE is a database-maintenance action, so this script deliberately
    # uses app.db.database.engine rather than the governed read-only query
    # engine used by the AI analytics runtime.
    with engine.begin() as connection:
        for table_name in table_names:
            qualified_name = (
                f'{_quote_identifier(TARGET_SCHEMA)}.'
                f'{_quote_identifier(table_name)}'
            )

            print(f"ANALYZE {qualified_name}")

            connection.execute(
                text(
                    f"ANALYZE {qualified_name}"
                )
            )

    print("=" * 80)
    print(
        "ANALYZE completed. "
        "Production query policy was not changed."
    )

    _print_statistics()


if __name__ == "__main__":
    analyze_dataset_v2()
