# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Tu Agente de Alertas como Genie Agent (tablas + funciones de UC + instrucciones)
# MAGIC
# MAGIC **Tiempo estimado:** 20 minutos
# MAGIC
# MAGIC ## Objetivos
# MAGIC - Crear un **Genie Agent** sobre las tablas de alertas, clientes y transacciones.
# MAGIC - Conectarle las **mismas funciones de Unity Catalog** de la Sesión 2 como *funciones SQL* (activos de confianza).
# MAGIC - Escribir sus **instrucciones**: disposiciones posibles y reglas duras.
# MAGIC - Verificar por API que el agente quedó configurado y que **usa las funciones** al analizar una alerta.
# MAGIC
# MAGIC ## Concepto — ¿Qué es un Genie Agent?
# MAGIC Un **Genie Agent** (antes *Genie Space*) es un agente que un analista configura **sin código**: le das datos
# MAGIC de Unity Catalog, ejemplos, funciones e instrucciones, y Genie traduce las preguntas a SQL, razona y responde.
# MAGIC
# MAGIC | Sesión 2 (code-first) | Hoy (low-code) |
# MAGIC |---|---|
# MAGIC | `UCFunctionToolkit` + `ToolNode` | Agregar la función en **Configure → SQL functions** |
# MAGIC | `INSTRUCCIONES_AGENTE_ALERTAS` en Python | Campo **Instructions** del agente |
# MAGIC | Bucle ReAct en LangGraph | **Agent mode**: Genie planea, ejecuta varias consultas y sintetiza |
# MAGIC | `COMMENT` de las funciones | `COMMENT` de las funciones **y** descripciones de tablas/columnas |
# MAGIC
# MAGIC > Gobierno: el agente **solo** usa las tablas y funciones que adjuntas, y siempre con los **permisos de UC de
# MAGIC > quien pregunta**. Si un analista no tiene `SELECT` sobre una tabla, el agente no se la puede mostrar.

# COMMAND ----------

# MAGIC %pip install --quiet "databricks-sdk>=0.94.0" "databricks-openai>=0.10.0"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import re
dbutils.widgets.text("catalog", "", "Catálogo asignado (REQUERIDO)")
dbutils.widgets.text("schema", "pld_aml", "Schema base")
dbutils.widgets.text("warehouse", "", "SQL warehouse (opcional)")
dbutils.widgets.dropdown("modo", "ui", ["ui", "api"], "¿Cómo creaste el agente?")

user_email = spark.sql("SELECT current_user()").collect()[0][0]
user_prefix = re.sub(r"[^a-z0-9]", "_", user_email.split("@")[0].lower())
CATALOG = dbutils.widgets.get("catalog").strip()
assert CATALOG, "Escribe en el widget 'catalog' el mismo catálogo del 00_setup."
SCHEMA = f"{(dbutils.widgets.get('schema').strip() or 'pld_aml')}_{user_prefix}"
TITULO_AGENTE = f"Alertas PLD · {user_prefix}"

from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

# COMMAND ----------

# MAGIC %run ./utils/genie_utils

# COMMAND ----------

# MAGIC %md
# MAGIC ## Tus valores para el formulario (ejecuta esta celda y tenla a la vista)

# COMMAND ----------

INSTRUCCIONES = [
    "Eres el Agente de Alertas AML de la Unidad PLD de un banco centroamericano. Analizas UNA alerta del monitoreo "
    "transaccional y recomiendas su disposición a un analista humano, que toma la decisión final.",
    "Procedimiento: (1) usa la función obtener_alerta para leer la alerta y el perfil KYC del cliente; (2) usa la "
    "función features_transaccionales para obtener las señales de los 30 días previos; (3) decide la disposición.",
    "Disposiciones posibles (elige exactamente una y escríbela tal cual): CERRAR_SIN_ACCION (la actividad es "
    "consistente con el perfil), SOLICITAR_INFORMACION (faltan datos, p. ej. origen de fondos), ESCALAR_INVESTIGACION "
    "(persisten indicios: pass-through, testaferros, alto riesgo), REPORTAR_ROS (tipología con evidencia clara).",
    "Reglas duras: nunca inventes cifras, usa solo las que devuelven las funciones y tablas. Si el cliente es PEP o "
    "hay contrapartes en jurisdicciones de alto riesgo, no cierres sin acción.",
    "Formato de respuesta en español: Disposición, Señales clave (con cifras), Justificación y Fundamento.",
]
TABLAS = [f"{CATALOG}.{SCHEMA}.{t}" for t in ("alertas", "clientes", "transacciones", "narrativas_casos")]
FUNCIONES = [f"{CATALOG}.{SCHEMA}.{f}" for f in ("obtener_alerta", "features_transaccionales")]

