FROM python:3.11-slim

# Install PostgreSQL client libraries
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Add networking tools for demo and debugging
RUN apt update

RUN apt install -y net-tools
RUN apt install -y inetutils-tools
RUN apt install -y inetutils-traceroute
RUN apt install -y net-tools
RUN apt install -y netcat-traditional
RUN apt install -y vim
#


# Create app directory
RUN mkdir -p /app

# Copy application files
COPY ./app/ /app/
COPY ./requirements.txt /app/requirements.txt

# "Ping" address/port with NC utility:
COPY  ./utils/ncping /usr/bin/ncping
RUN chmod +x /usr/bin/ncping

# Set working directory
WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8080

# Run the application with Gunicorn
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "--timeout", "120", "app:app"]
