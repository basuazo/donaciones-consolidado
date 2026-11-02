#!/usr/bin/env python3
"""Regenera el bloque <script id="DATA"> de index.html a partir de donaciones.arrowz.

Recalcula KPIs, comparativa por ley/año, serie mensual, rankings de donatarias
y donantes (top 300) y principales proyectos, y reescribe index.html en el lugar.
"""

import gzip
import json
import re
from datetime import date

import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather

ARCHIVO_DONACIONES = "donaciones.arrowz"
ARCHIVO_HTML = "index.html"
TOP = 300  # organizaciones por ranking


def cargar_donaciones() -> pd.DataFrame:
    """Lee donaciones.arrowz (Arrow IPC file, o gzip + IPC stream)."""
    try:  # 1) Feather / Arrow IPC file (formato actual)
        return feather.read_feather(ARCHIVO_DONACIONES)
    except Exception:
        pass
    for abrir in (lambda: pa.memory_map(ARCHIVO_DONACIONES, "r"),
                  lambda: gzip.open(ARCHIVO_DONACIONES, "rb")):
        try:  # 2) Arrow IPC stream, con o sin gzip
            with abrir() as fuente:
                return pa.ipc.open_stream(fuente).read_all().to_pandas()
        except Exception:
            pass
    raise RuntimeError("No se pudo cargar donaciones.arrowz.")


def _limpiar(serie: pd.Series) -> pd.Series:
    """Normaliza RUTs: mayúsculas y sólo dígitos + K."""
    return serie.astype(str).str.upper().str.replace(r"[^0-9K]", "", regex=True)


def _ranking(df, key_col, nombre_col, contraparte_col, contraparte_label) -> pd.DataFrame:
    """Agrega por RUT y devuelve el top TOP con los campos que usa la tabla."""
    work = df[df[key_col].notna()].copy()
    work["key"] = _limpiar(work[key_col])

    agg = work.groupby("key", sort=False).agg(
        nombre=(nombre_col, "first"),
        monto=("monto", "sum"),
        n=("monto", "size"),
        n_contra=(contraparte_col, "nunique"),
        leyes=("ley", lambda s: "+".join(sorted({str(v) for v in s.dropna().unique()}))),
    ).reset_index()

    agg["rut"] = agg["key"]
    agg = agg.rename(columns={"n_contra": contraparte_label})
    agg["nombre"] = agg["nombre"].fillna("")
    agg["monto"] = agg["monto"].astype("int64")
    agg = agg.sort_values("monto", ascending=False)
    return agg.head(TOP).reset_index(drop=True)


def _serie_mensual(df: pd.DataFrame) -> pd.DataFrame:
    """Suma mensual (aaaa-mm) por ley, ignorando filas sin fecha."""
    work = df[df["fecha"].notna()].copy()
    work["ym"] = work["fecha"].astype(str).str.slice(0, 7)
    work = work[work["ym"].str.match(r"^\d{4}-\d{2}$")]
    g = (work.groupby(["ley", "ym"], sort=False)
             .agg(monto=("monto", "sum"), n=("monto", "size"))
             .reset_index()
             .sort_values(["ley", "ym"]))
    g["monto"] = g["monto"].astype("int64")
    return g


