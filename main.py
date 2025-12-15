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

class Receta(BaseModel):
    Troquel: str
    Codigo: str
    monodroga: str
    descripcion: str

class TicketRecetasResponse(BaseModel):
    id_socio: str
    ticket_id: str
    recetas: list[Receta]

class HIVCheckResponse(BaseModel):
    presentacion: str
    es_hiv: bool

class SustitucionResponse(BaseModel):
    troquel: str
    codigo_original: str
    es_sustituible: bool
    mensaje: str
    codigo_sustituto: Optional[str] = None


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


# Mock de Recetas por Ticket
# Estructura: Ticket ID -> { Socio ID, Lista de Recetas }
MOCK_RECETAS_DB = {
    # CASO 1: HIV Positivo (Una receta con medicamento HIV)
    "1000073123": {
        "socio": "61134592601",
        "recetas": [
            {
                "Troquel": "45282",
                "Codigo": "18000",
                "monodroga": "ABACAVIR/LAMIVUDINA",
                "descripcion": "ABACAVIR/LAMIVUDINA 600/300 MG"
            }
        ]
    },
    # CASO 2: HIV Positivo - RENOVACION
    "1000073124": {
        "socio": "62245693702",
        "recetas": [
            {
                "Troquel": "18001",
                "Codigo": "18001",
                "monodroga": "EFAVIRENZ",
                "descripcion": "EFAVIRENZ 600 MG"
            }
        ]
    },
    # CASO 3: HIV Negativo (Una receta con medicamento NO HIV)
    "1000073125": {
        "socio": "63356704803",
        "recetas": [
            {
                "Troquel": "2039",
                "Codigo": "3002",
                "monodroga": "IBUPROFENO",
                "descripcion": "IBUPROFENO 400 MG"
            }
        ]
    },
    # CASO 4: Renovación con Sustitución (Ejemplo nuevo)
    "1000073199": {
        "socio": "62245693702", # Mismo socio que Renovación (Roberto)
        "recetas": [
            {
                "Troquel": "21955", 
                "Codigo": "21955",
                "monodroga": "3 TC COMPLEX",
                "descripcion": "3 TC COMPLEX 600 MG"
            }
        ]
    }
}


@app.get("/obtener_recetas_ticket", response_model=TicketRecetasResponse)
async def obtener_recetas_ticket(
    id: str = Query(..., description="ID del ticket (Trámite)"),
    socio: str = Query(..., description="Número de socio")
):
    """
    Obtiene las recetas asociadas a un ticket específico.
    Simula la búsqueda de recetas en el sistema core.
    """
    # 1. Buscar el ticket
    if id not in MOCK_RECETAS_DB:
        raise HTTPException(status_code=404, detail=f"Ticket {id} no encontrado")
    
    ticket_data = MOCK_RECETAS_DB[id]
    
    # 2. Validar socio (Simulación de seguridad/consistencia)
    # Nota: En el mock, validamos que el socio coincida con el dato guardado
    # Se puede relajar esta validación si el socio viene con formato distinto (ej guiones)
    if ticket_data["socio"] not in socio: 
         raise HTTPException(status_code=400, detail="El número de socio no coincide con el ticket")

    # 3. Retornar respuesta
    return TicketRecetasResponse(
        id_socio=socio,
        ticket_id=id,
        recetas=[Receta(**r) for r in ticket_data["recetas"]]
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
    # Bypass Mock para caso sustitución
    if presentacion == "23523":
        return HIVCheckResponse(presentacion=presentacion, es_hiv=True)

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

@app.get("/identificacion_ciclo")
def identificacion_ciclo(
    troquel: str = Query(..., description="Troquel del medicamento"),
    socio_id: str = Query(..., description="ID del socio")
):
    """
    Determina el ciclo del tratamiento basado en socio y troquel:
    - Inicio de tratamiento
    - Renovación
    - Cambio de tratamiento
    """
    # Mock hardcodeado según reglas de negocio
    # Caso 1: Inicio (Abacavir / Socio Carolina)
    if troquel == "45282" and socio_id == "61134592601":
        return {"ciclo": "Inicio de tratamiento", "codigo": 1}
    
    # Caso 2: Renovación (Efavirenz / Socio Roberto)
    elif troquel == "18001" and socio_id == "62245693702": 
        return {"ciclo": "Renovación", "codigo": 2}

    # Caso 3: Renovación con Sustitución (Nuevo caso mock)
    elif troquel == "23523" and socio_id == "62245693702":
        return {"ciclo": "Renovación", "codigo": 2}
    
    # Otros casos
    else:
        return {"ciclo": "Indeterminado", "codigo": 3}

@app.get("/agente_sustitutor", response_model=SustitucionResponse)
def agente_sustitutor(
    troquel: str = Query(..., description="Código de troquel del medicamento"),
    username: str = Depends(check_basic_auth)
):
    """
    Verifica si un medicamento es sustituible por otro según la tabla de sustitución HIV.
    
    - Si sustituye = 1: El medicamento es sustituible, retorna el código sustituto
    - Si sustituye = 0: El medicamento no es sustituible
    """
    sql = """
        SELECT "codigo", "sustituye", "codigoSustituible"
        FROM public."tablasustitucion_hiv"
        WHERE "codigo" = %s;
    """
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (troquel,))
                row = cur.fetchone()
                
                if not row:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Troquel '{troquel}' no encontrado en la tabla de sustitución"
                    )
                
                codigo_original, sustituye, codigo_sustituible = row
                
                if sustituye == 1:
                    return SustitucionResponse(
                        troquel=troquel,
                        codigo_original=codigo_original,
                        es_sustituible=True,
                        mensaje=f"El medicamento es sustituible. Código original '{codigo_original}' se sustituye por '{codigo_sustituible}'",
                        codigo_sustituto=codigo_sustituible
                    )
                else:
                    return SustitucionResponse(
                        troquel=troquel,
                        codigo_original=codigo_original,
                        es_sustituible=False,
                        mensaje=f"El medicamento con código '{codigo_original}' no es sustituible"
                    )
                    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando base de datos: {e}")


@app.get("/")
def root():
    return {"endpoints": ["/obtener_recetas_ticket", "/hiv/check", "/identificacion_ciclo", "/agente_sustitutor"]}



@app.get("/health")
def health():
    """Health check para Code Engine"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
