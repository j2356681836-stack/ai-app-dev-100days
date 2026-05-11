import os
from dotenv import load_dotenv
from enum import Enum
from pydantic import BaseModel,model_validator,Field
from openai import OpenAI

# 加载环境
load_dotenv()

# 验证
openai_client = OpenAI(
    api_key = os.getenv('OPENAI_API_KEY'),
    base_url = os.getenv('OPENAI_BASE_URL')
)

# 定义Enum
class BrandEnum(str,Enum):
    EsteeLauder = '雅诗兰黛'
    Lancome = '兰蔻'
    SKII = 'SK-II'

class OrderItem(BaseModel):
    brandname: BrandEnum
    product_name: str = Field(description = '订单中购买该品牌的产品名称')
    quantity: int = Field(default=1, description = '购买数量')
    price: int = Field(description = '单品折扣后的实际单价（不要计算总价，只算单价）')

class BeautyOrder(BaseModel):
    items: list[OrderItem]
    total_amount: int
    discount_applied: bool

    @model_validator(mode = 'after')
    def check_amount(self):
        # 第一步：计算订单总价
        ttl_amount = sum(item.price * item.quantity for item in self.items)

        # 跨字段业务逻辑比对
        # 总金额不等于单品之和且discount_applied为False
        # 1. 如果没打折
        if not self.discount_applied and self.total_amount != ttl_amount:
            raise ValueError(f'未记录折扣，明细总和{ttl_amount}和总金额{self.total_amount}不相等')
        # 2.如果打折了
        if self.discount_applied and self.total_amount > ttl_amount:
            raise ValueError(f'商品打折，但总金额{self.total_amount}比明细总和{ttl_amount}高')

        return self

# --- 大模型测试 ---
response = openai_client.responses.parse(
    model = 'gpt-5.4-mini',
    input = [
        {'role': 'system',
         'content': '获取订单信息。如果遇到枚举之外的品牌，直接丢弃该单品，不要输出。如果有数量，请填入 quantity 字段，绝对不要重复生成相同的 item！'},
        {'role': 'user',
         'content': '我今天八折买了雅诗兰黛的小棕瓶，花了650元，又去隔壁的兰蔻买了两瓶极光水，VVIP活动7.5折优惠，折下来单价700一瓶，最后去娇兰买了一瓶面霜花了680元。'}
    ],
    text_format = BeautyOrder
)

# --- 大模型输出结果 ---
print(response.output_parsed)


# --- 脏数据测试 ---
bad_order = {
    "items": [
        {"brandname": "雅诗兰黛", "product_name": "小棕瓶", "quantity": 1, "price": 600},
        {"brandname": "兰蔻", "product_name": "小黑瓶", "quantity": 1, "price": 1000}
    ],
    "total_amount": 2000, # 致命错误：600+1000 != 2000
    "discount_applied": False
}

try:
    bad_data = BeautyOrder(**bad_order)
    print(bad_data)
except Exception as e:
    # 打印具体报错原因
    print(f"被拦截了！拦截原因: {e.errors()[0]['msg']}")





