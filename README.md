# Bootcamp de Agentes AML · Sesión 3: Agentes low-code sobre Databricks

Contenido práctico de la Sesión 3 del bootcamp de Agentes AML para el equipo de PLD de Grupo LAFISE: construir el
mismo **Agente de Alertas AML** de la Sesión 2, pero **sin programar el agente**, como un **Genie Agent** (antes
Genie Space) con las tablas de alertas, clientes y transacciones, las mismas funciones de Unity Catalog de la
Sesión 2, los documentos de la política PLD en un volumen e instrucciones de negocio.

> **Sobre los nombres (octubre 2026).** Agent Bricks es hoy la plataforma de Databricks para agentes escritos en
> código (Sesión 2). Para construir agentes sin código se recomiendan los **Genie Agents**. Knowledge Assistant y
> Supervisor Agent quedaron como *legacy*; se muestran en el notebook opcional `03`.

> Todos los datos del laboratorio son **100% sintéticos**. Nunca uses PII real en un workspace de laboratorio.

## Contenido

| Ruta | Qué es |
|---|---|
| `lafise-agentes-alertas-aml/00 - Course Overview` | Agenda y requisitos de la sesión |
| `lafise-agentes-alertas-aml/Modulo 3 - Agentes low-code/` | Notebooks `00_setup` a `04` (código completo) y `05_reto` (tarea), con `solutions/`, `data/` y `utils/` |
| `lafise-agentes-alertas-aml/requirements.txt` | Librerías (para instalarlas como librerías de clúster si no hay salida a PyPI) |
| `validacion/validacion_entorno_lafise_s3.py` | Notebook de validación de entorno |
| `build/lafise-agentes-alertas-aml-s3.dbc` | El mismo árbol de notebooks en un solo archivo, para importar en un clic |

## Requisitos

- Clúster clásico **DBR 17.3 LTS**, modo de acceso **Standard**, para ejecutar los notebooks.
- **SQL warehouse pro o serverless** con permiso `CAN USE` y el entitlement **Databricks SQL**: ahí corre el Genie Agent.
- Permiso para crear funciones y volúmenes en el schema `pld_aml_<usuario>` del catálogo de las Sesiones 1 y 2.
- Para la parte de documentos (notebook `02`): un administrador debe activar en **Settings → Previews** la Beta
  **Analyze Files in Volumes with Genie Agents**. Si no está disponible, el notebook `03` cubre los documentos.

## Cómo cargarlo en Databricks

**Opción A (recomendada): archivo `.dbc`.** Importa todo el árbol de notebooks en un clic.
1. Descargar el archivo desde este repositorio: abrir `build/lafise-agentes-alertas-aml-s3.dbc` y pulsar **Download raw file**
   (o usar el enlace directo
   `https://github.com/FerHrndz7/lafise-bootcamp-agentes-s3/raw/main/build/lafise-agentes-alertas-aml-s3.dbc`).
2. En el workspace: **Workspace → (carpeta destino) → Import → File** y subir el `.dbc`.
3. Abrir `lafise-agentes-alertas-aml/00 - Course Overview`.

**Opción B: Git folder.** No requiere descargar archivos.
1. En el workspace: **Workspace → Create → Git folder**.
2. URL: `https://github.com/FerHrndz7/lafise-bootcamp-agentes-s3`, proveedor **GitHub** (repositorio público, no
   requiere credenciales).

**Opción C: descargar el ZIP.** En GitHub: **Code → Download ZIP**, descomprimir e importar la carpeta
`lafise-agentes-alertas-aml` al workspace.

## Prueba completa antes de la sesión (30 a 40 min)

Con una **cuenta de asistente (no administrador)**:

1. `validacion/validacion_entorno_lafise_s3`: widget `catalog` = el catálogo de los asistentes; **Run all**.
2. `Modulo 3 - Agentes low-code/00_setup`: mismo `catalog`; dejar `schema` = `pld_aml` y `warehouse` vacío.
3. `01`: crear el Genie Agent en la interfaz con el título exacto que imprime el notebook (`Alertas PLD · <usuario>`),
   o poner el widget `modo` = `api` para que el notebook lo cree.
4. `02`: conectar el volumen `documentos` desde **Configure → Sources → Add** en el agente; esperar a que diga
   **Indexed** y ejecutar el notebook.
5. `04`: corre las 3 alertas testigo por API.

Resultado esperado: celdas de validación en ✅ (por ejemplo, `AT-001 → REPORTAR_ROS` o `ESCALAR_INVESTIGACION`,
`AT-002 → CERRAR_SIN_ACCION`). `03_knowledge_assistant_legacy` es opcional y `05_reto` es la tarea para después de la
sesión (su solución está en `solutions/`).
