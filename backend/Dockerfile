FROM python:3.11-slim

WORKDIR /app

# System deps (bcrypt build etc.)
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# The extra index provides the internal 'emergentintegrations' package (unused at runtime,
# kept only for parity with the dev environment).
RUN pip install --no-cache-dir --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ -r requirements.txt

COPY . .

EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
