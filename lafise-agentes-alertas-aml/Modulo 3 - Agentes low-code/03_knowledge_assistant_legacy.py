# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · *(Opcional)* El camino anterior: Knowledge Assistant de Agent Bricks
# MAGIC
# MAGIC **Tiempo estimado:** 15 minutos (+ 5–15 min de indexación)
# MAGIC
# MAGIC ## ¿Por qué ver un producto *legacy*?
# MAGIC Hasta octubre de 2026, el camino low-code de Databricks eran los "bricks": **Knowledge Assistant** (preguntas
# MAGIC sobre documentos) y **Supervisor Agent** (orquestar varios agentes). Hoy son *legacy*: siguen funcionando y
# MAGIC tienen soporte, pero **no se recomiendan para agentes nuevos**; su reemplazo son los Genie Agents. Vale la pena
# MAGIC conocerlos porque:
# MAGIC - quizá ya existan en tu organización, y
# MAGIC - son el **plan B** si tu workspace no tiene la Beta de volúmenes en Genie Agents (notebook `02`).
# MAGIC
# MAGIC ## Objetivos
# MAGIC - Crear un **Knowledge Assistant (KA)** sobre el volumen de normativa PLD.
# MAGIC - Consultarlo **por API** (Responses API: campo `input`) y **validar** hechos y citas con 5 preguntas.
# MAGIC - Comparar su respuesta con la del Genie Agent del notebook `02`.

# COMMAND ----------

# MAGIC %pip install --quiet "databricks-sdk>=0.94.0"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import re, json, time
dbutils.widgets.text("catalog", "", "Catálogo asignado (REQUERIDO)")
dbutils.widgets.text("schema", "pld_aml", "Schema base")
dbutils.widgets.dropdown("modo", "ui", ["ui", "api"], "¿Cómo creas el asistente?")

user_email = spark.sql("SELECT current_user()").collect()[0][0]
user_prefix = re.sub(r"[^a-z0-9]", "_", user_email.split("@")[0].lower())
CATALOG = dbutils.widgets.get("catalog").strip()
assert CATALOG, "Escribe en el widget 'catalog' el mismo catálogo del 00_setup."
SCHEMA = f"{(dbutils.widgets.get('schema').strip() or 'pld_aml')}_{user_prefix}"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/documentos"
KA_NOMBRE = f"normativa-pld-{user_prefix.replace('_', '-')}"[:60]
KA_INSTRUCCIONES = ("Eres el asistente de normativa PLD de la Unidad de Cumplimiento. Responde en español, de forma "
                    "clara y breve, usando únicamente los documentos proporcionados. Cita siempre el documento y el "
                    "artículo o tipología. Si la respuesta no está en los documentos, dilo y no inventes.")

from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

print("Copia estos valores en el formulario del Knowledge Assistant:")
print("-" * 64)
print(f"Nombre        : {KA_NOMBRE}")
print(f"Descripción   : Responde preguntas sobre la normativa PLD del banco")
print(f"Fuente        : {VOLUME_PATH}/")
print(f"Instrucciones : {KA_INSTRUCCIONES}")
print("-" * 64)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 1 — Crear el asistente
# MAGIC **Interfaz** (adaptado del taller previo de Agent Bricks):
# MAGIC 1. Barra lateral → **Agents** → **Create Agent** → **Knowledge Assistant** (puede aparecer marcado como *legacy*).
# MAGIC 2. **Name** = el nombre impreso arriba; **Description** = "Responde preguntas sobre la normativa PLD del banco".
# MAGIC 3. **Knowledge sources → Add → Files in a Volume** → tu ruta `.../documentos/` → nombre "Normativa PLD".
# MAGIC 4. **Instructions** = las instrucciones impresas arriba → **Create**.
# MAGIC 5. Espera **5–15 min** a que indexe. La mejor señal de que está listo: responde en su chat de prueba.
# MAGIC
# MAGIC **API (widget `modo` = `api`):** la celda siguiente hace lo mismo con la API de Knowledge Assistants.

# COMMAND ----------

def buscar_ka(nombre):
    token = None
    while True:
        r = w.api_client.do("GET", "/api/2.1/knowledge-assistants", query={"page_token": token} if token else None)
        for ka in r.get("knowledge_assistants", []):
            if ka.get("display_name") == nombre:
                return ka
        token = r.get("next_page_token")
        if not token:
            return None

ka = buscar_ka(KA_NOMBRE)
if not ka and dbutils.widgets.get("modo") == "api":
    ka = w.api_client.do("POST", "/api/2.1/knowledge-assistants", body={
        "display_name": KA_NOMBRE, "description": "Responde preguntas sobre la normativa PLD del banco",
        "instructions": KA_INSTRUCCIONES})
    w.api_client.do("POST", f"/api/2.1/{ka['name']}/knowledge-sources", body={
        "display_name": "Normativa PLD", "description": "Política PLD, manual de tipologías e instructivo de alertas",
        "source_type": "files", "files": {"path": f"{VOLUME_PATH}/"}})
    w.api_client.do("POST", f"/api/2.1/{ka['name']}/knowledge-sources:sync")
    print("✅ Knowledge Assistant creado por API; empieza a indexar (5–15 min)")

