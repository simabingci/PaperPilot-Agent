ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /app
COPY pyproject.toml requirements.lock ./
RUN PIP_EXTRA_INDEX_URL= pip install --no-cache-dir --index-url "$PIP_INDEX_URL" uv==0.13.6 && \
    uv pip install --system --no-cache --index "$PIP_INDEX_URL" \
    --default-index "$PIP_EXTRA_INDEX_URL" --index-strategy unsafe-first-match -r requirements.lock && \
    pip uninstall -y uv
COPY paperpilot ./paperpilot
COPY .streamlit ./.streamlit
COPY README.md LICENSE ./
RUN useradd -m -u 10001 pilot && mkdir /app/data && chown pilot /app/data
USER pilot
EXPOSE 8000 8501
CMD ["python", "-m", "uvicorn", "paperpilot.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
