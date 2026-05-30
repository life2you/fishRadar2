FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends libzbar0 tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-runtime.txt ./requirements-runtime.txt
RUN pip install --no-cache-dir -r requirements-runtime.txt

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python3", "tools/worker_job_runner.py"]
