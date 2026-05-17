import os
import sys
import time
import asyncio # 引入Python原生的异步库
from dotenv import load_dotenv
from openai import AsyncOpenAI
from enum import Enum
from typing import Type
from pydantic import BaseModel,ValidationError,Field,model_validator
from tenacity import retry,wait_exponential,stop_after_attempt


# 加载环境
load_dotenv()

# 彻底解决 Windows 环境下的 Event loop is closed 幽灵报错
# 再win系统上运行，把底层的异步发动机从默认的V8降级成V6
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 验证
client = AsyncOpenAI(
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

class UserSentiment(BaseModel):
    is_angry: bool
    reason: str 

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

# Tenacity装饰器：如果遇上问题，等待2-10秒重试，最多重试5次
@retry (wait = wait_exponential(multiplier=1,min=2,max=10),stop = stop_after_attempt(5))
async def generate_with_reflection(
    system_prompt:str,
    user_text:str,
    response_model:Type[BaseModel],
    sem:asyncio.Semaphore, 
    max_retries:int = 3     # 带有默认值的参数必须放在所有没有默认值的参数后面
):

    messages = [
        {'role': 'system','content': system_prompt},
        {'role': 'user','content':user_text}
        ]

    # 任务编码
    task_id = f"[{response_model.__name__} | {user_text[:6]}...]"

    # 开始循环
    for attempt in range(max_retries):
        try: 
            # 日志分级
            if attempt == 0:
                print(f"{task_id}开始第1次解析...")
            else:
                print(f"⚠️ {task_id} 正在基于反思进行第{attempt+1}次重试...")

            # 包裹发起网络请求的代码，排队检查是否有位置
            async with sem:
                response = await client.responses.parse(
                    model = 'gpt-5.4-mini',
                    input = messages,
                    text_format = response_model
                )

                # 原生文本
                raw_string = response.output_text

                # 【优化点3】成功时给一个明确的绿灯反馈
                if attempt > 0:
                    print(f"{task_id} 第{attempt+1}次重试成功！")

                return response.output_parsed

        # 如果发生报错，将报错信息添加到上下文中
        # 1. 查看报错信息
        except ValidationError as e:
            errors_reason = e.errors()[0]['msg']

            print(f"{task_id} 第{attempt+1}次运行失败，报错原因：{errors_reason}。")

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
            print(f"{task_id} 触发底层网络异常: {e}，交由 Tenacity 退避重试。")
            raise e 

    # 4. 如果三次循环都失败了，进行最终报错
    raise Exception('大模型重试了3次仍然失败，申请人工介入。')

order_texts = [
    "之前购买了雅诗兰黛的小棕瓶，原价750一瓶，买了两瓶，当时打了八折，我只花1200就买到了。没想到是临期货，用完烂脸爆痘！最近买了兰蔻的小黑瓶，花了800元，海蓝之谜的精华1590，这两款产品用下来效果修复还不错。",
    "买了三瓶娇兰面霜，一瓶720，打完折一共1800元，效果还不错。",
    "我买了一瓶SK-II的神仙水，1200元，用下来面部没那么油了。",
    "昨天是兰蔻的VVIP活动，我买了两瓶黑金面霜，单价是3250，活动打折只花了5800元。",
    "买了一瓶欧莱雅的洗面奶，120元，很难用。",
    "之前购买了雅诗兰黛的小棕瓶，原价750一瓶，买了两瓶，当时打了八折，我只花1200就买到了。没想到是临期货，用完烂脸爆痘！最近买了兰蔻的小黑瓶，花了800元，海蓝之谜的精华1590，这两款产品用下来效果修复还不错。",
    "买了三瓶娇兰面霜，一瓶720，打完折一共1800元，效果还不错。",
    "我买了一瓶SK-II的神仙水，1200元，用下来面部没那么油了。",
    "昨天是兰蔻的VVIP活动，我买了两瓶黑金面霜，单价是3250，活动打折只花了5800元。",
    "买了一瓶欧莱雅的洗面奶，120元，很难用。"
    ]

    
# 异步代码控制台
async def main():
    print(f"---异步并发测速启动，共{len(order_texts)}条数据，生成{len(order_texts)*2}个并发任务 ---")
    start_time= time.time()

    # 设置并发上限
    global_sem = asyncio.Semaphore(10)

    order_tasks = []
    sentiment_tasks = []
    
    for text in order_texts:
        task1 = generate_with_reflection(
            system_prompt = '严格提取订单数据，认真对品牌进行归类。',
            user_text = text,
            response_model = BeautyOrder,
            sem = global_sem
        )
        order_tasks.append(task1)

    for text in order_texts:
        task2 = generate_with_reflection(
            system_prompt = '分析用户的情绪，对产品是否满意。',
            user_text = text,
            response_model = UserSentiment,
            sem = global_sem
        )
        sentiment_tasks.append(task2)


    print("所有任务同时启动！")
    orders, sentiments = await asyncio.gather(
        asyncio.gather(*order_tasks),
        asyncio.gather(*sentiment_tasks)
    )

    end_time = time.time() # 记录结束时间

    print("\n--- 结果汇报 ---")
    for i in range(len(order_texts)):
        print(f"\n 任务{i+1}：")
        print(f"所有订单数据：{orders[i]}")
        print(f"核心订单数据：{orders[i].get_core_brand()}")
        print(f"情绪分析结果：{sentiments[i]}")

    print(f"\n API 请求总耗时: {end_time - start_time:.2f} 秒")

if __name__ == "__main__":
    # 启动
    asyncio.run(main())