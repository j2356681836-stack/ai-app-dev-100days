# Day90 应用镜像
#
# 可复现性策略：
# - Python 保持在已验证的 3.10 兼容线。
# - 使用仍在维护的 Debian 基础镜像，而不是过时的 3.10.3/buster。
# - Python 应用依赖严格从 requirements-lock.txt 安装。
#
# 当前不声称镜像具备 byte-for-byte 可复现性。
# 后续正式发布时，可以在 Linux Gate 通过后进一步固定 base image digest。
#
# Day92 Cloud Runtime：
# - 本地 Docker 默认仍使用 8501。
# - 云端 Web Service 可以通过 PORT 覆盖运行端口。
# - 应用继续绑定 0.0.0.0，允许容器外部访问。
# - PYTHONPATH=/app 固化进镜像，避免依赖 Docker Compose 才能导入顶层 app 包。

FROM python:3.10.20-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# 先安装冻结后的 Python 依赖，
# 这样仅修改源码时可以复用 Docker 的 dependency layer cache。
COPY requirements-lock.txt /app/requirements-lock.txt

RUN python -m pip install -r /app/requirements-lock.txt \
    && python -m pip check

# 应用运行时不使用 root 用户。
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/runtime/audit \
    && chown -R appuser:appuser /app

# .dockerignore 会排除真实 secret、本地虚拟环境、Git 历史、
# 私有学习文档和运行时生成文件。
COPY --chown=appuser:appuser . /app

USER appuser

# 本地 Docker / Compose 默认使用 8501。
# Render 会把流量转发到实际运行时 PORT，
# 因此 EXPOSE 这里只是镜像说明，不是云端路由合同。
EXPOSE 8501

# 这里有意通过 shell 展开 ${PORT:-8501}：
# - 本地 Docker / Compose：PORT 不存在 → 使用 8501
# - Render Web Service：平台注入 PORT → 使用云端运行端口
CMD ["sh", "-c", "exec streamlit run app/ui/decision_console_app.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --server.headless=true --browser.gatherUsageStats=false"]
