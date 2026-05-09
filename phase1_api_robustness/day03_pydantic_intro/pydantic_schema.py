import os
from dotenv import load_dotenv

from pydantic import BaseModel,Field

from openai import OpenAI
from anthropic import Anthropic

# 加载环境变量
load_dotenv()

# 验证
openai_client = OpenAI(
    api_key = os.getenv('OPENAI_API_KEY'),
    base_url = os.getenv('OPENAI_BASE_URL'))

anthropic_client = Anthropic(
    api_key = os.getenv('ANTHROPIC_API_KEY'),
    base_url = os.getenv('ANTHROPIC_BASE_URL')
)

class MeetingTopic(BaseModel):
    topic: str = Field(description = '会议中具体讨论的议题名称，例如：旧版 API 废弃的决议')
    summary: str = Field(description = '议题的最终结论或处理方案，需高度精简')

class MeetingSummary(BaseModel):
    date: str = Field(description = '会议日期，必须格式化为 YYYY-MM-DD 的形式')
    people: int = Field(description = '参与会议的总人数')
    is_consensus: bool = Field(description = '会议最终是否达成完全一致的共识，无遗留争议')
    topics: list[MeetingTopic] = Field(description = '会议讨论的各个议题列表')

# --- openai大模型输出 ---
response_openai = openai_client.responses.parse(
    model = 'gpt-5.4-mini',
    input = [
        {'role': 'system',
         'content': 'Extract the meeting information.'
        },
        {'role': 'user',
         'content': '''会议记录：时间是2026年5月8日的下午两点半。今天这碰头会主要参与的是后端开发组和产品经理，一共到了7个人。整个讨论过程非常激烈，好在大家最后把几个核心分歧都给盘明白了，最终大家完全达成了一致共识，没有遗留争议。
                        今天主要过了三个事儿：
                        第一是关于旧版 API 废弃的决议。因为新版 GraphQL 接口已经上线，大家商量后决定，现有的 v1 版本 REST API 延迟到今年 Q3 季度末再彻底下线，给客户留足迁移时间。
                        第二个议题是数据库选型。为了配合下半年的 RAG 检索需求，架构组提议引入非关系型数据库。会议最后的结论是：直接在现有的 PostgreSQL 里开启 pgvector 插件，暂时不引入独立的向量数据库，以降低运维成本。
                        第三件是前端的流式输出改造。因为现有的 React 页面在接收长文本时总卡顿，最后定下来下周由李四带头，用原生 EventSource 把大模型的流式接收重写一遍'''
        },
    ],
    text_format = MeetingSummary
)

meeting_openai = response_openai.output_parsed
print("--- OPENAI大模型结构性输出 ---")
print(meeting_openai)

# # Pydantic 自动生成的 Schema
print("--- 自动生成的 JSON Schema ---")
print(MeetingSummary.model_json_schema())



# --- 脏数据验证 ---
dirty_data = {
    "date": "2026-05-08",
    "people": "7",        # 脏数据：大模型输出了字符串形式的数字
    "is_consensus": "yes", # 脏数据：大模型输出了 yes 而不是 True/False
    "topics": []
}

# 字典不能作为单个位置参数直接传入，通过**转化为关键字参数传给类
dirty_summary = MeetingSummary(**dirty_data)
print('---脏数据验证---')
print(dirty_summary)

print("\n--- 破坏性自检：自动类型转换 ---")
try:
    # 尝试用脏字典实例化模型
    test_model = MeetingSummary(**dirty_data)
    print("转换成功！类型如下：")
    print(f"people 字段现在的类型是: {type(test_model.people)} (值: {test_model.people})")
    print(f"is_consensus 字段现在的类型是: {type(test_model.is_consensus)} (值: {test_model.is_consensus})")
except Exception as e:
    print(f"转换失败: {e}")




# --- Day3 学习自检 ---
class TestModel(BaseModel):
    title: str = Field(description = '辩论标题')
    place: str = Field(description = "辩论会所在的城市.绝对规则：仅提取市级名称，必须以“市”结尾，严禁包含区县、街道等更低级别的行政区划。示例：如果是'北京市海淀区'，仅输出'北京市'。")
    date: str = Field(description = '日期，格式化为YYYY-MM-DD形式')
    name: list[str] = Field(description = '参与的人员名字列表')
    people: int = Field(description = '参与辩论的人数')
    summary: str = Field(description = '总结，风格简洁明了')


responsetest = openai_client.responses.parse(
    model = 'gpt-5.4-mini',
    input = [
        {'role': 'system',
         'content': '抓取会议信息'},
        {'role': 'user',
         'content': '''二零一六年12月六号，在北京市海淀区召开了关于吃葡萄到底吐不吐葡萄皮的辩论比赛，正方辩友有张三、李四和王五，反方辩友有黎川，魏什么，王立。
         经过一小时34分钟的辩论，正方在比赛中获得胜利。'''}
    ],
    text_format = TestModel
)

print(responsetest.output_parsed)

testdata = {
    'date': '2026-09-01',
    'title': '关于吃葡萄到底需不需要吐葡萄皮议题进行论证',
    'place': '北京',
    'name': ['张三','李四','王五'],
    'people': '3',
    'summary': '会议进行了五十分钟，最后吃葡萄要吐葡萄皮方获得胜利。'
}

# 打印 Schema 通常调用类的静态方法
print("\n--- TestModel 自动生成的 JSON Schema ---")
print(TestModel.model_json_schema())

print("\n--- TestModel 脏数据自检 ---")
try:
    dirtydata = TestModel(**testdata)
    print(f'people当前的类型是：{type(dirtydata.people)})(值：{dirtydata.people})')
except Exception as e:
    print(f'类型转换失败:{e}')