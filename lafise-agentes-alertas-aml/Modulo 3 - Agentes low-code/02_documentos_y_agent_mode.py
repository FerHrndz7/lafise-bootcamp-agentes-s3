# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Documentos de la política + dictamen citado en *Agent mode*
# MAGIC
# MAGIC **Tiempo estimado:** 20 minutos
# MAGIC
# MAGIC ## Objetivos
# MAGIC - Conectar el volumen `documentos` (política PLD, tipologías, instructivo) al agente.
# MAGIC - Entender **content search**: Databricks parsea e indexa los archivos por ti.
# MAGIC - Obtener un **dictamen** para AT-001 que combine **datos** (funciones) y **normativa** (documentos) con **citas**.
# MAGIC
# MAGIC ## Concepto — del índice de la Sesión 1 al volumen de hoy
# MAGIC En la Sesión 1 hiciste a mano el camino completo: `ai_parse_document` → chunking → embeddings → índice de
# MAGIC AI Search. Al adjuntar un volumen a un Genie Agent, **content search** hace ese mismo trabajo de forma
# MAGIC gestionada (parsea con `ai_parse_document`, indexa y se mantiene al día con el volumen).
# MAGIC
# MAGIC | Sesión 1-2 (code-first) | Hoy (low-code) |
# MAGIC |---|---|
# MAGIC | Parseo, chunking y `chunks_index` que tú controlas | **Content search** gestionado sobre el volumen |
# MAGIC | `VectorSearchRetrieverTool` (`buscar_normativa_pld`) | Volumen como **Source** del agente |
# MAGIC | Citas que pides en el prompt | Citas que el agente adjunta a su reporte |
# MAGIC
# MAGIC > **Requisitos (Beta):** un admin debe activar **Analyze Files in Volumes with Genie Agents** en *Previews*;
# MAGIC > el volumen debe ser **managed**; los archivos deben ser PDF, DOCX, PPTX, MD, TXT o imágenes. Las preguntas
# MAGIC > sobre documentos solo funcionan en **Agent mode**. Si tu workspace no tiene esta Beta, salta al
# MAGIC > notebook `03` (Knowledge Assistant) para la parte de documentos.

# COMMAND ----------

# MAGIC %pip install --quiet "databricks-sdk>=0.94.0" "databricks-openai>=0.10.0"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import re
dbutils.widgets.text("catalog", "", "Catálogo asignado (REQUERIDO)")
dbutils.widgets.text("schema", "pld_aml", "Schema base")
dbutils.widgets.dropdown("modo", "ui", ["ui", "api"], "¿Cómo conectas el volumen?")

user_email = spark.sql("SELECT current_user()").collect()[0][0]
user_prefix = re.sub(r"[^a-z0-9]", "_", user_email.split("@")[0].lower())
CATALOG = dbutils.widgets.get("catalog").strip()
assert CATALOG, "Escribe en el widget 'catalog' el mismo catálogo del 00_setup."
SCHEMA = f"{(dbutils.widgets.get('schema').strip() or 'pld_aml')}_{user_prefix}"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/documentos"
TITULO_AGENTE = f"Alertas PLD · {user_prefix}"

from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

# COMMAND ----------

# MAGIC %run ./utils/genie_utils

# COMMAND ----------

SPACE_ID = buscar_agente(w, TITULO_AGENTE)
assert SPACE_ID, f"No encontré tu agente '{TITULO_AGENTE}'. Completa primero el notebook 01."
print(f"Agente: {SPACE_ID}")
print(f"Volumen a conectar: {VOLUME_PATH}")
print("Archivos:", sorted(f.name for f in dbutils.fs.ls(VOLUME_PATH)))

DESCRIPCION_VOLUMEN = ("Normativa PLD del banco: política PLD/FT (artículos numerados, umbrales RTE y plazos ROS), "
                       "manual de tipologías de lavado y sus señales de alerta, e instructivo de escalamiento y "
                       "disposición de alertas. Úsalo para fundamentar y citar cada disposición.")
INSTRUCCION_EXTRA = ("Fundamento obligatorio: toda disposición debe citar al menos un documento del volumen de "
                     "normativa (nombre del archivo y artículo o tipología). Si no encuentras fundamento, dilo.")
print("\nDESCRIPCIÓN DEL VOLUMEN (cópiala):\n", DESCRIPCION_VOLUMEN)
print("\nAGREGA AL FINAL DE LAS INSTRUCCIONES:\n", INSTRUCCION_EXTRA)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 1 — Conectar el volumen al agente (interfaz, ~3–8 min de indexación)
# MAGIC 1. Abre tu agente → **Configure → Sources → Add** → filtro **Volumes** → elige `documentos` de **tu**
# MAGIC    schema `pld_aml_<tu_usuario>` → **Confirm**.
# MAGIC 2. Al adjuntarlo, Databricks **activa content search automáticamente**: el volumen muestra *Indexing* y, al
# MAGIC    terminar, **Indexed** ("This volume's files are indexed and searchable by the agent").
# MAGIC 3. Con el lápiz ✏️ del volumen, pega la **descripción** de arriba.
# MAGIC 4. En **Instructions**, agrega al final la instrucción de fundamento.
# MAGIC
# MAGIC > Si agregas o cambias archivos después, vuelve a sincronizar desde la página del volumen en **Catalog**
# MAGIC > (sección *Content search* → **Sync now**).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 2 — Verificar la conexión (y camino alternativo por API)
# MAGIC Con el widget `modo` = `api`, la celda siguiente agrega el volumen y la instrucción a la configuración.
# MAGIC Ojo: por API el volumen queda adjunto, pero **content search no se activa solo**: abre después el agente en
# MAGIC la interfaz (Sources) para que empiece la indexación.

