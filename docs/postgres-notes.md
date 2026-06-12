| 命令      | 作用    |
| ------- | ----- |
| `\q`    | 退出    |
| `\dt`   | 查看表   |
| `\d 表名` | 查看表结构 |
| `\l`    | 查看数据库 |
| `\du`   | 查看用户  |

`\pset pager off` 关闭分页器


`GREATEST(start1, start2)` 返回多个值中的最大值
`LEAST(end1, end2)` 返回多个值中的最小值

应用：
这是所有时间窗口求交集的标准公式。

`
SELECT
    GREATEST(startA, startB) AS overlap_start,
    LEAST(endA, endB) AS overlap_end;
`
