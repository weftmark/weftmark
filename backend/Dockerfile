FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY backend/ .
COPY VERSION .
COPY docs/research/looms/loom-data-master.json seeds/
# Substitute DejaVu Sans for Arial in the vendored weaving engine
RUN cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf /app/app/weaving/data/Arial.ttf

RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# Create GeoLite2 data directory; optionally pre-populate at build time.
# Pass --build-arg MAXMIND_LICENSE_KEY=<key> to embed the MMDB in the image.
# Without the key the weekly refresh Celery task populates the file at runtime.
ARG MAXMIND_LICENSE_KEY=""
RUN mkdir -p /app/data && \
    if [ -n "$MAXMIND_LICENSE_KEY" ]; then \
        MMDB_KEY="$MAXMIND_LICENSE_KEY" python -c "\
import urllib.request, tarfile, tempfile, os, sys; \
k = os.environ['MMDB_KEY']; \
u = 'https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=' + k + '&suffix=tar.gz'; \
d = tempfile.mkdtemp(); \
urllib.request.urlretrieve(u, d + '/g.tar.gz'); \
t = tarfile.open(d + '/g.tar.gz'); \
ms = [m for m in t.getmembers() if m.name.endswith('GeoLite2-City.mmdb')]; \
(sys.exit(1) if not ms else (setattr(ms[0], 'name', 'GeoLite2-City.mmdb'), t.extract(ms[0], '/app/data')))" \
        || echo "GeoLite2-City download failed — runtime task will retry"; \
    fi

# Drop to non-root — suppresses Celery SecurityWarning and follows least-privilege.
# chown covers /app/uploads and /app/data so the weekly geo task can write the MMDB.
RUN addgroup --system appuser && adduser --system --ingroup appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

ENTRYPOINT ["./entrypoint.sh"]
