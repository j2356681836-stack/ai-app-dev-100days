import os
from dotenv import load_dotenv
from langfuse.openai import OpenAI
from langfuse import observe # 核心：Langfuse 的监控探针


load_dotenv()

client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY'),
    base_url=os.getenv('OPENAI_BASE_URL')
)

# 使用 @observe 装饰器，Langfuse 会自动接管这个函数的所有 I/O 和耗时统计
@observe()
def simple_llm_call(prompt: str):
    print(f"发送请求: {prompt}")
    
    response = client.responses.parse(
        model="gpt-5.4-mini", 
        input=[{"role": "user", "content": prompt}],
    )
    
    # 必须 return，Langfuse 才能捕捉到函数的最终输出
    return response.output_text

if __name__ == "__main__":
    result = simple_llm_call("用一句话概括雅诗兰黛小棕瓶的核心卖点。")
    print(f"模型回复: {result}")