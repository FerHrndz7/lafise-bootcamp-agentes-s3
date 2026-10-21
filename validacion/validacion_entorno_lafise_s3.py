# Databricks notebook source
# MAGIC %md
# MAGIC # Validación de entorno — Workshop de Agentes AML (Sesión 3: agentes low-code)
# MAGIC
# MAGIC Ejecuta este notebook en el **workspace de desarrollo de LAFISE**, con un **clúster clásico** adjunto
# MAGIC (DBR **17.3 LTS**, modo *Standard*), para confirmar que el entorno soporta el laboratorio de la Sesión 3.
# MAGIC
# MAGIC Crea y usa cada pieza (un Genie Agent de prueba con una tabla y una función de UC, una consulta en
# MAGIC *Agent mode*, un volumen como fuente, la API de Knowledge Assistant) y reporta **PASA / FALLA / ALTERNATIVA / REVISAR**
# MAGIC por requisito. Al final borra lo que creó.
# MAGIC
# MAGIC ## Instrucciones
# MAGIC 1. Adjunta un **clúster clásico** DBR 17.3 LTS.
# MAGIC 2. En el widget **catalog** escribe el catálogo de los asistentes (el de las Sesiones 1 y 2).
# MAGIC 3. **Run all** (~5 min). Comparte la **tabla resumen final** con el facilitador.

# COMMAND ----------

# MAGIC %pip install --quiet "databricks-sdk>=0.94.0" "databricks-openai>=0.10.0" "reportlab>=4.0"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catálogo (requerido)")
dbutils.widgets.text("schema", "validacion_s3", "Schema de prueba")
dbutils.widgets.text("warehouse", "", "SQL warehouse (opcional)")

import json, re, time, uuid
resultados = {}

def marcar(req, estado, detalle=""):
    resultados[req] = (estado, str(detalle)[:300])
    print(f"[{estado}] {req} — {detalle}")

CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip() or "validacion_s3"
assert CATALOG, "Escribe el catálogo en el widget 'catalog' antes de ejecutar."
FQ = f"`{CATALOG}`.{SCHEMA}"
usuario = spark.sql("SELECT current_user()").collect()[0][0]

from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
marcar("0. Librerías instaladas desde PyPI", "PASA", "databricks-sdk, databricks-openai, reportlab")

# COMMAND ----------

try:
    dbr = spark.conf.get("spark.databricks.clusterUsageTags.sparkVersion")
    marcar("1. Clúster clásico y runtime", "PASA" if dbr.startswith("17.") else "ALTERNATIVA", dbr)
except Exception as e:
    marcar("1. Clúster clásico y runtime", "ALTERNATIVA", f"No legible: {e}")

# COMMAND ----------

WH = None
try:
    pref = dbutils.widgets.get("warehouse").strip()
    whs = [x for x in w.warehouses.list() if (not pref or pref in (x.id, x.name))
           and (x.enable_serverless_compute or str(x.warehouse_type).endswith("PRO"))]
    assert whs, "No hay SQL warehouses PRO o serverless visibles para este usuario"
    WH = sorted(whs, key=lambda x: not x.enable_serverless_compute)[0]
    marcar("2. SQL warehouse pro/serverless (CAN USE)", "PASA", f"{WH.name} · serverless={WH.enable_serverless_compute}")
except Exception as e:
    marcar("2. SQL warehouse pro/serverless (CAN USE)", "FALLA", e)

# COMMAND ----------

try:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {FQ}")
    spark.sql(f"CREATE OR REPLACE TABLE {FQ}.alertas_prueba AS SELECT 'AT-001' AS alerta_id, 91 AS score_riesgo")
    spark.sql(f"""CREATE OR REPLACE FUNCTION {FQ}.score_alerta(p_id STRING COMMENT 'ID de alerta')
                  RETURNS TABLE (alerta_id STRING, score_riesgo INT) COMMENT 'Score de una alerta'
                  RETURN SELECT alerta_id, score_riesgo FROM {FQ}.alertas_prueba WHERE alerta_id = p_id""")
    marcar("3. Crear tabla y función de UC", "PASA", f"{CATALOG}.{SCHEMA}")
except Exception as e:
    marcar("3. Crear tabla y función de UC", "FALLA", e)

# COMMAND ----------

SPACE_ID = None
try:
    cfg = {"version": 2,
           "data_sources": {"tables": [{"identifier": f"{CATALOG}.{SCHEMA}.alertas_prueba"}]},
           "instructions": {"sql_functions": [{"id": uuid.uuid4().hex,
                                               "identifier": f"{CATALOG}.{SCHEMA}.score_alerta"}]}}
    SPACE_ID = w.api_client.do("POST", "/api/2.0/genie/spaces", body={
        "warehouse_id": WH.id, "title": f"validacion-s3-{uuid.uuid4().hex[:6]}",
        "serialized_space": json.dumps(cfg)})["space_id"]
    marcar("4. Crear Genie Agent con tabla + función de UC", "PASA", SPACE_ID)
