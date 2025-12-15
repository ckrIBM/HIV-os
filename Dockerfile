FROM python:3.11-slim

WORKDIR /app

# Copiar archivos de dependencias
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY mainv2.py .

# Exponer puerto
EXPOSE 8080

# Comando para ejecutar la aplicación
CMD ["uvicorn", "mainv2:app", "--host", "0.0.0.0", "--port", "8080"]


