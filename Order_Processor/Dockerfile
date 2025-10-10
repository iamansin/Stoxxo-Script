# =============================
# Dockerfile for Stoxxo Script
# =============================

FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy dependency list
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Create log directory
RUN mkdir -p /app/logs_folder
# Set permissions
RUN chmod -R 755 /app/logs_folder

# Copy rest of the app code
COPY . .

# Default command
# You can override config path at runtime via `docker run ... <path>`
CMD ["python", "Order_Processor/app.py"]
