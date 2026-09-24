FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./app.py

RUN useradd --create-home --uid 10001 range \
    && mkdir -p /state /snapshots /evidence \
    && chown -R range:range /app /state /snapshots /evidence
USER range

EXPOSE 7070
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7070"]
