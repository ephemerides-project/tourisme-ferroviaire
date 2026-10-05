# Image de l'API. À construire depuis la racine du projet (voir docker-compose.yml).
FROM python:3.12-slim

WORKDIR /projet/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY db/ /projet/db/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
