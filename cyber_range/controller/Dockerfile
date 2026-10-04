FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then \
      PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi
COPY app.py ./app.py

RUN useradd --create-home --uid 10001 range \
    && mkdir -p /state /campaign-state /snapshots /evidence \
    && chown -R range:range /app /state /campaign-state /snapshots /evidence
USER range

EXPOSE 7070
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7070"]
