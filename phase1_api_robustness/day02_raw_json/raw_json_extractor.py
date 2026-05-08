import os
import json
from dotenv import load_dotenv

from openai import OpenAI
from anthropic import Anthropic 

# 1. 加载环境变量
load_dotenv()

# 2. 初始化两家的原生 Client
openai_client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY'),
    base_url=os.getenv('OPENAI_BASE_URL')
)

anthropic_client = Anthropic(
    api_key=os.getenv('ANTHROPIC_API_KEY'),
    base_url=os.getenv('ANTHROPIC_BASE_URL')
)

email_schema = {
        'format':{
            'type': 'json_schema',
            'name': 'email_response',
            'schema': {
                'type': 'object',
                'properties':{
                    'name': {'type': 'string'},
                    'email': {'type': 'string'},
                    'plan_interest': {'type': 'string'},
                    'demo_requested': {'type': 'boolean'}
                },
                'required': ['name','email','plan_interest','demo_requested'],
                'additionalProperties': False
            },
        }
    }

response_openai = openai_client.responses.create(
    model = 'gpt-5.4-mini',
    input = [
        {
            'role': 'system',
            'content': 'You are a strict data extraction API. You output ONLY valid JSON. No conversational text, no markdown formatting.'
        },
        {
            'role': 'user',
            'content': 'Extract the key information from this email: John Smith(john@example.com) is interested in our Enterprise plan and wants to schedule a demo for next Tuesday at 2pm.'
        }
    ],
    text = email_schema,
)

raw_string_openai = response_openai.output_text
print(raw_string_openai)

try:
    parsed_dict = json.loads(raw_string_openai)
    print("\n--- 成功反序列化为 Python 字典 ---")
    print(f"提取到的信箱是: {parsed_dict.get('email', '未找到')}")
except json.JSONDecodeError as e:
    print(f"\n❌ JSON 解析失败: {e}")


response_anthropic = anthropic_client.messages.create(
    model = 'claude-opus-4-6',
    max_tokens = 150,
    system=(
    "You are a strict data extraction API. You output ONLY valid JSON. "
    "CRITICAL RULE: You MUST strictly use the following exact keys: "
    "['name', 'email', 'plan_interest', 'demo_requested']. "
    "Do not invent new keys."),
    messages = [
        {
            'role': 'user',
            'content': 'Extract the key information from this email: John Smith(john@example.com) is interested in our Enterprise plan and wants to schedule a demo for next Tuesday at 2pm.',
        }
    ],
    output_config = email_schema,
)

raw_string_anthropic = response_anthropic.content[0].text
print("--- 强制生成的原始字符串 ---")
print(raw_string_anthropic)

try:
    parsed_dict = json.loads(raw_string_anthropic)
    print("\n--- 成功反序列化为 Python 字典 ---")
    print(f"提取到的姓名是: {parsed_dict.get('name', '未找到')}")
except json.JSONDecodeError as e:
    print(f"\n❌ JSON 解析失败: {e}")
