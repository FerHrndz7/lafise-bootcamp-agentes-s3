# Databricks notebook source
# MAGIC %md
# MAGIC # Utilidades — Genie Agents y Knowledge Assistant (Sesión 3)
# MAGIC
# MAGIC Funciones de apoyo que usan los notebooks `01`–`05`. **No necesitas modificarlas.**
# MAGIC
# MAGIC | Función | Para qué |
# MAGIC |---|---|
# MAGIC | `elegir_warehouse(w, preferido)` | Elige un SQL warehouse pro/serverless para el agente |
# MAGIC | `buscar_agente(w, titulo)` | Encuentra tu Genie Agent por título y devuelve su `space_id` |
# MAGIC | `leer_config(w, space_id)` | Lee la configuración del agente (`serialized_space`) como diccionario |
# MAGIC | `construir_config(...)` | Arma la configuración de un agente (tablas, funciones, instrucciones, volúmenes) |
# MAGIC | `guardar_agente(w, ...)` | Crea o actualiza el agente con esa configuración |
# MAGIC | `preguntar_agente(w, space_id, pregunta)` | Pregunta en **Agent mode** y devuelve texto, SQL ejecutado y citas |
# MAGIC | `extraer_disposicion(texto)` | Encuentra la disposición recomendada en la respuesta |

# COMMAND ----------

import json, re, time, uuid

DISPOSICIONES = ["CERRAR_SIN_ACCION", "SOLICITAR_INFORMACION", "ESCALAR_INVESTIGACION", "REPORTAR_ROS"]


def nuevo_id():
    """IDs de 32 caracteres hexadecimales que exige la configuración de Genie."""
    return uuid.uuid4().hex


def elegir_warehouse(w, preferido=""):
    """Devuelve el id de un SQL warehouse PRO o serverless (Genie no funciona con warehouses clásicos)."""
    whs = list(w.warehouses.list())
    if preferido:
        for x in whs:
            if preferido in (x.id, x.name):
                return x.id
        raise ValueError(f"No encontré el warehouse '{preferido}'. Disponibles: {[x.name for x in whs]}")
    aptos = [x for x in whs if x.enable_serverless_compute or str(x.warehouse_type).endswith("PRO")]
    if not aptos:
        raise RuntimeError("No hay SQL warehouses PRO o serverless visibles. Pide CAN USE sobre uno al administrador.")
    aptos.sort(key=lambda x: (str(x.state) not in ("State.RUNNING", "RUNNING"), not x.enable_serverless_compute))
    return aptos[0].id


def buscar_agente(w, titulo):
    """Busca un Genie Agent por título exacto (recorre todas las páginas). Devuelve space_id o None."""
    token = None
    while True:
        q = {"page_size": 100}
        if token:
            q["page_token"] = token
        r = w.api_client.do("GET", "/api/2.0/genie/spaces", query=q)
        for s in r.get("spaces", []):
            if s.get("title") == titulo:
                return s["space_id"]
        token = r.get("next_page_token")
        if not token:
            return None


def leer_config(w, space_id):
    r = w.api_client.do("GET", f"/api/2.0/genie/spaces/{space_id}", query={"include_serialized_space": "true"})
    return json.loads(r.get("serialized_space") or "{}")


def construir_config(tablas, funciones=(), instrucciones=(), preguntas=(), volumenes=(), ejemplos_sql=()):
    """Arma el serialized_space (versión 2). Genie exige ids de 32 hex y listas ordenadas."""
    cfg = {"version": 2,
           "data_sources": {"tables": sorted([{"identifier": t} for t in tablas], key=lambda x: x["identifier"])}}
    if volumenes:
        cfg["data_sources"]["volumes"] = [{"path": p, "description": [d]} for p, d in volumenes]
    if preguntas:
        cfg["config"] = {"sample_questions": sorted([{"id": nuevo_id(), "question": [q]} for q in preguntas],
                                                    key=lambda x: x["id"])}
    ins = {}
    if instrucciones:
        ins["text_instructions"] = [{"id": nuevo_id(), "content": list(instrucciones)}]
    if funciones:
        ins["sql_functions"] = sorted([{"id": nuevo_id(), "identifier": f} for f in funciones], key=lambda x: x["id"])
    if ejemplos_sql:
        ins["example_question_sqls"] = sorted([{"id": nuevo_id(), "question": [q], "sql": [s]} for q, s in ejemplos_sql],
                                              key=lambda x: x["id"])
    if ins:
        cfg["instructions"] = ins
    return cfg