except Exception as e:
    marcar("4. Crear Genie Agent con tabla + función de UC", "FALLA", e)

# COMMAND ----------

def preguntar(pregunta):
    from databricks_openai import DatabricksOpenAI
    c = DatabricksOpenAI(workspace_client=w)
    c.base_url = f"{w.config.host.rstrip('/')}/api/2.0/genie/agents/{SPACE_ID}"
    out = {"texto": "", "sql": [], "error": None}
    for ev in c.responses.create(model="genie-agent", stream=True, input=[
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": pregunta}]}]):
        if ev.type == "response.failed":
            out["error"] = getattr(ev.response.error, "message", str(ev.response.error))
        if ev.type == "response.completed":
            for it in ev.response.model_dump(warnings=False).get("output", []):
                if it.get("type") == "function_call":
                    out["sql"].append(json.loads(it.get("arguments") or "{}").get("sql", ""))
                if it.get("type") == "message":
                    out["texto"] += " ".join(c.get("text", "") for c in it.get("content", []))
    return out

try:
    r = preguntar("¿Cuál es el score de riesgo de la alerta AT-001? Usa la función score_alerta.")
    assert not r["error"], r["error"]
    usa_fn = any("score_alerta" in s for s in r["sql"])
    marcar("5. Agent mode por API (y uso de la función)", "PASA" if usa_fn and "91" in r["texto"] else "ALTERNATIVA",
           f"funcion={usa_fn} · respuesta contiene 91={'91' in r['texto']}")
except Exception as e:
    marcar("5. Agent mode por API (y uso de la función)", "FALLA",
           f"{e} · Revisa que Agent mode y la Beta 'Agent Mode APIs for Genie Agents' estén disponibles")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Documentos en un volumen (Beta)
# MAGIC Este punto prueba que se puede adjuntar un volumen con un PDF al agente. Requiere que un admin active en
# MAGIC **Previews** *Analyze Files in Volumes with Genie Agents*. Por API el volumen se adjunta pero **no se indexa**
# MAGIC (la indexación se activa al conectarlo desde la interfaz del agente, como haremos en la sesión). Por eso este
# MAGIC punto suele salir **REVISAR**: confirmen en **Settings → Previews** que la Beta esté en **On**. Si no se puede
# MAGIC activar, la sesión usa el Knowledge Assistant (notebook 03) para los documentos.

# COMMAND ----------

try:
    from io import BytesIO
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    spark.sql(f"CREATE VOLUME IF NOT EXISTS {FQ}.docs_prueba")
    buf = BytesIO()
    SimpleDocTemplate(buf).build([Paragraph("Artículo 5. El umbral del Reporte de Transacción en Efectivo es "
                                            "USD 10,000.", getSampleStyleSheet()["BodyText"])])
    open(f"/Volumes/{CATALOG}/{SCHEMA}/docs_prueba/politica_prueba.pdf", "wb").write(buf.getvalue())
    cfg["data_sources"]["volumes"] = [{"path": f"/Volumes/{CATALOG}/{SCHEMA}/docs_prueba",
                                       "description": ["Política de prueba"]}]
    w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{SPACE_ID}", body={"serialized_space": json.dumps(cfg)})
    r = preguntar("Según el documento de política, ¿cuál es el umbral del RTE?")
    if r["error"] and "content search" in r["error"].lower():
        marcar("6. Documentos de un volumen en el agente (Beta)", "REVISAR",
               "El volumen se adjunta. Confirmen en Settings → Previews que 'Analyze Files in Volumes with Genie "
               "Agents' esté en On (por API no se indexa; en la sesión se indexa desde la interfaz del agente)")
    elif r["error"]:
        marcar("6. Documentos de un volumen en el agente (Beta)", "ALTERNATIVA", r["error"])
    else:
        marcar("6. Documentos de un volumen en el agente (Beta)", "PASA" if "10" in r["texto"] else "ALTERNATIVA",
               r["texto"][:150])
except Exception as e:
    marcar("6. Documentos de un volumen en el agente (Beta)", "ALTERNATIVA", e)

# COMMAND ----------

try:
    r = w.api_client.do("GET", "/api/2.1/knowledge-assistants")
    marcar("7. API de Knowledge Assistant (legacy, plan B)", "PASA", f"{len(r.get('knowledge_assistants', []))} visibles")
except Exception as e:
    marcar("7. API de Knowledge Assistant (legacy, plan B)", "ALTERNATIVA", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Limpieza y resumen

# COMMAND ----------

try:
    if SPACE_ID:
        w.api_client.do("DELETE", f"/api/2.0/genie/spaces/{SPACE_ID}")
    spark.sql(f"DROP SCHEMA IF EXISTS {FQ} CASCADE")
    print("🧹 Limpieza completa")
except Exception as e:
    print("⚠️ Limpieza parcial:", e)

print(f"\n{'Requisito':55s} {'Estado':12s} Detalle")
for req, (estado, det) in resultados.items():
    print(f"{req:55s} {estado:12s} {det[:110]}")
