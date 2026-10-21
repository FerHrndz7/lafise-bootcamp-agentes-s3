# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Comparar con la Sesión 2 y gobernar el agente
# MAGIC
# MAGIC **Tiempo estimado:** 15 minutos
# MAGIC
# MAGIC ## Objetivos
# MAGIC - Correr las **3 alertas testigo** por API y comparar contra la disposición esperada.
# MAGIC - Comparar el resultado y el **esfuerzo** con el agente code-first de la Sesión 2.
# MAGIC - Revisar **quién puede usar el agente** y **qué datos ve cada usuario**.
# MAGIC - Decidir **cuándo conviene low-code y cuándo code-first**.

# COMMAND ----------

# MAGIC %pip install --quiet "databricks-sdk>=0.94.0" "databricks-openai>=0.10.0"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import re
dbutils.widgets.text("catalog", "", "Catálogo asignado (REQUERIDO)")
dbutils.widgets.text("schema", "pld_aml", "Schema base")

user_email = spark.sql("SELECT current_user()").collect()[0][0]
user_prefix = re.sub(r"[^a-z0-9]", "_", user_email.split("@")[0].lower())
CATALOG = dbutils.widgets.get("catalog").strip()
assert CATALOG, "Escribe en el widget 'catalog' el mismo catálogo del 00_setup."
SCHEMA = f"{(dbutils.widgets.get('schema').strip() or 'pld_aml')}_{user_prefix}"
FQ = f"`{CATALOG}`.{SCHEMA}"
TITULO_AGENTE = f"Alertas PLD · {user_prefix}"

from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

# COMMAND ----------

# MAGIC %run ./utils/genie_utils

# COMMAND ----------

