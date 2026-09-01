FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    curl \
    unzip \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY app.py .

EXPOSE 10000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]
