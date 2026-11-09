# Build the landing page, then serve it + the API from one container.
FROM node:20-alpine AS web
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html agent.html vite.config.js ./
COPY src ./src
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY landed ./landed
COPY api ./api
COPY data ./data
COPY --from=web /app/dist ./dist
# Accounts live in a SQLite file: mount a volume so they survive redeploys:
#   docker run -v landed-db:/app/db ...
RUN mkdir -p /app/db && chmod 777 /app/db
ENV LANDED_DB=/app/db/landed.sqlite3
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
