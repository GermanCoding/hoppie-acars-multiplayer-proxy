FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir fastapi[standard] && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port the app runs on
EXPOSE 8000

ENV HOPPIE_LOGON=""
ENV ALLOWED_LOGONS=""
ENV HOPPIE_UPSTREAM="https://www.hoppie.nl/acars/system/connect.html"

# Command to run the application
CMD ["fastapi", "run"]
