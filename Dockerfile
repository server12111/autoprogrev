FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create persistent data directory
RUN mkdir -p /data/sessions /data/logs

# Run bot
CMD ["python", "main.py"]
