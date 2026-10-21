# Databricks notebook source
# MAGIC %md
# MAGIC # Módulo 3 · Preparación — Agentes low-code (Agente de Alertas AML sin escribir el agente)
# MAGIC
# MAGIC | | |
# MAGIC |---|---|
# MAGIC | **Duración** | ~75 min de práctica (esta preparación: ~8 min) |
# MAGIC | **Nivel** | Intermedio |
# MAGIC | **Lenguaje** | Interfaz de Databricks + Python para validar |
# MAGIC | **Cómputo** | Clúster **clásico** (DBR **17.3 LTS**, modo *Standard*) + un **SQL warehouse** pro o serverless |
# MAGIC | **Catalog.Schema** | `<catálogo_asignado>.pld_aml_<tu_usuario>` (el mismo de las Sesiones 1 y 2) |
# MAGIC
# MAGIC ## Qué construirás hoy 🧱
# MAGIC En la Sesión 2 **programaste** el Agente de Alertas: herramientas, bucle de razonamiento, supervisor y
# MAGIC despliegue. Hoy construyes **el mismo agente sin programarlo**, con un **Genie Agent** (antes *Genie
# MAGIC Space*): le das las tablas, las mismas funciones de Unity Catalog, los documentos de la política y unas
# MAGIC instrucciones, y Databricks se encarga del razonamiento.
# MAGIC
# MAGIC Recorrido de la sesión:
# MAGIC 1. `00_setup` — configuración y verificación de tus datos de las Sesiones 1 y 2 (**estás aquí**).
# MAGIC 2. `01_genie_agent_alertas` — crea el agente sobre tablas + funciones de UC + instrucciones.
# MAGIC 3. `02_documentos_y_agent_mode` — conecta la política PLD (volumen) y pide un **dictamen citado** en *Agent mode*.
# MAGIC 4. `03_knowledge_assistant_legacy` — *(opcional)* el camino anterior: **Knowledge Assistant** de Agent Bricks.
# MAGIC 5. `04_comparar_y_gobernar` — corre las 3 alertas testigo por API, compara con la Sesión 2 y revisa permisos.
# MAGIC 6. `05_reto` — **tarea**: agrega la verificación de **sanciones** como regla dura.
# MAGIC
# MAGIC ### ¿Y "Agent Bricks"? Una aclaración de nombres (octubre 2026)
# MAGIC - **Agent Bricks** hoy es la plataforma de Databricks para agentes **escritos en código** (el CLI que viste
# MAGIC   en la Sesión 2, Agent Runtime, memoria, tracing).
# MAGIC - Para construir agentes **sin código**, la recomendación actual son los **Genie Agents**.
# MAGIC - **Knowledge Assistant** y **Supervisor Agent** (los "bricks" low-code originales) siguen funcionando, pero
# MAGIC   ya son *legacy*: no se recomiendan para agentes nuevos. Los verás en el notebook `03` para que los
# MAGIC   reconozcas si ya existen en tu organización.
# MAGIC
# MAGIC > ⚠️ **Datos sintéticos.** Todo es inventado. Nunca uses PII real de clientes en un workspace de laboratorio.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sección 1 — Dependencias
# MAGIC `databricks-openai` es el cliente con el que consultaremos al agente desde los notebooks. `reportlab` y
# MAGIC `faker` solo se usan si hay que regenerar datos de la Sesión 1.

# COMMAND ----------

# MAGIC %pip install --quiet "databricks-sdk>=0.94.0" "databricks-openai>=0.10.0" "reportlab>=4.0" "faker>=25.0.0"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sección 2 — Configuración (aislamiento por participante)
# MAGIC Escribe en el widget **catalog** el **mismo catálogo de las Sesiones 1 y 2**. El widget **warehouse** es
# MAGIC opcional: si lo dejas vacío, elegimos un SQL warehouse pro o serverless disponible.

# COMMAND ----------

import re

dbutils.widgets.text("catalog", "", "Catálogo asignado (REQUERIDO)")
dbutils.widgets.text("schema", "pld_aml", "Schema base")
dbutils.widgets.text("warehouse", "", "SQL warehouse (opcional)")

