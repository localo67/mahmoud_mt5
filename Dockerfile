FROM python:3.11-slim

WORKDIR /app
ENV TRADING_MODE=off

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application
COPY . .

# Lecture seule : MetaTrader5 n'est pas installe dans cette image Linux.
CMD ["python", "bot.py"]
