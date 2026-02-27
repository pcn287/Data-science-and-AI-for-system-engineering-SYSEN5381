# Homework 1: AI-Powered Methane Emissions Reporter
# For deployment on DigitalOcean App Platform

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY main_app.py .

# Expose port (DigitalOcean may override via PORT env)
EXPOSE 8000

# Bind to 0.0.0.0 so the app is reachable from outside the container
# Use PORT env var if set (e.g. DigitalOcean), else 8000
CMD ["sh", "-c", "python -m shiny run main_app.py --host 0.0.0.0 --port ${PORT:-8000}"]