def guardar_agente(w, titulo, warehouse_id, config, descripcion=""):
    """Crea el agente si no existe (por título) o actualiza su configuración. Devuelve space_id."""
    sid = buscar_agente(w, titulo)
    body = {"serialized_space": json.dumps(config, ensure_ascii=False)}
    if sid:
        w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{sid}", body=body)
        return sid
    body.update({"warehouse_id": warehouse_id, "title": titulo, "description": descripcion})
    return w.api_client.do("POST", "/api/2.0/genie/spaces", body=body)["space_id"]


def preguntar_agente(w, space_id, pregunta, conversation_id=None):
    """Pregunta al agente en Agent mode (razonamiento de varios pasos, documentos, funciones).

    Devuelve un diccionario con: texto (respuesta final), sql (consultas ejecutadas), herramientas (llamadas que hizo,
    p. ej. search_context_files = búsqueda en los documentos del volumen), citas (documentos citados: por API llegan
    como IDs `volume_file.file_…`; en la interfaz se ven con el nombre del archivo), conversation_id y error."""
    from databricks_openai import DatabricksOpenAI
    host = w.config.host.rstrip("/")
    cliente = DatabricksOpenAI(workspace_client=w)
    cliente.base_url = f"{host}/api/2.0/genie/agents/{space_id}"
    extra = {"conversation_id": conversation_id} if conversation_id else None
    res = {"texto": "", "sql": [], "herramientas": [], "citas": [], "conversation_id": conversation_id, "error": None}
    inicio = time.time()
    stream = cliente.responses.create(
        model="genie-agent", stream=True, extra_body=extra,
        input=[{"type": "message", "role": "user", "content": [{"type": "input_text", "text": pregunta}]}])
    for ev in stream:
        if ev.type == "response.failed":
            err = ev.response.error
            res["error"] = getattr(err, "message", str(err))
        if ev.type == "response.completed":
            d = ev.response.model_dump(warnings=False)
            res["conversation_id"] = d.get("conversation_id") or res["conversation_id"]
            for it in d.get("output", []):
                if it.get("type") == "function_call":
                    res["herramientas"].append(it.get("name"))
                    try:
                        sql = json.loads(it.get("arguments") or "{}").get("sql")
                    except Exception:
                        sql = None
                    if sql:
                        res["sql"].append(sql)
                if it.get("type") == "message":
                    for c in it.get("content", []):
                        if c.get("type") == "output_text" and not (c.get("metadata") or {}).get("sql"):
                            res["texto"] += c.get("text", "") + "\n"
                        for a in c.get("annotations") or []:
                            t = a.get("title") or a.get("url") or a.get("file_id")
                            if t and t not in res["citas"]:
                                res["citas"].append(t)
    for cid in re.findall(r":citation\[([^\]]+)\]", res["texto"]):
        if cid not in res["citas"]:
            res["citas"].append(cid)
    res["texto"] = re.sub(r"\s*:citation\[[^\]]+\]", " [cita]", res["texto"]).strip()
    res["segundos"] = round(time.time() - inicio)
    if not res["citas"]:                       # algunas respuestas citan el archivo solo dentro del texto
        res["citas"] = sorted(set(re.findall(r"[\w\-]+\.(?:pdf|docx)", res["texto"])))
    return res


def extraer_disposicion(texto):
    """Devuelve la primera disposición válida mencionada en el texto (o None)."""
    patron = r"(?<![A-Z])(" + "|".join(DISPOSICIONES) + r")(?![A-Z])"
    t = (texto or "").upper()
    m = re.search(patron, t) or re.search(patron, re.sub(r"(?<=[A-ZÁÉÍÓÚ]) (?=[A-ZÁÉÍÓÚ])", "_", t)
                                          .replace("ACCIÓN", "ACCION").replace("INFORMACIÓN", "INFORMACION")
                                          .replace("INVESTIGACIÓN", "INVESTIGACION"))
    return m.group(1) if m else None


def mostrar(res, max_chars=2500):
    if res.get("error"):
        print("❌ Error:", res["error"])
        return
    print(res["texto"][:max_chars])
    print("\n— SQL ejecutado por el agente:", len(res["sql"]), "consulta(s)")
    for s in res["sql"]:
        print("   ", s[:160].replace("\n", " "))
    print("— Herramientas usadas:", sorted(set(res.get("herramientas", []))) or "(ninguna)")
    print("— Citas a documentos:", len(res["citas"]), res["citas"][:5])
    print(f"— Tiempo: {res.get('segundos', '?')} s")
