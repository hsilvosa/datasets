# Archivo documental BOE y BORME

Consulta también `OPERATIONS.md` para pausar, recuperar una interrupción,
trasladar el archivo a otro disco y planificar su publicación en Hugging Face.

El piloto descarga las publicaciones entre el 1 de enero de 2023 y el 31 de
diciembre de 2025 y el catálogo completo de legislación consolidada. La fecha
de captura y la vigencia son distintas: una descarga actual no representa por
sí sola el estado histórico de una norma. Las fechas de las versiones se
conservan cuando la fuente las proporciona.

El archivo vive en `data/archive`, separado de las tablas anteriores. Su
manifiesto SQLite contiene los documentos, enlaces, recursos esperados,
versiones, observaciones HTTP, ejecuciones, errores y extracciones. Los originales
se guardan bajo `objects`, identificados por su SHA-256. Nunca se sustituyen por
el texto extraído. Las tablas Parquet conservan el documento de origen, URL,
hash, fecha de descarga, ejecución y versión del extractor.

## Instalación y ejecución

Desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[archive,dev]"
.\.venv\Scripts\python.exe -m boe_borme.archive run --config configs/archive-pilot.json
```

El mismo comando reanuda lo pendiente y permite ejecutar actualizaciones. Los
fallos se reintentan en una ejecución posterior. Se revisan los últimos días del
periodo y los recursos que llevan más de 30 días sin comprobarse. El catálogo
legislativo se consulta en cada ejecución; cuando cambia una norma se vuelven a
solicitar sus textos y metadatos. Las peticiones usan ETag y Last-Modified cuando
la fuente los facilita. Una respuesta idéntica no crea otra versión ni duplica
las extracciones. Cambiar de versión del extractor permite reprocesar los
originales almacenados.

La configuración permite ampliar las fechas conservando `root`. Para una
actualización hasta el día de ejecución se puede configurar `end_date: null`.
El piloto conserva su fecha final fija hasta que se decida ampliarlo.

## Progreso y comprobaciones

```powershell
.\.venv\Scripts\python.exe -m boe_borme.archive status --config configs/archive-pilot.json
.\.venv\Scripts\python.exe -m boe_borme.archive audit --config configs/archive-pilot.json
```

El progreso se guarda en `data/archive/artifacts/progress.json` y se informa
durante la ejecución. `audit` comprueba también los hashes de los originales y
los Parquet. La descarga, la extracción y la revisión son estados separados.
Una respuesta HTTP 404 de un documento es un recurso ausente, no una extracción
correcta. Los errores de red nunca se registran como días sin publicación.

No se declara `quality_status: pass` mientras haya recursos pendientes,
documentos sin texto, errores de extracción o incidencias sin resolver. Los
resultados de OCR, tablas detectadas y campos societarios extraídos son datos
derivados y necesitan revisión según su uso. Los casos OCR quedan explícitamente
pendientes de validación. Las cifras de la cola pueden crecer durante el proceso
porque cada documento puede descubrir anexos, traducciones e imágenes.

Si una interrupción del sistema deja `run.lock`, hay que comprobar el PID que
contiene antes de retirarlo; nunca se debe iniciar un segundo proceso sobre el
mismo archivo mientras el primero siga activo. Las escrituras de objetos y
Parquet son atómicas y el manifiesto usa transacciones con WAL.

## Tablas y uso en RAG

Las tablas bajo `tables` incluyen publicaciones, documentos, textos completos,
metadatos originales, estructura, bloques y versiones, páginas PDF, tablas,
imágenes, anexos, referencias, actos BORME y fragmentos RAG. Cada tabla tiene
campos de procedencia y `payload_json`, que conserva los campos específicos sin
descartar datos por no encajar en un esquema reducido.

Los fragmentos mantienen offsets exactos, documento, fuente y localización
cuando existe. El texto íntegro permanece en su propia tabla. El XML original
permite reconstruir formato y contenido que una representación plana no recoge.
Las páginas PDF conservan texto, bloques con coordenadas e información OCR. Las
imágenes incrustadas y los originales PDF permiten revisar gráficos y planos.

El manifiesto ofrece `current_records`, que selecciona las extracciones del
contenido actual de cada recurso, y `rag_chunks_current`, que además omite
versiones legislativas anteriores y fragmentos marcados como pendientes de
revisión. Los Parquet son históricos: no se deben concatenar sin filtrar
versiones para construir un índice actual. El índice de legislación se contrasta
con los bloques presentes en el XML completo; cada bloque ya incluido se registra
con su URL anunciada y su contenido, y se solicita por separado si falta.

## Alcance y pendientes de revisión

El inventario procede de los sumarios oficiales, XML documentales, cuerpos HTML
e índices de legislación. No incluye automáticamente los portales independientes
de subastas o notificaciones ni páginas externas citadas por una publicación.
Un recurso externo necesario se registra como incidencia. Los anexos binarios de
formatos sin extractor se conservan y quedan pendientes de revisión; conservar
un original no implica que todo su contenido esté listo para RAG.

La segmentación BORME conserva el acto íntegro y los campos extraídos con sus
fragmentos y offsets. Los valores ausentes no se inventan. Las referencias
entre normas y todos los metadatos del análisis se conservan en su forma original.

Antes del histórico se ejecutan pruebas sintéticas y una muestra real acotada:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m boe_borme.archive run --config configs/archive-smoke.json --max-requests 48
.\.venv\Scripts\python.exe scripts/archive_sample.py
```

La muestra usa `data/archive-smoke` y no cuenta como el piloto terminado.
