# Day90 application image
#
# Reproducibility policy:
# - Keep Python on the validated 3.10 compatibility line.
# - Use a maintained Debian base rather than the obsolete 3.10.3/buster image.
# - Application packages are installed from the fully pinned requirements-lock.txt.
#
# Byte-for-byte image reproducibility is NOT claimed here.
# A later release can pin the base-image digest after the Linux gate passes.

FROM python:3.10.20-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the frozen Python environment first so source-only changes
# can reuse Docker's dependency layer cache.
COPY requirements-lock.txt /app/requirements-lock.txt

RUN python -m pip install -r /app/requirements-lock.txt \
    && python -m pip check

# Do not run the application as root.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/runtime/audit \
    && chown -R appuser:appuser /app

# .dockerignore excludes secrets, virtualenvs, Git history,
# private learning docs and generated runtime artifacts.
COPY --chown=appuser:appuser . /app

USER appuser

EXPOSE 8501

CMD ["streamlit", "run", "app/ui/decision_console_app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
