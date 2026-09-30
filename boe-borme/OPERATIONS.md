# Guardar, reanudar y ampliar el archivo documental

## Estado y alcance

El piloto 2023–2025 está incompleto y se ha pausado por petición del usuario.
Los originales y el trabajo pendiente se conservan en `data/archive`. No hay
que empezar de cero. El seguimiento automático también está pausado.

La implementación adquiere los recursos descubiertos en los sumarios y el
catálogo consolidado, conserva originales, textos completos y procedencia, y
exporta tablas históricas. No sustituye textos por resúmenes. No constituye
todavía un RAG validado: falta terminar la adquisición, revisar OCR y anexos
problemáticos, y construir el índice de búsqueda o embeddings.

## Reanudar cuando haya espacio

Desde `D:\datasets\boe-borme`:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[archive,dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m boe_borme.archive status --config configs/archive-pilot.json
.\scripts\start-archive.ps1
```

El ejecutor vuelve a comprobar recursos según su antigüedad, pero una respuesta
idéntica no duplica el contenido. Los cambios añaden versiones. El mismo `root`
es imprescindible para continuar este archivo. No se necesita Hugging Face
para descargar ni procesar. El seguimiento en la aplicación debe reactivarse
por separado si se desean nuevos informes.

## Pausar y recuperar

```powershell
.\.venv\Scripts\python.exe -m boe_borme.archive pause --config configs/archive-pilot.json
```

La pausa cooperativa se comprueba entre lotes: deja terminar el lote y exporta
lo procesado antes de salir. Puede tardar mientras una petición agota sus
reintentos. No es una terminación inmediata. Comprueba que desaparezca
`data/archive/run.lock` y que la última ejecución indique `paused_by_user`.
Una nueva ejecución elimina la petición de pausa anterior.

Después de un corte de corriente o una terminación forzada:

```powershell
.\.venv\Scripts\python.exe -m boe_borme.archive recover --config configs/archive-pilot.json
.\.venv\Scripts\python.exe -m boe_borme.archive export --config configs/archive-pilot.json
.\.venv\Scripts\python.exe -m boe_borme.archive audit --config configs/archive-pilot.json
```

`recover` se niega si el PID del bloqueo sigue existiendo o no puede verificarlo.
No borra originales ni reinicia la cola. SQLite revierte transacciones no
confirmadas. Puede quedar algún temporal no registrado tras una interrupción;
no lo uses como documento ni lo confundas con un original confirmado.

## Copia de seguridad y cambio de disco

Primero pausa y espera a que el proceso salga. Copia el proyecto, su configuración
y **todo** `data/archive`, incluidos `manifest.sqlite`, cualquier archivo WAL
o SHM existente, `objects`, `tables` y `artifacts`. No copies solo los Parquet:
perderías originales, cola, versiones y trazabilidad. No copies la base SQLite
en vivo con una copia ordinaria de archivos.

En otro equipo crea una nueva `.venv` e instala las dependencias; no reutilices
la carpeta del entorno virtual anterior. Ajusta `root` y `legacy_raw` en el JSON
si cambian las rutas. Las rutas internas del archivo son relativas a `root`.
Audita la copia antes de borrar el original. Conserva una copia del código y de
las versiones de dependencias utilizadas junto con cada entrega.

## Ampliar periodos

Copia la configuración del piloto a otro JSON dentro de `configs`, conserva
`root: data/archive` y amplía `start_date` o `end_date`. Ejecuta con `--config`
apuntando a ese JSON. `end_date: null` significa hasta la fecha de ejecución.
Para añadir años antiguos conviene hacerlo por tramos y auditar cada uno.

El alcance histórico del API no equivale a todos los fondos del BOE: los
sumarios BOE comienzan en septiembre de 1960 y los BORME en enero de 2009.
La configuración actual comparte fecha inicial para ambas publicaciones;
un tramo anterior a 2009 hará consultas BORME sin edición. Los fondos anteriores,
como Gazeta, requieren otro inventario y no se deben anunciar como incluidos.

## Espacio y límites reales

No hay actualmente un límite automático de 100 GB ni garantía de tamaño final.
Los originales, SQLite, Parquet, imágenes y temporales consumen espacio; la
cifra `archived_bytes` mide respuestas archivadas y no el tamaño físico total.
Reserva margen para exportaciones, WAL y reprocesamiento. No inicies un tramo
que apenas quepa en el espacio disponible. `--max-requests 48` permite una
ejecución acotada por peticiones, no por bytes ni tiempo ni número de extracciones.

Reducir formatos o años es una decisión de cobertura, no una optimización ya
aplicada. Ningún recurso pendiente se considera completo por alcanzar un límite.

## Hugging Face

Mantener `hsilvosa/boe-borme`: sus sumarios históricos y textos consolidados
siguen siendo útiles y no son el espejo documental de cada publicación.
Mantener `hsilvosa/boe-borme-detailed`: es una derivación por bloques y versiones
de la legislación del primero, no de todos los documentos BOE/BORME.

El nuevo archivo no debe reemplazar esos esquemas ni reducir silenciosamente
su cobertura a tres años. Cuando esté validado, preparar una entrega separada,
por ejemplo `hsilvosa/boe-borme-archive` (nombre propuesto, no creado), con fechas,
alcance, versión del extractor, checksums, incidencias y condiciones de reutilización.
Un subconjunto RAG debe identificar expresamente qué excluye y cómo selecciona
versiones actuales. No subir directamente `data/archive`: contiene estado interno,
logs y extracciones históricas que requieren selección y documentación.

El comando `stage` del pipeline antiguo no publica el nuevo archivo. Todavía
no existe un empaquetador de publicación específico para él. Antes de una
publicación completa, exigir auditoría íntegra sin pendientes y revisión de
OCR y formatos no extraídos. Si se decide publicar una muestra parcial, etiquetarla
como parcial, nunca como archivo completo. Las fichas publicadas del dataset base
y del derivado detallado incluyen un aviso de cobertura al principio. Esa
aclaración documental no incorpora el piloto ni modifica los archivos de datos.
