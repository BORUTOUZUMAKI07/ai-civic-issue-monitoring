FROM python:3.12-slim

WORKDIR /opt/civicpulse

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY flows/ ./flows/
ENV PYTHONPATH=/opt/civicpulse/flows

# For managed serverless: Prefect injects the flow entrypoint.
# For local worker: uncomment the line below and comment the one above.
# ENTRYPOINT ["prefect", "worker", "start", "--pool", "civicpulse-local"]