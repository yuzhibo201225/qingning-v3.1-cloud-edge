FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py analytics.py ai_engine.py ./
COPY static/ static/
CMD ["gunicorn", "-w", "1", "--threads", "4", "--timeout", "40", "--bind", "0.0.0.0:8000", "app:app"]
