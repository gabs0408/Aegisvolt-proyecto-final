FROM python:3.12-slim

WORKDIR /app
COPY saga-orchestrator-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY saga-orchestrator-service/app ./app
COPY shared ./shared

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
