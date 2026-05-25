import asyncio
import asyncpg
from pgvector.asyncpg import register_vector

async def test_db_connection():
    print("⏳ 正在尝试连接本地 Docker 数据库...")
    try:
        # 建立异步连接
        conn = await asyncpg.connect(
            user='admin',
            password='admin_password',
            database='beauty_kb',
            host='127.0.0.1',
            port=5432
        )
        
        print("✅ 数据库连接成功！")
        
        # 核心动作：在数据库实例中激活 pgvector 扩展
        await conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
        
        # 将 pgvector 的数据类型注册到当前的连接中
        await register_vector(conn)
        print("✅ pgvector 向量扩展激活并注册成功！数据库基建已就绪。")
        
        # 查验版本
        version = await conn.fetchval('SELECT version()')
        print(f"📊 数据库版本: {version}")

        await conn.close()
        
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_db_connection())