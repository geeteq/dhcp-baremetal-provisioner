# Baremetal Automation Workers - Docker Image
FROM python:3.11-slim

LABEL maintainer="Baremetal Automation"
LABEL description="Event-driven baremetal server automation workers"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    lldpd \
    dmidecode \
    iproute2 \
    jq \
    ansible \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Copy requirements first (for layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create log directory
RUN mkdir -p /var/log/bm/metrics

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["all"]
