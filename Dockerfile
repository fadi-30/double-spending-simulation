# 1. Startpunkt: Wir nehmen ein offizielles, schlankes Python-Betriebssystem
FROM python:3.10-slim

# NEU: Schaltet den Text-Zwischenspeicher ab, damit print() sofort erscheint
ENV PYTHONUNBUFFERED=1

# 2. Arbeitsordner IM Container festlegen
WORKDIR /app

# 3. Kopiere alle Dateien aus deinem PC-Ordner in den Container-Ordner
COPY . .

# 3.5 Installiere externe Bibliotheken
RUN pip install cryptography flask requests

# 4. Der Befehl, der ausgeführt wird, sobald der Container startet
CMD ["python", "Miner.py"]