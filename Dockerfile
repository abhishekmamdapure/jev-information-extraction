FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# libgomp1 provides libgomp.so.1, which onnxruntime's Linux wheel links
# against for OpenMP threading; it is not present in the slim base image.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY sample_questions.txt ./
COPY sample_pdf/ ./sample_pdf/

CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
