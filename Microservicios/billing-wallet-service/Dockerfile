FROM python:3.12-slim

WORKDIR /app
COPY billing-wallet-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY billing-wallet-service/app ./app
COPY shared ./shared

RUN mkdir -p /data
ENV DATABASE_PATH=/data/wallet.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