assert ka, f"No encontré el asistente '{KA_NOMBRE}'. Créalo en la interfaz o cambia el widget 'modo' a 'api'."
KA_ENDPOINT = ka.get("endpoint_name")
print(f"Asistente: {ka['name']} · estado {ka.get('state')} · endpoint {KA_ENDPOINT}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 2 — Consultarlo por API
# MAGIC Un KA se sirve con la **Responses API**: la petición usa el campo **`input`** (no `messages`). El texto viene en
# MAGIC `output[].content[]` (`output_text`) y las **citas** en sus `annotations` (`url_citation`, con `title` = archivo).
# MAGIC

# COMMAND ----------

def parse_ka(resp):
    texto, citas = "", []
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    texto += c.get("text", "")
                    for a in c.get("annotations", []):
                        t = a.get("title") or a.get("url", "")
                        if t and t not in citas:
                            citas.append(t)
    return texto.strip(), citas

def preguntar_ka(pregunta):
    # un KA usa la Responses API; con {"messages": ...} responde "'messages' field is not supported".
    body = {"input": [{"role": "user", "content": pregunta}]}
    resp = w.api_client.do("POST", f"/serving-endpoints/{KA_ENDPOINT}/invocations", body=body)
    return parse_ka(resp)

texto, citas = None, None
for intento in range(20):                          # el endpoint puede estar READY antes que el índice
    try:
        texto, citas = preguntar_ka("¿Cuál es el umbral del Reporte de Transacción en Efectivo?")
        break
    except Exception as e:
        print(f"   aún no está listo ({str(e)[:90]}...); reintento en 30 s")
        time.sleep(30)
print("RESPUESTA:", texto)
print("CITAS:", citas)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 3 — Evaluar 5 preguntas de normativa (hecho esperado + documento citado)

# COMMAND ----------

PREGUNTAS_EVAL = [
    ("¿Cuál es el umbral para reportar una transacción en efectivo (RTE) a la UAF?", "10,000", "politica_pld_lafise"),
    ("¿En qué plazo debe remitirse un ROS a la UAF tras confirmar la sospecha?", "3 días hábiles", "politica_pld_lafise"),
    ("¿Por cuánto tiempo se conservan los registros de clientes y transacciones?", "5 años", "politica_pld_lafise"),
    ("¿Qué es la estructuración o pitufeo?", "10,000", "manual_tipologias"),
    ("¿Cuál es el plazo (SLA) máximo para analizar y disponer una alerta?", "15 días hábiles", "instructivo_alertas"),
]
norm = lambda s: re.sub(r"\s+", " ", s.lower().translate(str.maketrans("áéíóú", "aeiou")))

resultados = []
for q, hecho, doc in PREGUNTAS_EVAL:
    t, c = preguntar_ka(q)
    ok_hecho = norm(hecho) in norm(t) or norm(hecho).replace(",", "") in norm(t).replace(",", "")
    ok_cita = any(doc in x for x in c)
    resultados.append((ok_hecho, ok_cita))
    print(f"{'✅' if ok_hecho and ok_cita else '⚠️'} {q}\n    R: {t[:160]}\n    hecho: {ok_hecho} · cita {doc}: {ok_cita}")

# COMMAND ----------

# Expected output: ✅ 5/5 respuestas con el hecho correcto y cita a la fuente
try:
    hechos, citas_ok = sum(h for h, _ in resultados), sum(c for _, c in resultados)
    assert hechos >= 4, f"Solo {hechos}/5 respuestas contienen el hecho esperado"
    assert citas_ok >= 3, f"Solo {citas_ok}/5 respuestas citan el documento correcto"
    print(f"✅ {hechos}/5 respuestas correctas y {citas_ok}/5 con cita a la fuente")
except AssertionError as e:
    print("❌ Casi:", e, "· ¿Terminó de indexar? Revisa el estado del asistente.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 4 — KA vs Genie Agent: ¿qué cambió?
# MAGIC
# MAGIC | | Knowledge Assistant (legacy) | Genie Agent (actual) |
# MAGIC |---|---|---|
# MAGIC | Fuentes | Solo documentos (volumen o índice de AI Search) | Tablas, funciones de UC, volúmenes y MCP |
# MAGIC | Dictamen de una alerta | No: no ve las transacciones | Sí: combina datos y normativa |
# MAGIC | Varios agentes | Requería un **Supervisor Agent** (legacy) | Un solo agente con varias fuentes; para orquestación fina, código (Sesión 2) |
# MAGIC | Se sirve como | Endpoint de Model Serving (`ka-...-endpoint`) | API de Genie (Agent mode) |
# MAGIC | Estado | Legacy, con soporte | Recomendado para low-code |
# MAGIC
# MAGIC > **Limpieza:** si creaste el KA solo para probar, bórralo desde **Agents** (menú ⋮ → Delete) para liberar
# MAGIC > su endpoint.
# MAGIC
# MAGIC ➡️ `04_comparar_y_gobernar`.
# MAGIC
# MAGIC ## Glosario
# MAGIC | Término | Definición |
# MAGIC |---|---|
# MAGIC | **Knowledge Assistant (KA)** | Brick legacy de preguntas y respuestas sobre documentos (RAG gestionado). |
# MAGIC | **Supervisor Agent** | Brick legacy que orquestaba varios agentes (KA, Genie, funciones). |
# MAGIC | **Responses API** | Formato de petición `{"input": [...]}` con citas en `annotations`. |
# MAGIC | **Legacy** | Producto que sigue funcionando y con soporte, pero no recomendado para desarrollos nuevos. |