print("TÍTULO DEL AGENTE (cópialo exacto):", TITULO_AGENTE)
print("\nTABLAS:");     [print("  ", t) for t in TABLAS]
print("\nFUNCIONES SQL:"); [print("  ", f) for f in FUNCIONES]
print("\nINSTRUCCIONES (copia y pega en Instructions):\n")
print("\n\n".join(INSTRUCCIONES))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Parte A — Crear el agente en la interfaz (camino principal)
# MAGIC
# MAGIC 1. En la barra lateral, haz clic en **Genie Agents** → **New** (arriba a la derecha).
# MAGIC 2. Elige las **4 tablas** que imprimió la celda anterior (`alertas`, `clientes`, `transacciones`,
# MAGIC    `narrativas_casos`) → **Create**. *Genie Code* puede ofrecer sugerencias de contexto: revísalas y acepta
# MAGIC    las que tengan sentido.
# MAGIC 3. **Configure → Settings**: pon el **título exacto** `Alertas PLD · <tu_usuario>`, elige el SQL warehouse y
# MAGIC    una descripción ("Analiza alertas del monitoreo transaccional y recomienda una disposición").
# MAGIC 4. **Configure → Instructions**: pega las instrucciones de la celda anterior.
# MAGIC 5. **Configure → SQL queries / functions → Add → SQL function**: agrega `obtener_alerta` y
# MAGIC    `features_transaccionales` de tu schema.
# MAGIC 6. Prueba en el chat (modo *Chat*):
# MAGIC    - *¿Cuántas alertas abiertas hay por tipología?*
# MAGIC    - *Muéstrame la alerta AT-001 con el perfil del cliente.*
# MAGIC    - *¿Qué clientes PEP tienen alertas abiertas?*
# MAGIC 7. Abre **Show code** en una respuesta: es SQL que puedes auditar. Fíjate si usó tu función.
# MAGIC
# MAGIC > ¿No puedes usar la interfaz (o se te acabó el tiempo)? Cambia el widget **modo** a `api` y la siguiente
# MAGIC > celda crea el mismo agente por ti, con la API de Genie.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Parte B — El agente como configuración (y camino alternativo por API)
# MAGIC Un Genie Agent **es una configuración**: tablas, funciones, instrucciones y ejemplos en un JSON
# MAGIC (`serialized_space`). Eso permite versionarlo y promoverlo entre workspaces (desarrollo → producción).
# MAGIC

# COMMAND ----------

# las listas que imprimimos arriba; Genie solo usa lo que se adjunta explícitamente.
CONFIG = construir_config(
    tablas=TABLAS,
    funciones=FUNCIONES,
    instrucciones=INSTRUCCIONES,
    preguntas=["Analiza la alerta AT-001 y recomienda una disposición",
               "¿Cuántas alertas abiertas hay por tipología?",
               "¿Qué clientes PEP tienen alertas abiertas?"],
)

if dbutils.widgets.get("modo") == "api":
    WAREHOUSE_ID = elegir_warehouse(w, dbutils.widgets.get("warehouse").strip())
    SPACE_ID = guardar_agente(w, TITULO_AGENTE, WAREHOUSE_ID, CONFIG,
                              "Analiza alertas del monitoreo transaccional y recomienda una disposición")
    print(f"✅ Agente creado/actualizado por API: {SPACE_ID}")
else:
    SPACE_ID = buscar_agente(w, TITULO_AGENTE)
    assert SPACE_ID, (f"No encontré un Genie Agent con el título '{TITULO_AGENTE}'. Revisa el título en "
                      "Configure → Settings, o cambia el widget 'modo' a 'api'.")
    print(f"✅ Encontré tu agente creado en la interfaz: {SPACE_ID}")

