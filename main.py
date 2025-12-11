from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="PoC Watsonx Orchestrate - Endpoints",
    version="1.0.0",
    description="API para endpoints de OSDE HIV - Orchestrate"
)

security = HTTPBasic()

# Credenciales de la API (Basic Auth HTTP)
API_USERNAME = os.getenv("API_USERNAME", "admin")
API_PASSWORD = os.getenv("API_PASSWORD", "adminpass")

# Datos de la base (IBM Cloud PostgreSQL)
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_SSLMODE = os.getenv("DB_SSLMODE", "require")


class Ticket(BaseModel):
    ObjectID: str
    Filial: str
    Socio: str
    ID: str
    FechaEntrada: datetime


class Coding(BaseModel):
    system: str
    code: str


class Code(BaseModel):
    coding: list[Coding]
    text: str


class Troquel(BaseModel):
    code: Code


class HIVCheckResponse(BaseModel):
    presentacion: str
    es_hiv: bool


# Funciones auxiliares
def get_conn():
    """Conexión a PostgreSQL"""
    if not all([DB_HOST, DB_NAME, DB_USER, DB_PASS]):
        raise RuntimeError("Faltan variables de entorno de base de datos")
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        sslmode=DB_SSLMODE,
    )


def check_basic_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """Validación de Basic Auth"""
    if credentials.username != API_USERNAME or credentials.password != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    return credentials.username


# Mock estático
FIXED_TICKET = Ticket(
    ObjectID="1269035B88971FD0A4EC29358D190ED9",
    Filial="60",
    Socio="61134592601 - CAROLINA",
    ID="1000073123",
    FechaEntrada=datetime.fromisoformat("2025-09-16T21:57:32"),
)


@app.get("/GetFristTicket", response_model=Ticket)
def get_first_ticket():
    return FIXED_TICKET


@app.get("/GetTroquel", response_model=Troquel)
async def get_troquel(
    id: str = Query(..., description="ID del ticket"),
    socio: str = Query(..., description="Número de socio")
):
    """
    Busca el troquel (medicamento) en PostgreSQL según ID y Socio.
    Por ahora devuelve datos mock. Conexión a DB lista para implementar.
    """
    # TODO: Conectar a PostgreSQL cuando esté disponible
    # db_host = os.getenv("POSTGRES_HOST")
    # db_user = os.getenv("POSTGRES_USER")
    # db_password = os.getenv("POSTGRES_PASSWORD")
    # db_name = os.getenv("POSTGRES_DB")
    
    # Mock response
    return Troquel(
        code=Code(
            coding=[
                Coding(
                    system="https://www.osde.com.ar/troquel",
                    code="9930127"
                )
            ],
            text="ACTRON caps.gelat.blanda x 10"
        )
    )


@app.get("/hiv/check", response_model=HIVCheckResponse)
def check_hiv_medication(
    presentacion: str,
    username: str = Depends(check_basic_auth)
):
    """
    Verifica si una presentación corresponde a un medicamento HIV.
    presentacion: el valor que se consulta en "Presentacion" (ej: '18000')
    """
    sql = """
        SELECT EXISTS (
            SELECT 1
            FROM public."medicamentos_HIV.csv"
            WHERE "Presentacion" = %s
        ) AS es_hiv;
    """

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (presentacion,))
                row = cur.fetchone()
                es_hiv = row[0] if row else False
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando base: {e}")

    return HIVCheckResponse(
        presentacion=presentacion,
        es_hiv=bool(es_hiv)
    )


@app.get("/")
def root():
    return {"endpoints": ["/GetFristTicket", "/GetTroquel", "/hiv/check"]}


@app.get("/health")
def health():
    """Health check para Code Engine"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
