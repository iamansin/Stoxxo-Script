# =============================
# Dockerfile for Stoxxo Script
# =============================

FROM python:3.11-slim

# Set working directory
WORKDIR /Order_Processor

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy the rest of the source code
COPY . .

# Create a logs folder (default inside container)
RUN mkdir -p /Order_Processor/logs_folder && chmod -R 755 /Order_Processor/logs_folder

# Default entrypoint
# Config path will be passed at runtime
ENTRYPOINT ["python", "app.py"]
