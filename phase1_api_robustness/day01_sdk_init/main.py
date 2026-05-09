import os
from dotenv import load_dotenv
from openai import OpenAI
from anthropic import Anthropic

# 1. 加载环境变量
load_dotenv()

# 2. 初始化两家的原生 Client
openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)
anthropic_client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url=os.getenv("ANTHROPIC_BASE_URL")
)

def test_openai_api():
    print("\n--- 测试 OpenAI 原生 API ---")
    try:
        # 注意：OpenAI 的 System 提示词是作为 messages 列表的第一项传入的
        response = openai_client.chat.completions.create(
            model="gpt-5.4-mini", # 使用较便宜的模型进行初期测试
            messages=[
                {"role": "system", "content": "你是一个严厉但专业的 Python 架构师，回答问题直接指出核心，不要说废话。"},
                {"role": "user", "content": "请用一句话告诉我，为什么做 AI 开发要学 Pydantic？"}
            ],
            temperature=0.7,
            max_tokens=150
        )
        # 解析返回的深层 JSON 结构提取文本
        print(f"🤖 OpenAI 回复: {response.choices[0].message.content}")
    except Exception as e:
        print(f"❌ OpenAI 调用失败: {e}")

def test_anthropic_api():
    print("\n--- 测试 Anthropic 原生 API ---")
    try:
        # 注意：Anthropic 的 System 提示词是作为顶层参数传入的，而不是混在 messages 里
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6", 
            system="你是一个严厉但专业的 Python 架构师，回答问题直接指出核心，不要说废话。",
            messages=[
                {"role": "user", "content": "请用一句话告诉我，为什么做 AI 开发要学 Pydantic？"}
            ],
            temperature=0.7,
            max_tokens=150
        )
        print(f"🤖 Claude 回复: {response.content[0].text}")
    except Exception as e:
        print(f"❌ Anthropic 调用失败: {e}")

if __name__ == "__main__":
    # 执行测试
    test_openai_api()
    test_anthropic_api()