print(f"Ábrelo en: {w.config.host.rstrip('/')}/genie/rooms/{SPACE_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validación — ¿el agente tiene lo que necesita?

# COMMAND ----------

# Expected output: ✅ 4 tablas, 2 funciones e instrucciones configuradas
cfg = leer_config(w, SPACE_ID)
tablas_cfg = {t["identifier"] for t in cfg.get("data_sources", {}).get("tables", [])}
funcs_cfg = {f["identifier"] for f in cfg.get("instructions", {}).get("sql_functions", [])}
tiene_instr = bool(cfg.get("instructions", {}).get("text_instructions"))
try:
    assert {f"{CATALOG}.{SCHEMA}.alertas", f"{CATALOG}.{SCHEMA}.clientes",
            f"{CATALOG}.{SCHEMA}.transacciones"} <= tablas_cfg, f"Faltan tablas. Tiene: {sorted(tablas_cfg)}"
    assert set(FUNCIONES) <= funcs_cfg, f"Faltan funciones SQL. Tiene: {sorted(funcs_cfg) or 'ninguna'}"
    assert tiene_instr, "El agente no tiene instrucciones"
    print(f"✅ {len(tablas_cfg)} tablas, {len(funcs_cfg)} funciones e instrucciones configuradas")
except AssertionError as e:
    print("❌ Casi:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 2 — Pregúntale por API en *Agent mode*
# MAGIC **Agent mode** es el modo de razonamiento de varios pasos: arma un plan, ejecuta varias consultas (o tus
# MAGIC funciones), revisa los resultados y sintetiza. Es el equivalente gestionado del bucle ReAct de la Sesión 2.
# MAGIC
# MAGIC La utilidad `preguntar_agente` devuelve la respuesta, **el SQL que ejecutó** y los documentos citados.
# MAGIC Tarda ~20–60 s.

# COMMAND ----------

res = preguntar_agente(w, SPACE_ID, "Analiza la alerta AT-001 y recomienda una disposición.")
mostrar(res)

# COMMAND ----------

# Expected output: ✅ El agente usó features_transaccionales y recomendó una disposición válida
try:
    assert not res["error"], res["error"]
    usadas = " ".join(res["sql"]).lower()
    assert "features_transaccionales" in usadas or "obtener_alerta" in usadas, \
        "El agente no usó tus funciones de UC. Revisa que estén agregadas como SQL functions."
    disp = extraer_disposicion(res["texto"])
    assert disp, "No encontré una disposición válida en la respuesta. Revisa las instrucciones."
    print(f"✅ El agente usó tus funciones y recomendó: {disp}")
except AssertionError as e:
    print("❌ Casi:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resumen
# MAGIC - Construiste el Agente de Alertas **sin escribir su código**: tablas + funciones de UC + instrucciones.
# MAGIC - Las **mismas funciones** de la Sesión 2 sirven a los dos caminos: el gobierno vive en Unity Catalog.
# MAGIC - El agente **es una configuración** (`serialized_space`) que puedes versionar y promover.
# MAGIC
# MAGIC Todavía le falta algo: **fundamentar** la disposición en la política PLD. ➡️ `02_documentos_y_agent_mode`.
# MAGIC
# MAGIC ## Glosario
# MAGIC | Término | Definición |
# MAGIC |---|---|
# MAGIC | **Genie Agent** | Agente low-code sobre datos de UC (antes *Genie Space*). Se configura, no se programa. |
# MAGIC | **Función SQL (activo de confianza)** | Función de UC adjunta al agente; su lógica la verificó el autor. |
# MAGIC | **Agent mode** | Modo de razonamiento de varios pasos con plan, varias consultas y reporte final. |
# MAGIC | **Chat mode** | Modo rápido: una pregunta, una consulta SQL. No lee documentos. |
# MAGIC | **serialized_space** | El JSON con toda la configuración del agente; base para versionarlo. |
# MAGIC | **SQL warehouse** | El cómputo donde corren las consultas del agente (pro o serverless). |
