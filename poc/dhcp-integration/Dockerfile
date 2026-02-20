FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy worker script and utilities
COPY netbox-bmc-worker.py .
COPY netbox_utils.py .

# Create log directory
RUN mkdir -p /var/log && chmod 777 /var/log

# Run worker
CMD ["python", "-u", "netbox-bmc-worker.py"]
