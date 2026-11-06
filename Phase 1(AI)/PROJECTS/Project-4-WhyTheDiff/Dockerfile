FROM node:24-bookworm-slim@sha256:6042915a8b58012e6699f998ed96bca43ec9d8582447bdb68bc2445d0fafeb79 AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim-bookworm@sha256:516b51cb9db2ef061e465c803e50f64361b82cefd91e525b889b967b83e83527
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATA_DIR=/state/data REPORTS_DIR=/state/reports PUBLIC_APP=true \
    HF_HOME=/state/.cache/huggingface XDG_CACHE_HOME=/state/.cache
WORKDIR /app
COPY requirements-linux.lock ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-linux.lock \
    && useradd --uid 10001 --create-home whythediff \
    && mkdir -p /state/data /state/reports /state/.cache \
    && chown -R whythediff:whythediff /state
ARG RUNTIME_UID=10001
# Keep the verified dependency layer reusable for the Spaces UID 1000 build.
RUN if [ "${RUNTIME_UID}" != "10001" ]; then \
      usermod --uid "${RUNTIME_UID}" whythediff \
      && chown -R whythediff:whythediff /state /home/whythediff; \
    fi
COPY --chown=whythediff:whythediff . .
COPY --from=frontend --chown=whythediff:whythediff /build/dist ./frontend/dist
USER whythediff
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import os,urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/health',headers={'Host':__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(os.environ['APP_ORIGIN']).netloc}); urllib.request.urlopen(r,timeout=3)"
CMD ["python", "scripts/start_server.py"]
