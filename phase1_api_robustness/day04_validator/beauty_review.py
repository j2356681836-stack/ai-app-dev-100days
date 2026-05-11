import os
import re
from dotenv import load_dotenv
from typing import Annotated,Any
from pydantic import BaseModel,ValidationError,BeforeValidator,field_validator,ValidationInfo

from openai import OpenAI
from anthropic import Anthropic

# 加载环境
load_dotenv()

# OPENAI
openai_client = OpenAI(
    api_key = os.getenv('OPENAI_API_KEY'),
    base_url = os.getenv('OPENAI_BASE_URL')
)

# 方法一：Annotated模式
# 第一个验证器：检查ensure_paid的类型
def ensure_paid(value: Any):
    # Any：任何类型
    # 警惕传入列表中含有多个数字的问题：取指定位置的值/强制报错/其他
    if isinstance(value, (float,int)):
        return float(value)
    else:
        # 正则表达式，提取纯数字部分
        # FIXME: 目前正则仅支持阿拉伯数字清洗。
        # TODO: 如果业务涉及大量中文数字输入，需引入 cn2an 库或在 Prompt 中强制约束。
        cleaned = re.sub(r'[^\d.]', '', str(value))
        return cleaned

class ReviewData(BaseModel):
    brand: str
    product_name: str
    actual_paid: Annotated[float, BeforeValidator(ensure_paid)]
    symptoms_reported: list[str]
    sentiment_score: int

# 方法二：装饰器模式
    # 第二个验证器： 检查分数范围，并自定义ValidationInfo
    @field_validator('sentiment_score')     # mode默认after，这里不用写
    @classmethod
    def check_score (cls, value: int, info: ValidationInfo):
        if value < 0 or value > 5:
            raise ValueError('情感得分必须在 1-5 之间')
        return value

# --- 调用大模型 ---
response = openai_client.responses.parse(
    model = 'gpt-5.4-mini',
    input = [
        {'role': 'system',
         'content': 'Extract the information'},
        {'role': 'user',
         'content': '丽华在上海国贸购买了雅思兰黛的小棕瓶，据她所说原价980元，赶上活动折扣价680.5元，于是买了一瓶，但是用了三天后出现了爆痘、烂脸的症状，满生气的，1星差评！'}
    ],
    text_format = ReviewData
)

print('---大模型调用结果---')
print(response.output_parsed)

# --- 不调用大模型 ---
# --- 脏数据 ---
dirty_review = {
    "brand": "雅诗兰黛",
    "product_name": "小棕瓶",
    "actual_paid": "大概花了￥680.5块钱吧",  # 致命脏数据
    "symptoms_reported": ["爆痘", "烂脸"],
    "sentiment_score": '5'  # 致命越界数据
}

print('---非大模型结果---')
# 脏数据验证
try :
    testdata = ReviewData(**dirty_review)
    print(testdata)
except Exception as e:
    print(repr(e.errors()[0]['type']))
