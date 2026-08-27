FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV APP_VERSION=v1.0.0
ENV APP_COLOR=#4F46E5
ENV APP_COLOR_NAME=indigo
ENV DB_HOST=mysql
ENV DB_PORT=3306
ENV DB_USER=todo
ENV DB_NAME=tododb

EXPOSE 5000

# -w 2 is safe now: state lives in MySQL, not in-process memory, so multiple
# workers (and multiple Pod replicas) no longer cause the create/delete
# consistency bugs seen with the earlier in-memory version.
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "--access-logfile", "-", "app:app"]
