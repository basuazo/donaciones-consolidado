import pandas as pd
import pyarrow.feather as feather
import json, re

print("Cargando arrowz...")
# Ahora lo lee directo y descomprime automáticamente
df = feather.read_feather('donaciones.arrowz')

df = df.dropna(subset=['dtr_key', 'dnt_key'])

print("Calculando agregados...")
donatarias = df.groupby('dtr_key').agg(nombre=('dtr_nombre', 'first'), rut=('dtr_key', 'first'), monto=('monto', 'sum'), n=('dtr_key', 'count'), n_donantes=('dnt_key', 'nunique')).reset_index(drop=True)
donatarias['key'] = donatarias['rut'].str.replace(r'[^0-9K]', '', regex=True)
donatarias = donatarias.sort_values('monto', ascending=False).head(300)

donantes = df.groupby('dnt_key').agg(nombre=('dnt_nombre', 'first'), rut=('dnt_key', 'first'), monto=('monto', 'sum'), n=('dnt_key', 'count'), n_donatarias=('dtr_key', 'nunique')).reset_index(drop=True)
donantes['key'] = donantes['rut'].str.replace(r'[^0-9K]', '', regex=True)
donantes = donantes.sort_values('monto', ascending=False).head(300)

print("Inyectando nombres en index.html...")
with open('index.html', 'r', encoding='utf-8') as f: html = f.read()
match = re.search(r'<script id="DATA" type="application/json">(.*?)</script>', html, re.DOTALL)

if match:
    data = json.loads(match.group(1))
    data['donatarias'] = donatarias.to_dict(orient='records')
    data['donantes_top'] = donantes.to_dict(orient='records')
    nuevo_html = html.replace(match.group(1), json.dumps(data, ensure_ascii=False))
    with open('index.html', 'w', encoding='utf-8') as f: f.write(nuevo_html)
    print("¡Éxito! index.html actualizado.")
else:
    print("Error: No se encontró el bloque DATA.")