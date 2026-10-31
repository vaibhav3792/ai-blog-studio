# One container: builds the React app, then serves it and the API from a single FastAPI process.
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
# Hugging Face Spaces runs containers as UID 1000.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/home/user/data \
    FRONTEND_DIST=/home/user/app/static
RUN mkdir -p /home/user/data
WORKDIR /home/user/app
COPY --chown=user backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY --chown=user backend/app ./app
COPY --chown=user --from=web /web/dist ./static
EXPOSE 7860
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
