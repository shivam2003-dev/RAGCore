# --- build stage: resolve and install dependencies into a venv ---
FROM python:3.13-slim AS build

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /venv
COPY pyproject.toml ./
# install deps from project metadata (source copied next; editable not needed in image)
RUN /venv/bin/pip install .  || true
COPY . .
RUN /venv/bin/pip install .

# --- runtime stage ---
FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r kimbal && useradd -r -g kimbal kimbal
WORKDIR /app
ENV PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1 APP_ENV=production

COPY --from=build /venv /venv
COPY --from=build /app /app
RUN mkdir -p /app/var/uploads && chown -R kimbal:kimbal /app/var

USER kimbal
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
