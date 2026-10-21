# Databricks notebook source
# MAGIC %md
# MAGIC # SOLUCIÓN · 05 · Reto (tarea) — Sanciones como regla dura, sin escribir el agente
# MAGIC
# MAGIC **Tiempo estimado:** 20–30 minutos, después de la sesión
# MAGIC
# MAGIC ## El problema
# MAGIC El cliente de **AT-003** (*Ramiro Quintanilla Rojas*) está en la **lista OFAC**. Tu agente todavía no lo sabe:
# MAGIC no tiene acceso a `lista_sanciones`. Y el instructivo es claro: *un hit confirmado en lista de sanciones se
# MAGIC bloquea y se escala de inmediato; nunca se cierra sin acción.*
# MAGIC
# MAGIC En la Sesión 2 resolviste esto con una herramienta **y** una regla en código. Hoy lo resolverás con:
# MAGIC 1. una **función de UC** que hace el cotejo (la lógica crítica sigue en código gobernado),
# MAGIC 2. la función conectada al agente + una **instrucción** de regla dura, y
# MAGIC 3. una pregunta de **benchmark** para que esta regla se evalúe siempre (antesala de la Sesión 4).
# MAGIC
# MAGIC > **Lección:** en low-code, las reglas que *no pueden fallar* van en una **función de UC** (código que tú
# MAGIC > controlas y Genie ejecuta), no solo en las instrucciones de texto.

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

# MAGIC %run ../utils/genie_utils

# COMMAND ----------

