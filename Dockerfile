FROM python:3.14-alpine
COPY src/exporter.py /app/exporter.py
USER 65534:65534
ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 3000
ENTRYPOINT ["python3", "-u", "/app/exporter.py"]
