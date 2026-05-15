import os
from dotenv import load_dotenv
from openai import OpenAI
from enum import Enum
from typing import Type
from pydantic import BaseModel,ValidationError,Field,model_validator

# 加载环境
load_dotenv()

# 验证
Client = OpenAI(
    api_key = os.getenv('OPENAI_API_KEY'),
    base_url = os.getenv('OPENAI_BASE_URL')
)

# 定义品牌枚举范围
class BrandEnum(str, Enum):
    EsteeLauder = '雅诗兰黛'
    Lancome = '兰蔻'
    SKII = 'SK-II'
    Other = '其他品牌'

class OrderItems(BaseModel):
    brand_name: BrandEnum = Field(description = "品牌名，不在枚举的具体品牌名字一律放进'其他品牌'中")
    product_name: str = Field(description = '属于该品牌的商品名')
    price: int = Field(description = '商品单价')
    quantity: int = Field(description = '商品购买数量')

class BeautyOrder(BaseModel):
    items: list[OrderItems]
    total_amount: int
    discount_applied: bool

    @model_validator(mode = 'after')
    # 折扣和总价验证
    def check_amount(self):
        # 计算明细总价
        ttl_amount = sum(item.price * item.quantity for item in self.items)
        # 情况1：没有打折，总价和明细总和不等
        if not self.discount_applied and ttl_amount != self.total_amount:
            raise ValueError(f"未记录折扣，明细总和{ttl_amount}和订单总价{self.total_amount}不相等。")
        # 情况2：打折了，折后总价高于明细总和
        if self.discount_applied and ttl_amount < self.total_amount:
            raise ValueError(f"折扣后的订单总价{self.total_amount}高于明细总和{ttl_amount}")
        # 验证通过
        return self

    # 获取核心品牌数据
    def get_core_brand(self):
        core_items = [item for item in self.items if item.brand_name != BrandEnum.Other]
        core_revenue = sum(item.price * item.quantity for item in core_items)
        return {
            'core_items': core_items,
            'core_revenue': core_revenue
        }

def generate_with_reflection(system_prompt:str,user_text:str,response_model:Type[BaseModel],max_retries:int = 3):
    messages = [
        {'role': 'system','content': system_prompt},
        {'role': 'user','content':user_text}
        ]

    # 开始循环
    for attempt in range(max_retries):
        try: 
            print(f"正在进行第{attempt+1}次运行")
    
            response = Client.responses.parse(
                model = 'gpt-5.4-mini',
                input = messages,
                text_format = response_model
            )

            # 原生文本
            raw_string = response.output_text

            # 如果没有发生报错
            return response.output_parsed

        # 如果发生报错，将报错信息添加到上下文中
        # 1. 查看报错信息
        except ValidationError as e:
            errors_reason = e.errors()[0]['msg']
            print(f"第{attempt+1}次运行失败，报错原因：{errors_reason}。")

            # 2. 将提取后的文本添加到assistant
            messages.append({
                'role': 'assistant',
                'content': raw_string
            })
            # 3. 将报错原因添加到user
            messages.append({
                'role': 'user',
                'content':f"刚才生成的结果出现错误，报错原因是：{errors_reason}，请重新生成正确结果。"
            })
        
        # 4. 其他原因（API欠费，断网等）导致的错误，直接输出：
        except Exception as e:
            raise e 

    # 4. 如果三次循环都失败了，进行最终报错
    raise Exception('大模型重试了3次仍然失败，申请人工介入。')

order_text = '之前购买了雅诗兰黛的小棕瓶，原价750一瓶，买了两瓶，当时打了八折，我只花1200就买到了。没想到是临期货，用完烂脸爆痘！最近买了兰蔻的小黑瓶，花了800元，海蓝之谜的精华1590，这两款产品用下来效果修复还不错。'


# 业务场景
# 1. 提取订单信息
order_data = generate_with_reflection(
    system_prompt = '严格提取订单数据，认真对品牌进行归类。',
    user_text = order_text,
    response_model = BeautyOrder
)

print(f"---以下是原始订单数据---")
print(order_data)

print(f"---以下是核心品牌订单数据---")
print(order_data.get_core_brand())

# 2. 获取用户情绪
class UserSentiment(BaseModel):
    is_angry: bool
    reason: str 

sentiment_data = generate_with_reflection(
    system_prompt = '分析用户的情绪，对产品是否满意。',
    user_text = order_text, 
    response_model = UserSentiment
)

print(f"---以下是用户情绪---")
print(sentiment_data)










