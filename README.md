# 🏢 Argenprop Salta Scraper

Scraper independiente de propiedades de **Argenprop** para Salta y región NOA.  
Obtiene propiedades estructuradas con soporte para modo directo (`https://www.argenprop.com/inmuebles/alquiler-o-venta/salta-arg`) y modo catálogo completo (segmentación adaptativa) para superar el tope de 10 páginas (~200 avisos) de Argenprop y cubrir las **~3.500+ propiedades** de la provincia.

---

## Quick Start

```bash
# 1. Iniciar PostgreSQL local (puerto 5434)
docker compose up -d

# 2. Instalar dependencias en el entorno virtual
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 3. Configurar entorno y aplicar migraciones
cp .env.example .env
alembic upgrade head

# 4. Scrape inicial de prueba
python -m src.cli scrape --limit 40

# 5. Enriquecer fichas con GPS y teléfono
python -m src.cli enrich --limit 40

# 6. Abrir visor interactivo Streamlit
streamlit run app.py
```

---

## Arquitectura

| Componente | Tecnología | Función |
|---|---|---|
| **curl_cffi** | TLS impersonate Chrome 116/131 | Descarga rápida evadiendo AWS WAF sin navegadores pesados |
| **PostgreSQL** | Docker (puerto `5434:5432`) | Almacenamiento local en tabla `argenprop_properties` con UPSERT por `argenprop_id` |
| **Alembic** | SQLAlchemy Async | Control de versiones y esquema de base de datos |
| **Streamlit** | Python Web UI | Dashboard interactivo con filtros, cards, fotos y enlaces directos |
| **FastAPI** | Uvicorn | Endpoints REST para disparar el scraper desde Railway o webhooks |
| **APScheduler** | Cron interno | Sincronización periódica cada 24 horas |

---

## Comandos CLI

```bash
# Scrape por defecto (Salta catálogo completo)
python -m src.cli scrape --limit 100

# Scrape de una URL específica dada
python -m src.cli scrape --url "https://www.argenprop.com/inmuebles/alquiler-o-venta/salta-arg" --limit 200

# Scrape en modo catálogo segmentado (para superar las 10 páginas y descargar todo Salta)
python -m src.cli scrape --segmented --limit 1000

# Enriquecer avisos activos existentes con GPS (Leaflet) y teléfono
python -m src.cli enrich --limit 50

# Ver estadísticas en base de datos
python -m src.cli stats

# Sincronizar directamente con Supabase (tabla argenprop_propiedades)
python -m src.cli scrape-supabase --limit 100

# Iniciar scheduler diario
python -m src.cli schedule
```

---

## Esquema de Base de Datos (`argenprop_properties`)

```
argenprop_properties
├── id (UUID PK)                 ├── latitud / longitud / coordenadas_origen
├── argenprop_id (TEXT UNIQUE)   ├── url / imagen_principal / imagenes (JSONB)
├── titulo / titulo_generado     ├── precio_m2
├── tipo_propiedad               ├── descripcion
├── tipo_operacion               ├── anunciante_nombre / anunciante_logo
├── precio / moneda              ├── anunciante_telefono / anunciante_whatsapp
├── expensas / expensas_moneda   ├── visualizaciones (Visto / Puntos)
├── superficie_total             ├── es_super_destacado / nivel_destacado
├── superficie_cubierta          ├── apto_credito / a_estrenar
├── ambientes / dormitorios      ├── pagina_origen / estado
├── banos / cocheras             ├── activa (BOOLEAN)
├── direccion / barrio           ├── primera_vez_visto / ultima_actualizacion
└── localidad / provincia        └── created_at / updated_at
```
