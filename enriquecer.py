#!/usr/bin/env python3
"""Enriquece nombres de donatarias/donantes usando el SII e instituciones.

Lee donaciones.arrowz, cruza dtr_key/dnt_key con el SII (PUB_NOMBRES_PJ.txt)
e instituciones.csv, completa los nombres faltantes y guarda de vuelta.
"""

import gzip
import os
import re
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather

ARCHIVO_DONACIONES = "donaciones.arrowz"
PATHS_SII = [
    os.path.join("..", "TEST", "PUB_NOMBRES_PJ.txt"),
    "PUB_NOMBRES_PJ.txt",
]
PATHS_INST = [
    os.path.join("..", "TEST", "instituciones.csv"),
    "instituciones.csv",
]


def limpiar_rut(rut):
    if pd.isna(rut):
        return None
    rut_limpio = re.sub(r"[^0-9K]", "", str(rut).upper())
    return rut_limpio if rut_limpio else None


def cargar_csv(path, columnas):
    print(f"   Leyendo {path}…", flush=True)
    ext = os.path.splitext(path)[1]
    if ext == ".xlsx":
        return pd.read_excel(path, dtype=str)
    return pd.read_csv(path, sep=None, engine="python", dtype=str, encoding="latin1", on_bad_lines="skip")


def encontrar_archivo(paths):
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


def _dict_nombres(df, col_rut, col_nombre):
    """Arma un diccionario {RUT_limpio: nombre_first_nonnull}."""
    work = df[[col_rut, col_nombre]].dropna(subset=[col_rut, col_nombre]).copy()
    work = work.drop_duplicates(subset=[col_rut])
    return dict(zip(work[col_rut], work[col_nombre]))


def main():
    print("1. Cargando donaciones.arrowz…", flush=True)
    df = pd.read_feather(ARCHIVO_DONACIONES)
    df["dtr_key"] = df["dtr_key"].astype(str)
    df["dnt_key"] = df["dnt_key"].astype(str)
    print(f"   {len(df):,} registros".replace(",", "."))

    # limpiar RUTs para cruce
    df["rut_dtr_clean"] = df["dtr_key"].apply(limpiar_rut)
    df["rut_dnt_clean"] = df["dnt_key"].apply(limpiar_rut)

    # Cargar archivos complementarios
    ruta_sii = encontrar_archivo(PATHS_SII)
    ruta_inst = encontrar_archivo(PATHS_INST)

    diccionario_nombres = {}

    if ruta_inst:
        print(f"2. Cargando {os.path.basename(ruta_inst)}…", flush=True)
        inst = cargar_csv(ruta_inst, None)
        col_rut = [c for c in inst.columns if "rut" in c.lower()]
        col_nom = [c for c in inst.columns if "razon" in c.lower() or "nombre" in c.lower()]
        if col_rut and col_nom:
            col_rut = col_rut[0]
            col_nom = col_nom[0]
            print(f"   Columnas: RUT={col_rut}, Nombre={col_nom}")
            d = _dict_nombres(inst, col_rut, col_nom)
            d = {limpiar_rut(k): v for k, v in d.items() if k and len(str(k)) >= 6}
            diccionario_nombres.update(d)
            print(f"   {len(d)} nombres desde instituciones")
    else:
        print("2. instituciones.csv no encontrado (opcional)")

    if ruta_sii:
        print(f"3. Cargando {os.path.basename(ruta_sii)}…", flush=True)
        sii = cargar_csv(ruta_sii, None)
        col_rut = sii.columns[0]  # 'RUT'
        col_nom = [c for c in sii.columns if "razon" in c.lower() or "nombre" in c.lower()]
        if col_nom:
            col_nom = col_nom[0]
            # Si hay columna DV separada, combinar RUT+DV
            col_dv = [c for c in sii.columns if c.lower() in ("dv", "digito")]
            if col_dv:
                col_dv = col_dv[0]
                sii["_rut_completo"] = (
                    sii[col_rut].fillna("").astype(str).str.replace(r"[^0-9]", "", regex=True)
                    + sii[col_dv].fillna("").astype(str).str.upper().str.replace(r"[^0-9K]", "", regex=True)
                )
                llave = "_rut_completo"
            else:
                llave = col_rut
            print(f"   Columnas: RUT={llave}, Nombre={col_nom}")
            d = _dict_nombres(sii, llave, col_nom)
            # Limpiar llaves para que coincidan con las claves normalizadas
            d = {limpiar_rut(k): v for k, v in d.items() if k and len(str(k)) >= 6}
            # SII tiene prioridad sobre instituciones
            diccionario_nombres.update(d)
            print(f"   {len(d)} nombres desde SII")
        if not col_nom:
            # fallback: columna fija (según estructura conocida)
            print("   Buscando columna de nombre… primer columna de texto largo")
            for c in sii.columns:
                if sii[c].dropna().astype(str).str.len().mean() > 15:
                    d = _dict_nombres(sii, col_rut, c)
                    diccionario_nombres.update(d)
                    break
    else:
        print("3. SII no encontrado — se usarán los nombres existentes.")

    print(f"   Total nombres en diccionario: {len(diccionario_nombres)}")

    # Aplicar enriquecimiento: reemplazar nombres que parecen RUTs
    def parece_rut(s):
        return bool(re.match(r"^[\d.]+-[0-9K]$", str(s).strip()))

    print("4. Reemplazando RUTs por nombres legales…", flush=True)

    for col, clean_col in [("dtr_nombre", "rut_dtr_clean"), ("dnt_nombre", "rut_dnt_clean")]:
        antes = df[col].notna().sum()
        mask_rut = df[col].apply(parece_rut)
        n_reemplazo = 0
        if mask_rut.any():
            reemplazo = df.loc[mask_rut, clean_col].map(diccionario_nombres)
            n_reemplazo = int(reemplazo.notna().sum())
            mask = mask_rut & reemplazo.notna()
            df.loc[mask, col] = reemplazo[mask]
        despues = df[col].notna().sum()
        print(f"   {col}: {antes:,} → {despues:,} con nombre "
              f"({int(mask_rut.sum()):,} RUTs, {n_reemplazo:,} reemplazados)".replace(",", "."))

    # Guardar (sin columnas auxiliares)
    df = df.drop(columns=["rut_dtr_clean", "rut_dnt_clean"])
    print("5. Guardando donaciones.arrowz…", flush=True)
    feather.write_feather(df, ARCHIVO_DONACIONES)
    print("¡Listo! Ahora ejecutá python actualizar.py para regenerar index.html")


if __name__ == "__main__":
    main()