FROM python:3.12-slim

WORKDIR /app

COPY . /app

ENV HOST=0.0.0.0
ENV PORT=8080
ENV APP_DB_PATH=/app/data/app.db

EXPOSE 8080

CMD ["python", "-m", "ai_test_platform.server"]

