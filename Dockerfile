FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py webapp.py worker.py sms_sandbox.py sms_production_test.py gunicorn.conf.py ./
COPY public ./public
CMD ["gunicorn", "--config", "gunicorn.conf.py", "webapp:create_app()"]
