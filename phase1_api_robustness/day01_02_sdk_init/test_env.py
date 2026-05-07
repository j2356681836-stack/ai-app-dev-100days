import os
from dotenv import load_dotenv

# 1. 加载根目录下的 .env 文件
# find_dotenv() 会自动向上级目录寻找 .env 文件，非常适合深层目录嵌套的项目
load_dotenv()

# 2. 读取环境变量
openai_key = os.getenv("OPENAI_API_KEY")
anthropic_key = os.getenv("ANTHROPIC_API_KEY")

# 3. 安全打印测试 (绝不要打印出完整的 Key)
print("=== 环境变量测试开始 ===")

if openai_key:
    # 只打印前 8 个字符，后面用星号代替，证明读到了即可
    print(f"✅ OpenAI Key 读取成功: {openai_key[:8]}**********")
else:
    print("❌ 错误: 未找到 OPENAI_API_KEY")

if anthropic_key:
    print(f"✅ Anthropic Key 读取成功: {anthropic_key[:10]}**********")
else:
    print("❌ 错误: 未找到 ANTHROPIC_API_KEY")

print("=== 测试结束 ===")