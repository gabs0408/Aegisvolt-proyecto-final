FROM python:3.12-slim

WORKDIR /app
COPY saga-auditor-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY saga-auditor-service/app ./app
COPY shared ./shared

CMD ["python", "-m", "app.flows.audit_sagas"]
