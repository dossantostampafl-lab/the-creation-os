FROM python:3.12-alpine
RUN addgroup -S range && adduser -S -G range range
WORKDIR /app
COPY proxy.py /app/proxy.py
USER range
ENTRYPOINT ["python", "/app/proxy.py"]
