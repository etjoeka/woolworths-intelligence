# Woolworths Intelligence — container build for PaaS hosting (Render / Railway / Fly / etc.)
# Ships with the pre-scraped SQLite snapshot so no browser/scraping is needed on the host.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bind to 0.0.0.0 and honour the platform-injected PORT (defaults to 8777).
ENV HOST=0.0.0.0
EXPOSE 8777

CMD ["sh", "-c", "python run.py dashboard --host 0.0.0.0 --port ${PORT:-8777}"]
