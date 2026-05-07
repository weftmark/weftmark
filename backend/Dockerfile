FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# PyWeaving expects Arial.ttf in its data directory; substitute DejaVu Sans
RUN PYWEAVING_DATA=$(python -c "import pyweaving.render as r, os; print(os.path.join(os.path.dirname(r.__file__), 'data'))") && \
    mkdir -p "$PYWEAVING_DATA" && \
    cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf "$PYWEAVING_DATA/Arial.ttf"

COPY backend/ .
COPY VERSION .

RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# Drop to non-root — suppresses Celery SecurityWarning and follows least-privilege.
# chown covers /app/uploads so the named volume initialises with correct ownership.
RUN addgroup --system appuser && adduser --system --ingroup appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

ENTRYPOINT ["./entrypoint.sh"]
