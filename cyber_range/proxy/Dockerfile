FROM python:3.12-alpine
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN addgroup -S range && adduser -S -G range range
WORKDIR /app
COPY proxy.py /app/proxy.py
USER range
ENTRYPOINT ["python", "/app/proxy.py"]