# COMMAND ----------

if dbutils.widgets.get("modo") == "api":
    cfg = leer_config(w, SPACE_ID)
    # la ruta del volumen managed y una descripción que le diga al agente qué contiene y cuándo usarlo.
    volumen = (VOLUME_PATH, DESCRIPCION_VOLUMEN)
    cfg["data_sources"]["volumes"] = [{"path": volumen[0], "description": [volumen[1]]}]
    textos = cfg.setdefault("instructions", {}).setdefault("text_instructions", [{"id": nuevo_id(), "content": []}])
    if INSTRUCCION_EXTRA not in textos[0]["content"]:
        textos[0]["content"].append(INSTRUCCION_EXTRA)
    guardar_agente(w, TITULO_AGENTE, None, cfg)
    print("✅ Volumen e instrucción agregados por API")

cfg = leer_config(w, SPACE_ID)
vols = [v["path"] for v in cfg.get("data_sources", {}).get("volumes", [])]
print("Volúmenes conectados:", vols or "(ninguno)")

# COMMAND ----------

# Expected output: ✅ El volumen documentos está conectado al agente
try:
    assert any(v.rstrip("/") == VOLUME_PATH for v in vols), f"El agente no tiene conectado {VOLUME_PATH}"
    print("✅ El volumen documentos está conectado al agente")
except AssertionError as e:
    print("❌ Casi:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 3 — Una pregunta solo de normativa
# MAGIC En la interfaz: elige **Agent** (no *Chat*) en la caja de pregunta y pregunta lo mismo. Fíjate en las **citas**:
# MAGIC en la interfaz muestran el archivo; por API llegan como IDs (`volume_file.file_…`) y la búsqueda en los
# MAGIC documentos aparece como la herramienta `search_context_files`.
# MAGIC Si recibes *"content search isn't ready"*, el volumen aún no dice **Indexed**: espera y reintenta.

# COMMAND ----------

res = preguntar_agente(w, SPACE_ID, "Según la política PLD, ¿cuál es el umbral del Reporte de Transacción en "
                                    "Efectivo (RTE) y qué artículo lo establece?")
mostrar(res)

# COMMAND ----------

# Expected output: ✅ Respondió USD 10,000 citando la política
try:
    assert not res["error"], res["error"]
    assert re.search(r"10[,.]?000", res["texto"]), "La respuesta no menciona el umbral de USD 10,000"
    assert "search_context_files" in res["herramientas"], "El agente no buscó en los documentos del volumen"
    assert res["citas"], "La respuesta no trae citas a documentos (¿el volumen dice Indexed?)"
    print("✅ Respondió USD 10,000 citando la política")
except AssertionError as e:
    print("❌ Casi:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 4 — El dictamen completo: datos + normativa
# MAGIC Ahora el agente debe combinar sus **funciones** (cifras de AT-001) con los **documentos** (fundamento).

# COMMAND ----------

# nombra la alerta (para que use las funciones) y pide el fundamento (para que lea la normativa).
PREGUNTA = ("Analiza la alerta AT-001: usa las funciones para obtener la alerta y sus señales, recomienda una "
            "disposición y fundaméntala citando la política PLD y el manual de tipologías.")
dictamen = preguntar_agente(w, SPACE_ID, PREGUNTA)
mostrar(dictamen)

# COMMAND ----------

# Expected output: ✅ Dictamen de AT-001: REPORTAR_ROS (o ESCALAR_INVESTIGACION), con cifras y citas
try:
    assert not dictamen["error"], dictamen["error"]
    disp = extraer_disposicion(dictamen["texto"])
    assert disp in ("REPORTAR_ROS", "ESCALAR_INVESTIGACION"), f"Esperaba REPORTAR_ROS o ESCALAR_INVESTIGACION, obtuve {disp}"
    assert dictamen["sql"], "El agente no consultó datos (¿mencionaste la alerta AT-001?)"
    assert "search_context_files" in dictamen["herramientas"] and dictamen["citas"], \
        "El dictamen no consultó ni citó la normativa del volumen"
    print(f"✅ Dictamen de AT-001: {disp}, con {len(dictamen['sql'])} consulta(s) y citas {dictamen['citas']}")
except AssertionError as e:
    print("❌ Casi:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resumen
# MAGIC - Conectaste la normativa **sin construir un pipeline de RAG**: content search lo gestiona.
# MAGIC - En **Agent mode**, el agente combinó **funciones de UC** (cifras) y **documentos** (fundamento) en un
# MAGIC   dictamen citado: el mismo resultado que el supervisor de la Sesión 2.
# MAGIC - Lo que cediste a cambio: el control fino del chunking, del modelo y del orden de los pasos.
# MAGIC
# MAGIC ➡️ `04_comparar_y_gobernar` (o `03_knowledge_assistant_legacy` si tu workspace no tiene la Beta de volúmenes).
# MAGIC
# MAGIC ## Glosario
# MAGIC | Término | Definición |
# MAGIC |---|---|
# MAGIC | **Content search** | Indexación gestionada de los archivos de un volumen (parseo con `ai_parse_document`). |
# MAGIC | **Source (volumen)** | Volumen de UC adjunto al agente; el agente lo lee con los permisos de quien pregunta. |
# MAGIC | **READ VOLUME** | Privilegio de UC que necesita cada usuario para que el agente le lea los documentos. |
# MAGIC | **Dictamen** | Disposición recomendada + señales + justificación + fundamento citado. |
