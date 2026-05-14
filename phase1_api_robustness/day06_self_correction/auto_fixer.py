import os
from dotenv import load_dotenv
from enum import Enum
from pydantic import BaseModel,model_validator,Field,ValidationError
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
    Other = '其他品牌' # 设置泄洪口

class OrderItem(BaseModel):
    # 强类型约束高于自然语言提示词
    brandname: BrandEnum= Field(description="品牌名称。如果文本中出现的品牌不在枚举列表中，必须严格选择'其他品牌'（例如娇韵诗等），必须严格选择'其他品牌'，绝对禁止强行归类到兰蔻或雅诗兰黛下！")
    product_name: str = Field(description = '订单中购买该品牌的产品名称')
    quantity: int = Field(default=1, description = '购买数量')
    price: int = Field(description = '单品折扣后的实际单价（不要计算总价，只算单价）')

class BeautyOrder(BaseModel):
    items: list[OrderItem]
    total_amount: int
    discount_applied: bool

    @model_validator(mode = 'after')
    def check_amount(self):
        # 原订单总价
        ttl_amount = sum(item.price * item.quantity for item in self.items)

        # 1. 没有打折且明细总价不等于订单总金额
        if not self.discount_applied and self.total_amount != ttl_amount:
            raise ValueError(f'未记录折扣，明细总和{ttl_amount}和总金额{self.total_amount}不相等')
       
        # 2. 打折，折后总价格应小于订单原价总价
        if self.discount_applied and self.total_amount > ttl_amount:
            raise ValueError(f'商品折后总金额{self.total_amount}比明细总和{ttl_amount}高')
        
        return self

    # 仅保留核心品牌
    def get_core_brand(self):
        core_items = [item for item in self.items if item.brandname != BrandEnum.Other]
        core_revenue = sum(item.price * item.quantity for item in core_items)
        return {
            'core_items': core_items,
            'core_revenue': core_revenue
        }

def extact_with_retry(user_text:str, max_retries:int = 3):
    # 1. 对话框初始化
    messages = [
        {'role': 'system', 'content': '严格按照schema提取订单信息，认真核对每一个品牌的归属。'},
        {'role': 'user', 'content': user_text}
    ]

    # 2. 循环
    for attempt in range(max_retries):
        try:
            print(f'---正在进行第{attempt+1}次尝试---')
            response = openai_client.responses.parse(
                model = 'gpt-5.4-mini',
                input = messages,
                text_format = BeautyOrder
            )

            # 如果结果没有报错，则带着正确结果跳出循环
            return response.output_parsed

        # 如果报错，则查看报错信息
        except ValidationError as e:
            errors_reason = e.errors()[0]['msg']
            print(f'第{attempt+1}次失败，报错原因：{errors_reason}。')

            # 将报错原因追加到上下文，进行再一次
            messages.append({
                'role': 'user',
                'content': f'刚才的输出出现错误，报错信息为{errors_reason}，请检查并重新输出正确的结果。'
            })

        # 其他原因（API欠费，断网等）导致的错误，直接输出：
        except Exception as e:
            raise e 

    # 如果三次循环都失败了，进行最终报错
    raise Exception('大模型重试了3次仍然失败，申请人工介入。')

# 订单信息
order_text = '昨天买了3瓶雅诗兰黛小棕瓶，单价600。今天又买了1瓶兰蔻小黑瓶，单价800，以及2瓶娇韵诗面霜，单价750。因为我是雅诗兰黛的高级会员，有8折优惠最后共付了3100元。'
# 抓取订单信息
exteactinfo = extact_with_retry(order_text)

print('---原始订单信息---')
print(exteactinfo)

print('---核心品牌信息---')
core_data = exteactinfo.get_core_brand()
print(f"核心品牌单品：{core_data['core_items']}")
print(f"核心品牌收入：{core_data['core_revenue']}")












