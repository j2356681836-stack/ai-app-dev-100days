import os
import sys

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import SQLAlchemyError


def build_database_url() -> URL:
    """
    从 .env 读取数据库配置，并安全构造 SQLAlchemy 连接地址。
    """
    env_path = find_dotenv()

    if not env_path:
        raise RuntimeError("没有找到 .env 文件，请确认 .env 位于项目根目录。")

    load_dotenv(env_path)

    required_keys = [
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
    ]

    missing_keys = [key for key in required_keys if not os.getenv(key)]
    if missing_keys:
        raise RuntimeError(f".env 缺少以下配置项：{missing_keys}")

    return URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ["POSTGRES_DB"],
    )


def main() -> None:
    database_url = build_database_url()

    print("准备连接数据库：")
    print(database_url.render_as_string(hide_password=True))

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        echo=False,
    )

    try:
        with engine.connect() as connection:
            database_name = connection.execute(
                text("SELECT current_database();")
            ).scalar_one()

            vector_version = connection.execute(
                text(
                    """
                    SELECT extversion
                    FROM pg_extension
                    WHERE extname = 'vector';
                    """
                )
            ).scalar_one_or_none()

            vector_distance = connection.execute(
                text(
                    """
                    SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector AS distance;
                    """
                )
            ).scalar_one()

            print(f"✅ PostgreSQL 连接成功，当前数据库：{database_name}")

            if vector_version is None:
                print("❌ PostgreSQL 已连接，但 pgvector 尚未启用。")
                print("请先执行：CREATE EXTENSION IF NOT EXISTS vector;")
                sys.exit(1)

            print(f"✅ pgvector 已启用，版本：{vector_version}")
            print(f"✅ 向量距离测试成功，计算结果：{vector_distance}")

    except SQLAlchemyError as error:
        print("❌ 数据库连接或查询失败。")
        print("错误详情：")
        print(error)
        sys.exit(1)

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()