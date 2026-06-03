from sqlalchemy import text
from app.db.database import engine

def run_sql(sql: str):
    with engine.connect() as conn:
        result = conn.execute(text(sql))

        columns = result.keys()
        rows = result.fetchall()

        return [
            dict(zip(columns, row))
            for row in rows
        ]


if __name__ == "__main__":
    rows = run_sql(
        """
        SELECT
            COUNT(*)
        FROM fact_orders
        """
    )

    print(rows)