FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
# Dependencies first, so a source change does not re-resolve them.
COPY pyproject.toml .
RUN pip install --no-cache-dir "pip>=23.0" && pip install --no-cache-dir .
COPY . .
# The install above ran before the source existed, so it brought the dependencies and the
# console scripts but not the package itself. uvicorn does not notice — it puts the working
# directory on the path — but a console script does not, so seed-universes, create-db and
# restore-creator all failed with "No module named 'app'". This installs the package now that
# the source is here; the dependencies are already resolved, so it stays a cheap layer.
RUN pip install --no-cache-dir --no-deps .
# The workspace capability keeps each Mission's files here. Creating it in the image with the
# right owner means a fresh named volume inherits that ownership and the non-root user can write.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/lib/creation/workspaces \
    && chown -R appuser:appuser /app /var/lib/creation
USER appuser