SPACE_ID = buscar_agente(w, TITULO_AGENTE)
assert SPACE_ID, f"No encontré tu agente '{TITULO_AGENTE}'."
display(spark.table(f"{FQ}.lista_sanciones"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 1 — La función `verificar_sanciones`
# MAGIC Recibe un `nombre` y devuelve las coincidencias **exactas o aproximadas** en `lista_sanciones` (los nombres
# MAGIC rara vez vienen escritos igual). **TODO:** completa la condición de coincidencia.
# MAGIC Pistas: `levenshtein(a, b)` mide cuántas letras hay que cambiar; usa `lower(...)` en ambos lados.

# COMMAND ----------

# SOLUCIÓN: Levenshtein ≤ 3 tolera errores de escritura; LIKE cubre nombres parciales.
spark.sql(f"""
CREATE OR REPLACE FUNCTION {FQ}.verificar_sanciones(
  nombre STRING COMMENT 'Nombre completo de la persona o empresa a verificar'
)
RETURNS TABLE (nombre_listado STRING, lista STRING, pais STRING, fecha_inclusion STRING, motivo STRING, distancia INT)
COMMENT 'Coteja un nombre contra las listas de sanciones (OFAC, ONU y listas locales). Una coincidencia obliga a bloquear la operación y escalar de inmediato.'
RETURN
  SELECT nombre_listado, lista, pais, fecha_inclusion, motivo,
         levenshtein(lower(nombre_listado), lower(verificar_sanciones.nombre)) AS distancia
  FROM {FQ}.lista_sanciones
  WHERE levenshtein(lower(nombre_listado), lower(verificar_sanciones.nombre)) <= 3
     OR lower(nombre_listado) LIKE concat('%', lower(verificar_sanciones.nombre), '%')
""")
display(spark.sql(f"SELECT * FROM {FQ}.verificar_sanciones('Ramiro Quintanila Rojas')"))

# COMMAND ----------

# Expected output: ✅ verificar_sanciones tolera errores de escritura y no da falsos positivos obvios
try:
    assert spark.sql(f"SELECT * FROM {FQ}.verificar_sanciones('Ramiro Quintanila Rojas')").count() >= 1, \
        "Debe tolerar errores de escritura (Quintanila con una sola l)"
    assert spark.sql(f"SELECT * FROM {FQ}.verificar_sanciones('Lucía Fernanda Castillo Mena')").count() == 0, \
        "Da un falso positivo con un cliente que no está en la lista"
    print("✅ verificar_sanciones tolera errores de escritura y no da falsos positivos obvios")
except AssertionError as e:
    print("❌ Casi:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 2 — Conectar la función y escribir la regla dura
# MAGIC **Interfaz:** agrega `verificar_sanciones` en **Configure → SQL functions** y suma la regla a **Instructions**.
# MAGIC La celda siguiente hace lo mismo por API. **TODO:** escribe la regla dura (una o dos oraciones).

# COMMAND ----------

# SOLUCIÓN: la regla nombra la función y la consecuencia exacta.
REGLA_SANCIONES = ("Regla dura de sanciones: verifica SIEMPRE el nombre del cliente con la función "
                   "verificar_sanciones. Si hay coincidencia, la disposición es ESCALAR_INVESTIGACION y nunca "
                   "CERRAR_SIN_ACCION; menciona la lista (por ejemplo OFAC) en el dictamen.")

cfg = leer_config(w, SPACE_ID)
ins = cfg.setdefault("instructions", {})
fn = f"{CATALOG}.{SCHEMA}.verificar_sanciones"
if fn not in {f["identifier"] for f in ins.get("sql_functions", [])}:
    ins.setdefault("sql_functions", []).append({"id": nuevo_id(), "identifier": fn})
    ins["sql_functions"].sort(key=lambda x: x["id"])
textos = ins.setdefault("text_instructions", [{"id": nuevo_id(), "content": []}])
if REGLA_SANCIONES not in textos[0]["content"]:
    textos[0]["content"].append(REGLA_SANCIONES)
guardar_agente(w, TITULO_AGENTE, None, cfg)
print("✅ Función y regla agregadas al agente")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 3 — Un benchmark para que la regla no se olvide
# MAGIC Los **benchmarks** son preguntas de prueba con su criterio de evaluación. Genie no los usa para responder;
# MAGIC sirven para **medir** al agente cada vez que cambias algo (los veremos a fondo en la Sesión 4).

# COMMAND ----------

cfg = leer_config(w, SPACE_ID)
preguntas = cfg.setdefault("benchmarks", {}).setdefault("questions", [])
TEXTO_BENCH = "Analiza la alerta AT-003 y recomienda una disposición."
if TEXTO_BENCH not in [q["question"][0] for q in preguntas]:
    preguntas.append({"id": nuevo_id(), "question": [TEXTO_BENCH], "answer": [{"format": "SQL", "content": []}],
                      "evaluation_note": ["Debe usar verificar_sanciones con el nombre del cliente, detectar la "
                                          "coincidencia OFAC y recomendar ESCALAR_INVESTIGACION. Rechazar si cierra "
                                          "sin acción o si no menciona la lista de sanciones."]})
    preguntas.sort(key=lambda x: x["id"])
guardar_agente(w, TITULO_AGENTE, None, cfg)
print(f"✅ Benchmarks del agente: {len(preguntas)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Paso 4 — Probar AT-003

# COMMAND ----------

res = preguntar_agente(w, SPACE_ID, TEXTO_BENCH)
mostrar(res)

# COMMAND ----------

# Expected output: ✅ AT-003 → ESCALAR_INVESTIGACION, usando verificar_sanciones y citando la lista OFAC
try:
    assert not res["error"], res["error"]
    assert "verificar_sanciones" in " ".join(res["sql"]).lower(), "El agente no llamó a verificar_sanciones"
    assert extraer_disposicion(res["texto"]) == "ESCALAR_INVESTIGACION", \
        f"Esperaba ESCALAR_INVESTIGACION, obtuve {extraer_disposicion(res['texto'])}"
    assert "OFAC" in res["texto"].upper(), "El dictamen no menciona la coincidencia en la lista OFAC"
    print("✅ AT-003 → ESCALAR_INVESTIGACION, usando verificar_sanciones y citando la lista OFAC")
except AssertionError as e:
    print("❌ Casi:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Para pensar
# MAGIC - ¿Qué pasaría si un analista sin `SELECT` sobre `lista_sanciones` usa el agente? (Pista: permisos por usuario.)
# MAGIC - La instrucción de texto **guía** al agente; ¿qué la **garantiza**? En la Sesión 2 era el código. Aquí, la
# MAGIC   función de UC hace el cotejo de forma determinística, pero la decisión de llamarla sigue siendo del agente:
# MAGIC   por eso existe el benchmark.
