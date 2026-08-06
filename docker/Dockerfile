FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# fonts-dejavu-core : requis par tools/pdf.py (chemins en dur)
# libreoffice-writer : conversions bureautiques
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        libreoffice-writer && \
    rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && \
    adduser --system --ingroup app --home /home/app app

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

COPY . .

# LibreOffice a besoin d'un HOME inscriptible pour son profil
ENV HOME=/home/app

# app doit pouvoir écrire dans data/, logs/ et temp/
RUN chown -R app:app /app /home/app

USER app

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8001), 3).close()"

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
