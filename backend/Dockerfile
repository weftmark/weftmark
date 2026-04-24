FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# PyWeaving expects Arial.ttf in its data directory; substitute DejaVu Sans
RUN PYWEAVING_DATA=$(python -c "import pyweaving.render as r, os; print(os.path.join(os.path.dirname(r.__file__), 'data'))") && \
    mkdir -p "$PYWEAVING_DATA" && \
    cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf "$PYWEAVING_DATA/Arial.ttf"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
