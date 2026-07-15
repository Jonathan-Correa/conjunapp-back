# ConjunApp Backend (API)

API REST de la plataforma ConjunApp (conjuntos residenciales).

## Stack

- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy 2 + PostgreSQL
- JWT (admin / residente)

## Requisitos

- Python 3.12+
- PostgreSQL 16 (o Docker)

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger: http://localhost:8000/docs

## Variables de entorno

Ver `.env.example` y [docs/VariablesEntorno.md](../docs/VariablesEntorno.md).

## Docker

Desde la raíz del monorepo:

```bash
docker compose up --build back db
```

## Credenciales demo (seed)

| Rol | Email | Password |
|-----|-------|----------|
| Admin | admin@conjunapp.com | admin123 |
| Residente | ana@example.com | residente123 |

## Documentación

Documentación completa: [../docs/Backend.md](../docs/Backend.md)
