# Databricks notebook source
# MAGIC %md
# MAGIC # LAFISE — Bootcamp de Agentes AML · Sesión 3
# MAGIC ## Agentes low-code: el mismo Agente de Alertas, sin programar el agente
# MAGIC
# MAGIC En la **Sesión 1** construimos la **base de conocimiento** (política PLD, tipologías y precedentes) y en la
# MAGIC **Sesión 2** programamos el **Agente de Alertas** con LangGraph y funciones de Unity Catalog. Hoy construimos
# MAGIC **el mismo agente sin escribir su código**: un **Genie Agent** con las tablas, las mismas funciones de UC, los
# MAGIC documentos de la política e instrucciones de negocio. Al final comparamos ambos caminos.
# MAGIC
# MAGIC > **Sobre los nombres (octubre 2026).** En el plan del bootcamp esta sesión se llamaba *Agent Bricks (low-code)*.
# MAGIC > Hoy **Agent Bricks** es la plataforma para agentes **en código** (Sesión 2) y el camino **sin código**
# MAGIC > recomendado son los **Genie Agents** (antes *Genie Spaces*). Los bricks originales, **Knowledge Assistant** y
# MAGIC > **Supervisor Agent**, quedaron como *legacy*: los vemos en el notebook opcional `03`.

# COMMAND ----------

# MAGIC %md-sandbox
# MAGIC ## A. Aviso
# MAGIC
# MAGIC <div style="border-left: 4px solid #f44336; background: #ffebee; padding: 14px 18px; border-radius: 4px; margin: 16px 0;">
# MAGIC <strong style="display:block; color:#c62828; margin-bottom:6px; font-size: 1.1em;">Solo laboratorio · datos sintéticos</strong>
# MAGIC <div style="color:#333;">
# MAGIC <ul>
# MAGIC <li>Ejecuta esta práctica únicamente en el <strong>workspace de laboratorio</strong> proporcionado.</li>
# MAGIC <li>Clientes, transacciones, alertas y listas de sanciones son <strong>sintéticos</strong>. <strong>Nunca</strong> uses PII real de clientes de LAFISE.</li>
# MAGIC <li>El agente <strong>recomienda</strong>; la decisión final siempre es del analista humano. Los umbrales y plazos son <strong>didácticos</strong>, no asesoría de cumplimiento.</li>
# MAGIC </ul>
# MAGIC </div>
# MAGIC </div>

# COMMAND ----------

# MAGIC %md-sandbox
# MAGIC ## B. Recorrido de la sesión (1 h 30 min)
# MAGIC
# MAGIC <div style="max-width: 1200px; margin: 0 auto; font-family: sans-serif;">
# MAGIC <div style="background: #F9F7F4; border-radius: 10px; padding: 20px 24px; box-shadow: 0 2px 8px rgba(27,49,57,0.06);">
# MAGIC <style>.agenda-table td, .agenda-table th { font-size: 14pt !important; }</style>
# MAGIC <table class="agenda-table" style="width: 100%; border-collapse: collapse; line-height: 1.5;">
# MAGIC   <thead>
# MAGIC      <tr style="background: #1B5162; color: white;">
# MAGIC       <th style="padding: 10px 14px; text-align: center; border: 1px solid #EEEDE9; width: 60px;">#</th>
# MAGIC       <th style="padding: 10px 14px; text-align: center; border: 1px solid #EEEDE9; width: 90px;">Tiempo</th>
# MAGIC       <th style="padding: 10px 14px; text-align: left; border: 1px solid #EEEDE9;">Notebook</th>
# MAGIC      </tr>
# MAGIC   </thead>
# MAGIC   <tbody>
# MAGIC      <tr style="background: white;"><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center; font-weight:700; color:#1B5162;">—</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center;">10 min</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9;">Introducción del facilitador: agentes low-code y cuándo usarlos</td></tr>
# MAGIC      <tr style="background: #FBFAF8;"><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center; font-weight:700; color:#1B5162;">00</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center;">8 min</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9;">Preparación: datos de las Sesiones 1 y 2, documentos y funciones de UC</td></tr>
# MAGIC      <tr style="background: white;"><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center; font-weight:700; color:#1B5162;">01</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center;">20 min</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9;">Genie Agent sobre tablas + funciones de UC + instrucciones</td></tr>
# MAGIC      <tr style="background: #FBFAF8;"><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center; font-weight:700; color:#1B5162;">02</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center;">20 min</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9;">Documentos de la política (content search) y dictamen citado en <em>Agent mode</em></td></tr>
# MAGIC      <tr style="background: white;"><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center; font-weight:700; color:#1B5162;">03</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center;">Opcional</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9;">El camino anterior: Knowledge Assistant (legacy). Plan B si no hay Beta de volúmenes</td></tr>
# MAGIC      <tr style="background: #FBFAF8;"><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center; font-weight:700; color:#1B5162;">04</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center;">15 min</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9;">Comparar con la Sesión 2 y gobernar: permisos, datos por usuario, cuándo usar cada camino</td></tr>
# MAGIC      <tr style="background: white;"><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center; font-weight:700; color:#1B5162;">05</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9; text-align:center;">Tarea</td><td style="padding: 8px 14px; border: 1px solid #EEEDE9;">Reto: sanciones como regla dura con una función de UC y un benchmark</td></tr>
# MAGIC   </tbody>
# MAGIC </table>
# MAGIC </div>
# MAGIC </div>
# MAGIC
# MAGIC Empieza en `Modulo 3 - Agentes low-code/00_setup`. La creación del agente es **en la interfaz**; los notebooks
# MAGIC te dan los valores a copiar y **validan por API** lo que hiciste (cada uno trae un modo `api` de respaldo).
# MAGIC El `05_reto` es la tarea para después de la sesión (su solución está en `solutions/`).

# COMMAND ----------

# MAGIC %md-sandbox
# MAGIC ## C. Requisitos
# MAGIC
# MAGIC <div style="border-left: 4px solid #1976d2; background: #e3f2fd; padding: 14px 18px; border-radius: 4px; margin: 16px 0;">
# MAGIC <div style="color:#333;">
# MAGIC
# MAGIC - Conecta un **clúster clásico** (DBR **17.3 LTS**, modo de acceso *Standard*) para ejecutar los notebooks.
# MAGIC - En el widget **catalog** escribe el **mismo catálogo de las Sesiones 1 y 2**.
# MAGIC - Necesitas **CAN USE** sobre un **SQL warehouse pro o serverless** y el entitlement **Databricks SQL**:
# MAGIC   ahí corren las consultas del Genie Agent.
# MAGIC - Para la parte de documentos (notebook `02`), un admin debe activar en *Previews* la Beta
# MAGIC   **Analyze Files in Volumes with Genie Agents**. Si no está disponible, usa el notebook `03`.
# MAGIC - Usa **Chrome o Firefox** (no Safari), sin modo Incógnito.
# MAGIC - Todo se valida antes de la sesión con el notebook de validación de entorno.
# MAGIC
# MAGIC </div>
# MAGIC </div>

# COMMAND ----------

# MAGIC %md
# MAGIC &copy; 2026 Databricks, Inc. Todos los derechos reservados.