def _proyectos(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa por proyecto + donataria (sin filas sin proyecto)."""
    work = df[df["proyecto"].notna() & (df["proyecto"].astype(str).str.strip() != "")].copy()
    g = (work.groupby(["proyecto", "dtr_nombre"], sort=False)
             .agg(monto=("monto", "sum"),
                  n=("monto", "size"),
                  n_donantes=("dnt_key", "nunique"))
             .reset_index()
             .rename(columns={"dtr_nombre": "donataria"})
             .sort_values("monto", ascending=False))
    g["monto"] = g["monto"].astype("int64")
    return g


def _conc(df: pd.DataFrame, total_monto: int) -> dict:
    """Concentración top 10/20 (donantes excluye el grupo no identificado)."""
    dtr = df.groupby("dtr_key", sort=False)["monto"].sum().sort_values(ascending=False).to_numpy()
    dnt_all = df.groupby("dnt_key", sort=False)["monto"].sum().sort_values(ascending=False)
    dnt = dnt_all[dnt_all.index.astype(str) != ""].to_numpy()

    def pct(valores, k):
        return round(float(valores[:k].sum()) / total_monto * 100, 1) if total_monto else 0.0

    return {
        "donatarias_top10": pct(dtr, 10),
        "donatarias_top20": pct(dtr, 20),
        "donantes_top10": pct(dnt, 10),
        "donantes_top20": pct(dnt, 20),
    }


def main():
    print("1. Cargando donaciones.arrowz…", flush=True)
    df = cargar_donaciones()

    df["dtr_key"] = df["dtr_key"].astype(str)
    df["dnt_key"] = df["dnt_key"].astype(str)
    df["monto"] = df["monto"].astype("int64")
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce")

    total_monto = int(df["monto"].sum())
    n_total = int(len(df))
    sin_dnt = df["dnt_key"] == ""
    print(f"   {n_total:,} registros cargados.".replace(",", "."))

    # ── meta (KPIs) ──
    meta = {
        "generado": date.today().isoformat(),
        "total_monto": total_monto,
        "total_donaciones": n_total,
        "n_donatarias": int(df["dtr_key"].nunique()),
        "n_donantes_ident": int(df.loc[~sin_dnt, "dnt_key"].nunique()),
        "monto_sin_donante": int(df.loc[sin_dnt, "monto"].sum()),
        "n_sin_donante": int(sin_dnt.sum()),
        "fondo_mixto_total": 0,
    }

    # ── comparativa por ley ──
    por_ley = {}
    for ley, grp in df.groupby("ley"):
        por_ley[str(ley)] = {
            "monto": int(grp["monto"].sum()),
            "n": int(len(grp)),
            "n_donatarias": int(grp["dtr_key"].nunique()),
            "n_donantes": int(grp.loc[grp["dnt_key"] != "", "dnt_key"].nunique()),
            "monto_sin_donante": int(grp.loc[grp["dnt_key"] == "", "monto"].sum()),
        }

    # ── comparativa por ley y año ──
    pla = (df.groupby(["ley", "anio"], sort=False)
             .agg(monto=("monto", "sum"), n=("monto", "size"))
             .reset_index()
             .sort_values(["ley", "anio"]))
    pla["monto"] = pla["monto"].astype("int64")
    pla["anio"] = pla["anio"].astype(int)

    # ── serie mensual y proyectos ──
    serie = _serie_mensual(df)
    proyectos = _proyectos(df)

    # ── rankings de la tabla ──
    print("2. Calculando donatarias…", flush=True)
    donatarias = _ranking(df, "dtr_key", "dtr_nombre", "dnt_key", "n_donantes")
    print("3. Calculando donantes…", flush=True)
    donantes = _ranking(df, "dnt_key", "dnt_nombre", "dtr_key", "n_donatarias")

    data = {
        "meta": meta,
        "por_ley": por_ley,
        "por_ley_anio": pla.to_dict(orient="records"),
        "donatarias": donatarias.to_dict(orient="records"),
        "n_donantes_total": meta["n_donantes_ident"],
        "monto_donantes_ident": int(df.loc[~sin_dnt, "monto"].sum()),
        "donantes_top": donantes.to_dict(orient="records"),
        "n_proyectos": int(len(proyectos)),
        "proyectos_top": proyectos.to_dict(orient="records"),
        "serie_mensual": serie.to_dict(orient="records"),
        "conc": _conc(df, total_monto),
    }

    print("4. Escribiendo index.html…", flush=True)
    with open(ARCHIVO_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    nuevo_json = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))

    html, n = re.subn(
        r'(<script id="DATA" type="application/json">)(.*?)(</script>)',
        lambda m: m.group(1) + nuevo_json + m.group(3),
        html, count=1, flags=re.S,
    )
    if not n:
        raise RuntimeError('No se encontró el bloque <script id="DATA"> en index.html.')

    with open(ARCHIVO_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✓ index.html actualizado con datos al {meta['generado']}.")
    print(f"  Donatarias: {len(donatarias)} · Donantes: {len(donantes)} · "
          f"Proyectos: {len(proyectos)}")
    print(f"  Total: ${total_monto // 1_000_000:,} MM · {n_total:,} donaciones".replace(",", "."))


if __name__ == "__main__":
    main()

