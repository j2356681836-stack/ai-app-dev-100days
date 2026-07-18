from sqlalchemy import inspect, text
from app.db.database import engine


V2_SCHEMA_NAME = "beauty_bi_v2"

EXPECTED_DIM_DATE_COLUMNS = {
    "date_key",
    "full_date",
    "year",
    "quarter",
    "month",
    "month_name",
    "week_of_year",
    "day_of_month",
    "day_of_week",
    "is_weekend",
    "is_holiday",
    "holiday_name",
}


def check_v2_database() -> None:
    """
    检查当前数据库连接以及 V2 dim_date 表结构。
    """
    with engine.connect() as connection:
        database_name = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

    schema_name = V2_SCHEMA_NAME

    print(f"Database: {database_name}")
    print(f"Target schema: {schema_name}")

    inspector = inspect(engine)

    table_names = set(
        inspector.get_table_names(
            schema=schema_name,
        )
    )

    if "dim_date" not in table_names:
        raise RuntimeError(
            "当前数据库不存在 dim_date，"
            "需要先执行 beauty_bi_v2/schema.sql。"
        )

    actual_columns = {
        column["name"]
        for column in inspector.get_columns(
            "dim_date",
            schema=schema_name,
        )
    }

    missing_columns = (
        EXPECTED_DIM_DATE_COLUMNS - actual_columns
    )

    unexpected_columns = (
        actual_columns - EXPECTED_DIM_DATE_COLUMNS
    )

    if missing_columns:
        raise RuntimeError(
            "dim_date 缺少 V2 字段："
            f"{sorted(missing_columns)}"
        )

    if unexpected_columns:
        print(
            "dim_date 存在额外字段："
            f"{sorted(unexpected_columns)}"
        )

    with engine.connect() as connection:
        row_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_date
                """
            )
        ).scalar_one()

    with engine.connect() as connection:
        row_count, min_date, max_date = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    MIN(full_date),
                    MAX(full_date)
                FROM beauty_bi_v2.dim_date
                """
            )
        ).one()

    print(f"Existing dim_date rows: {row_count}")
    print(f"Existing date range: {min_date} -> {max_date}")

    print("dim_date structure check passed.")
    print(
        "dim_date columns: "
        f"{sorted(actual_columns)}"
    )
    print(f"Existing dim_date rows: {row_count}")


if __name__ == "__main__":
    check_v2_database()