user_email = spark.sql("SELECT current_user()").collect()[0][0]
user_prefix = re.sub(r"[^a-z0-9]", "_", user_email.split("@")[0].lower())
CATALOG = dbutils.widgets.get("catalog").strip()
assert CATALOG, "Escribe en el widget 'catalog' el catálogo que te asignó el facilitador (el de la Sesión 1)."
SCHEMA = f"{(dbutils.widgets.get('schema').strip() or 'pld_aml')}_{user_prefix}"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/documentos"
TITULO_AGENTE = f"Alertas PLD · {user_prefix}"

print(f"Usuario:   {user_email}")
print(f"Destino:   {CATALOG}.{SCHEMA}")
print(f"Volumen:   {VOLUME_PATH}")
print(f"Tu agente: {TITULO_AGENTE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sección 3 — Verificación del entorno

# COMMAND ----------

import sys
from importlib.metadata import version
from databricks.sdk import WorkspaceClient

print(f"Python: {sys.version.split()[0]}")
assert sys.version_info >= (3, 10), "Se requiere Python 3.10+"
for p in ["databricks-sdk", "databricks-openai"]:
    print(f"  {p:20s} {version(p)}")
try:
    print(f"DBR del clúster: {spark.conf.get('spark.databricks.clusterUsageTags.sparkVersion')}")
except Exception:
    print("DBR del clúster: no legible aquí (confirma 17.3 LTS en la configuración del clúster).")

w = WorkspaceClient()

# COMMAND ----------

# MAGIC %run ./utils/genie_utils

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sección 4 — Permisos y SQL warehouse
# MAGIC Un Genie Agent ejecuta su SQL en un **SQL warehouse pro o serverless** (no en tu clúster). Necesitas
# MAGIC **CAN USE** sobre uno y el entitlement **Databricks SQL**. También creas funciones en tu schema.

# COMMAND ----------

WAREHOUSE_ID = elegir_warehouse(w, dbutils.widgets.get("warehouse").strip())
wh = w.warehouses.get(WAREHOUSE_ID)
print(f"✅ SQL warehouse: {wh.name} ({WAREHOUSE_ID}) · tipo {wh.warehouse_type} · serverless={wh.enable_serverless_compute}")

try:
    spark.sql(f"USE CATALOG `{CATALOG}`")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.{SCHEMA}")
    spark.sql(f"CREATE OR REPLACE FUNCTION `{CATALOG}`.{SCHEMA}._prueba_permiso() RETURNS STRING RETURN 'ok'")
    spark.sql(f"DROP FUNCTION IF EXISTS `{CATALOG}`.{SCHEMA}._prueba_permiso")
    print(f"✅ Puedes crear funciones en {CATALOG}.{SCHEMA}")
except Exception as e:
    raise PermissionError(f"No se pueden crear funciones en {CATALOG}.{SCHEMA}. Pide al administrador USE CATALOG + "
                          f"USE SCHEMA + CREATE FUNCTION + CREATE VOLUME. Error subyacente: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sección 5 — Datos, documentos y herramientas
# MAGIC El bootstrap **reutiliza** lo de las Sesiones 1 y 2 (tablas, volumen `documentos`, alertas testigo) y solo
# MAGIC regenera lo que falte. También (re)crea las funciones `obtener_alerta` y `features_transaccionales` y pone
# MAGIC **descripciones** a tablas y columnas, que Genie usa para entender tus datos.

# COMMAND ----------

# MAGIC %run ./data/bootstrap_sesion3 $catalog=$catalog $schema=$schema

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sección 6 — Resumen

# COMMAND ----------

FQ = f"`{CATALOG}`.{SCHEMA}"
print("=" * 64)
print(f"Catálogo.schema : {CATALOG}.{SCHEMA}")
print(f"SQL warehouse   : {wh.name}")
print(f"Volumen         : {VOLUME_PATH}")
print(f"Funciones UC    : {CATALOG}.{SCHEMA}.obtener_alerta, {CATALOG}.{SCHEMA}.features_transaccionales")
print(f"Título agente   : {TITULO_AGENTE}   (úsalo tal cual en el notebook 01)")
print("=" * 64)
display(spark.sql(f"SELECT * FROM {FQ}.obtener_alerta('AT-001')"))
print("✅ Preparación completa. Sigue con 01_genie_agent_alertas.")
