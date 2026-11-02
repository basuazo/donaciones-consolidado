import pyarrow.feather as feather
import json, re
import pandas as pd

print("1. Cargando base enriquecida para extraer nombres...")
df = feather.read_feather('donaciones.arrowz')

# Limpiar ruts para armar un diccionario perfecto
df['dtr_clean'] = df['dtr_key'].astype(str).str.upper().str.replace(r'[^0-9K]', '', regex=True)
df['dnt_clean'] = df['dnt_key'].astype(str).str.upper().str.replace(r'[^0-9K]', '', regex=True)

# Armar un diccionario maestro { '12345678K': 'NOMBRE EMPRESA' }
dict_dtr = pd.Series(df['dtr_nombre'].values, index=df['dtr_clean']).dropna().to_dict()
dict_dnt = pd.Series(df['dnt_nombre'].values, index=df['dnt_clean']).dropna().to_dict()
diccionario = {**dict_dnt, **dict_dtr}
diccionario = {k: v for k, v in diccionario.items() if k and len(k) >= 6}

print("2. Actualizando index.html de forma quirúrgica...")
with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

match = re.search(r'<script id="DATA" type="application/json">(.*?)</script>', html, re.DOTALL)
if match:
    data = json.loads(match.group(1))
    
    # Reemplazar RUTs por Nombres en Donatarias y sus top donantes
    for d in data.get('donatarias', []):
        if d.get('key') in diccionario:
            d['nombre'] = diccionario[d['key']]
        for td in d.get('top_donantes', []):
            posible_rut = re.sub(r'[^0-9K]', '', str(td.get('nombre', '')).upper())
            if posible_rut in diccionario:
                td['nombre'] = diccionario[posible_rut]

    # Reemplazar RUTs por Nombres en Donantes y sus top donatarias
    for d in data.get('donantes_top', []):
        if d.get('key') in diccionario:
            d['nombre'] = diccionario[d['key']]
        for td in d.get('top_donatarias', []):
            posible_rut = re.sub(r'[^0-9K]', '', str(td.get('nombre', '')).upper())
            if posible_rut in diccionario:
                td['nombre'] = diccionario[posible_rut]

    # Guardar devolviendo el JSON intacto
    nuevo_json = json.dumps(data, ensure_ascii=False)
    nuevo_html = html.replace(match.group(1), nuevo_json)
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(nuevo_html)
    print("¡Éxito! Nombres inyectados sin romper el código.")
else:
    print("Error: No se encontró el bloque DATA en el HTML.")