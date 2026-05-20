# 异步读取测试

import asyncio
import aiofiles
import json 

async def main():
    # 计算兰蔻的商品数量
    lancome_total_quantity = 0

    # 异步打开文件
    async with aiofiles.open("day10_output_v3.jsonl",mode="r",encoding = "utf-8") as f:
        # 逐行迭代
        async for line in f:
            # 将每一行Json字符串反序列化成Python字典
            data = json.loads(line.strip())

            # 进入字典，遍历items列表
            items = data.get("order_info",{}).get("items",[])
            for item in items:
                if item.get("brand_name") == "兰蔻":
                    lancome_total_quantity += item.get("quantity",0)

    print(f"全量数据解析完毕，兰蔻商品总销量为：{lancome_total_quantity}件")
    
if __name__ == "__main__":
    asyncio.run(main())


