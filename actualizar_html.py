import pandas as pd
import pyarrow.feather as feather
import pyarrow as pa
import gzip
import json
import re

ARCHIVO_DONACIONES = 'donaciones.arrowz'
ARCHIVO_HTML = 'index.html'

print("1. Cargando base de datos enriquecida...")
try:
    with pa.memory_map(ARCHIVO_DONACIONES, 'r') as source:
        df = pa.ipc.open_stream(source).read_all().to_pandas()
except Exception:
    try:
        with gzip.open(ARCHIVO_DONACIONES, 'rb') as f:
            df = pa.ipc.open_stream(f).read_all().to_pandas()
    except Exception:
        df = feather.read_feather(ARCHIVO_DONACIONES)

# Limpiar RUTs vacíos para evitar errores
df = df.dropna(subset=['dtr_key', 'dnt_key'])

print("2. Calculando agregados para donatarias...")
# Agrupar por RUT de donataria, pero usando el nombre enriquecido
donatarias_agg = df.groupby('dtr_key').agg(
    nombre=('dtr_nombre', 'first'),
    rut=('dtr_key', 'first'),
    monto=('monto', 'sum'),
    n=('dtr_key', 'count'),
    n_donantes=('dnt_key', 'nunique'),
).reset_index(drop=True)
donatarias_agg['key'] = donatarias_agg['rut'].str.replace(r'[^0-9K]', '', regex=True)

# Quedarse con el Top 300 para no hacer tan pesado el HTML
top_donatarias = donatarias_agg.sort_values('monto', ascending=False).head(300)

print("3. Calculando agregados para donantes...")
# Agrupar por RUT de donante, usando su nombre enriquecido
donantes_agg = df.groupby('dnt_key').agg(
    nombre=('dnt_nombre', 'first'),
    rut=('dnt_key', 'first'),
    monto=('monto', 'sum'),
    n=('dnt_key', 'count'),
    n_donatarias=('dtr_key', 'nunique'),
).reset_index(drop=True)
donantes_agg['key'] = donantes_agg['rut'].str.replace(r'[^0-9K]', '', regex=True)
top_donantes = donantes_agg.sort_values('monto', ascending=False).head(300)

# ==========================================
# REEMPLAZAR EL BLOQUE EN EL HTML
# ==========================================
print("4. Actualizando index.html...")
with open(ARCHIVO_HTML, 'r', encoding='utf-8') as f:
    html_content = f.read()

# Extraer el JSON actual
match = re.search(r'<script id="DATA" type="application/json">(.*?)</script>', html_content, re.DOTALL)
if match:
    data_json = json.loads(match.group(1))
    
    # Sobrescribir con los nombres actualizados
    data_json['donatarias'] = top_donatarias.to_dict(orient='records')
    data_json['donantes_top'] = top_donantes.to_dict(orient='records')
    
    # Inyectar el JSON nuevo en el HTML
    nuevo_json_str = json.dumps(data_json, ensure_ascii=False)
    nuevo_html = html_content.replace(match.group(1), nuevo_json_str)
    
    with open('index_actualizado.html', 'w', encoding='utf-8') as f:
        f.write(nuevo_html)
    print("¡Listo! Se ha creado 'index_actualizado.html' con los nombres enriquecidos.")
else:
    print("Error: No se encontró el bloque <script id='DATA'> en el HTML.")