# Failure Log

## 2026-07-16

### 问题
Pydantic ValidationError

### 原因
LLM 输出 markdown code block

### 解决
field_validator 清洗 markdown fence

---

### 问题
429 Retry Storm

### 原因
asyncio 并发过高

### 解决
Semaphore 限制并发