SPACE_ID = buscar_agente(w, TITULO_AGENTE)
assert SPACE_ID, f"No encontré tu agente '{TITULO_AGENTE}'. Completa los notebooks 01 y 02."
print(f"Agente: {SPACE_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 1 — Las 3 alertas testigo
# MAGIC
# MAGIC | Alerta | Patrón | Disposición aceptable |
# MAGIC |---|---|---|
# MAGIC | `AT-001` | 9 depósitos en efectivo justo debajo de USD 10,000 (estructuración) | `REPORTAR_ROS` o `ESCALAR_INVESTIGACION` |
# MAGIC | `AT-002` | Cliente de riesgo bajo, movimientos pequeños y consistentes | `CERRAR_SIN_ACCION` o `SOLICITAR_INFORMACION` |
# MAGIC | `AT-003` | Contraparte en jurisdicción de alto riesgo | Cualquiera **menos** `CERRAR_SIN_ACCION` (regla dura) |
# MAGIC
# MAGIC Cada alerta va en una **conversación nueva** para que no se contaminen entre sí (~1 min por alerta).

# COMMAND ----------

# AT-002 es consistente con el perfil; pedir información también es prudente.
ACEPTABLES = {
    "AT-001": {"REPORTAR_ROS", "ESCALAR_INVESTIGACION"},
    "AT-002": {"CERRAR_SIN_ACCION", "SOLICITAR_INFORMACION"},
    "AT-003": {"SOLICITAR_INFORMACION", "ESCALAR_INVESTIGACION", "REPORTAR_ROS"},
}

dictamenes = {}
for alerta in ACEPTABLES:
    r = preguntar_agente(w, SPACE_ID, f"Analiza la alerta {alerta} y recomienda una disposición con su fundamento.")
    dictamenes[alerta] = r
    disp = extraer_disposicion(r["texto"])
    ok = disp in ACEPTABLES[alerta]
    print(f"{'✅' if ok else '❌'} {alerta}: {disp}  ·  {len(r['sql'])} consultas · {len(r['citas'])} citas a documentos · {r['segundos']} s")

# COMMAND ----------

# Expected output: ✅ 3/3 alertas con una disposición aceptable
try:
    aciertos = sum(extraer_disposicion(r["texto"]) in ACEPTABLES[a] for a, r in dictamenes.items())
    assert aciertos == 3, f"Solo {aciertos}/3 alertas con disposición aceptable. Revisa instrucciones y funciones."
    print("✅ 3/3 alertas con una disposición aceptable")
except AssertionError as e:
    print("❌ Casi:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 2 — Lado a lado con la Sesión 2
# MAGIC Si corriste el reto de la Sesión 2, la tabla `dictamenes_agente` guarda las disposiciones del agente
# MAGIC code-first. Las comparamos con las de hoy.

# COMMAND ----------

hoy = {a: extraer_disposicion(r["texto"]) for a, r in dictamenes.items()}
if spark.catalog.tableExists(f"{CATALOG}.{SCHEMA}.dictamenes_agente"):
    s2 = {r["alerta_id"]: r["disposicion"] for r in spark.table(f"{FQ}.dictamenes_agente").collect()}
else:
    s2 = {}
    print("ℹ️ No encontré dictamenes_agente (Sesión 2, reto). Comparamos solo contra lo esperado.")
print(f"{'Alerta':8s} {'Sesión 2 (code-first)':26s} {'Hoy (Genie Agent)':24s}")
for a in ACEPTABLES:
    print(f"{a:8s} {str(s2.get(a, '—')):26s} {str(hoy[a]):24s}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### ¿Cuánto esfuerzo costó cada camino?
# MAGIC
# MAGIC | | Sesión 2 · code-first | Hoy · Genie Agent |
# MAGIC |---|---|---|
# MAGIC | Herramientas | 2 funciones UC + retriever en Python | Las mismas 2 funciones UC + un volumen (clics) |
# MAGIC | Razonamiento | Bucle ReAct en LangGraph, supervisor y sub-agentes | *Agent mode* gestionado |
# MAGIC | Reglas de negocio | Prompt **y** código (regla dura en Python) | Instrucciones (texto) y funciones de UC |
# MAGIC | Documentos | Parseo, chunking e índice que tú controlas | Content search gestionado |
# MAGIC | Despliegue | `ResponsesAgent` + Agent Bricks CLI / Model Serving | Ya está disponible: UI, API y Genie One |
# MAGIC | Control fino | Total (modelo, pasos, formato JSON exacto) | Limitado (instrucciones, ejemplos, funciones) |
# MAGIC
# MAGIC **Regla práctica:**
# MAGIC - **Genie Agent (low-code)** cuando el valor está en preguntar sobre datos y documentos gobernados, el usuario es
# MAGIC   un analista y la lógica crítica cabe en **funciones de UC** (que sí controlas).
# MAGIC - **Code-first (Agent Bricks CLI)** cuando necesitas un flujo exacto, salida estructurada estricta para otro
# MAGIC   sistema, reglas duras que el código **garantiza**, o integrar el agente en una aplicación.
# MAGIC - **Ambos:** un agente code-first puede usar tu Genie Agent como herramienta:
# MAGIC   `agentbricks tools add genie-agent <SPACE_ID>`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 3 — Gobierno: quién usa el agente y qué datos ve
# MAGIC Un Genie Agent separa dos credenciales:
# MAGIC - **Cómputo:** las consultas corren en el SQL warehouse con las credenciales que embebió el autor.
# MAGIC - **Datos:** Unity Catalog evalúa **los permisos de quien pregunta**. Si un analista no tiene `SELECT` sobre
# MAGIC   `transacciones` o `READ VOLUME` sobre `documentos`, el agente no se los muestra. Los *row filters* y
# MAGIC   *column masks* de UC se aplican por usuario, automáticamente.
# MAGIC
# MAGIC Niveles para compartir: **CAN VIEW**, **CAN RUN** (usar), **CAN EDIT** (configurar), **CAN MANAGE**.
# MAGIC En la interfaz: botón **Share** del agente. Por API:

# COMMAND ----------

acl = w.api_client.do("GET", f"/api/2.0/permissions/genie/{SPACE_ID}")
for e in acl.get("access_control_list", []):
    quien = e.get("user_name") or e.get("group_name") or e.get("service_principal_name")
    print(f"  {quien:45s} {[p.get('permission_level') for p in e.get('all_permissions', [])]}")

# COMMAND ----------

# MAGIC %md
# MAGIC > **Para producción en LAFISE:** comparte el agente con un **grupo** de analistas PLD (CAN RUN), no con
# MAGIC > personas; da `SELECT` y `READ VOLUME` a ese grupo en UC; y revisa la pestaña **Monitoring** del agente
# MAGIC > para ver qué preguntan y con qué SQL respondió. En la Sesión 4 lo evaluaremos con **benchmarks** y MLflow.
# MAGIC
# MAGIC ## Resumen
# MAGIC - El Genie Agent resolvió las 3 alertas testigo con el mismo criterio que el agente de la Sesión 2.
# MAGIC - El gobierno vive en **Unity Catalog**: mismas funciones, mismos permisos, por usuario.
# MAGIC - Low-code y code-first **no compiten**: se combinan.
# MAGIC
# MAGIC ➡️ Tarea: `05_reto` — la verificación de **sanciones** como regla dura.
# MAGIC
# MAGIC ## Glosario
# MAGIC | Término | Definición |
# MAGIC |---|---|
# MAGIC | **CAN RUN** | Permiso para usar (preguntar a) un Genie Agent. |
# MAGIC | **Row filter / column mask** | Reglas de UC que filtran filas o enmascaran columnas según quién consulta. |
# MAGIC | **Monitoring** | Pestaña del agente con las preguntas, respuestas y SQL de cada usuario. |
# MAGIC | **Genie One** | Experiencia de Databricks para usuarios de negocio; puede llamar a tu Genie Agent. |
