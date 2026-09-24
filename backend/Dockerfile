FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY pyproject.toml .
RUN pip install --no-cache-dir "pip>=23.0" && pip install --no-cache-dir .
COPY . .
# The workspace capability keeps each Mission's files here. Creating it in the image with the
# right owner means a fresh named volume inherits that ownership and the non-root user can write.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/lib/creation/workspaces \
    && chown -R appuser:appuser /app /var/lib/creation
USER appuser
