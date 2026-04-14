FROM python:3.12-slim

WORKDIR /app

ENV TZ=Asia/Kolkata

# Install system dependencies if any are needed
RUN apt-get update && apt-get install -y \
    tzdata \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port FastAPI runs on
EXPOSE 8557

# Command to run the application
# Use --host 0.0.0.0 to allow access from outside the container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8557"]
