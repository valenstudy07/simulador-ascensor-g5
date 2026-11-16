"""Figuras estáticas (Matplotlib) y tablas CSV para el artículo, con los parámetros del Caso 1.
Ejecutar:  python figuras.py   -> crea la carpeta figuras/
"""
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from parametros import CASO
from modelo import Params
from simulacion import simular
from energia import barrido_masa, J_POR_WH as WH
import validacion as val

OUT = Path(__file__).parent / "figuras"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})
Q = CASO["carga_nominal"]
SUBE = dict(piso_ini=0, piso_fin=CASO["n_paradas"] - 1)
BAJA = dict(piso_ini=CASO["n_paradas"] - 1, piso_fin=0)


def caso(frac, **kw):
    return replace(Params(m_contrapeso=CASO["m_cabina"] + frac * Q), **kw)


# 1. Convergencia Euler vs RK4 (solución analítica)
p = caso(0.5)
filas = val.errores(p)
df = pd.DataFrame(filas)
df.to_csv(OUT / "tabla_errores.csv", index=False)
fig, ax = plt.subplots(figsize=(4.5, 3.3))
ax.loglog(df["dt"], df["Euler_abs"], "o-", label="Euler")
ax.loglog(df["dt"], df["RK4_abs"], "s-", label="RK4")
ax.axvline(2 * p.tau, ls=":", c="gray")
ax.text(2 * p.tau, ax.get_ylim()[0] * 10, " 2τ", color="gray")
ax.set_xlabel("Paso dt (s)"); ax.set_ylabel("Error absoluto máx. en v (m/s)")
ax.set_title("Convergencia frente a la solución analítica"); ax.legend()
fig.tight_layout(); fig.savefig(OUT / "fig_convergencia.png"); plt.close(fig)

# 2. Euler vs RK4 en el viaje real (cabina vacía, sube, CW 50 %) con dt grande
q = caso(0.5, m_pasajeros=0.0, **SUBE)
ref = simular(q, "RK4", 0.001)
fig, ax = plt.subplots(figsize=(5, 3.3))
ax.plot(ref["t"], ref["v"], "k:", label="Referencia RK4 (dt = 0.001 s)")
for met, dt in (("Euler", 0.2), ("RK4", 0.2)):
    B = simular(q, met, dt)
    ax.plot(B["t"], B["v"], label=f"{met} (dt = {dt} s)")
ax.set_xlabel("t (s)"); ax.set_ylabel("v (m/s)"); ax.set_title("Velocidad de la cabina: Euler vs RK4")
ax.legend(); fig.tight_layout(); fig.savefig(OUT / "fig_euler_vs_rk4.png"); plt.close(fig)

# 3. Balance de energía en el tiempo (cabina vacía sube, CW 50 %)
B = ref
fig, ax = plt.subplots(figsize=(5, 3.3))
for clave, nombre in [("Ep", "ΔEp neta"), ("E_cons", "Consumida"), ("E_rec", "Recuperada"),
                      ("E_fric", "Fricción"), ("E_resistencia", "Pérdidas de regeneración")]:
    ax.plot(B["t"], B[clave] / WH, label=nombre)
ax.set_xlabel("t (s)"); ax.set_ylabel("Energía (Wh)")
ax.set_title("Cabina vacía subiendo, contrapeso 50 %"); ax.legend(fontsize=7)
fig.tight_layout(); fig.savefig(OUT / "fig_energia_tiempo.png"); plt.close(fig)

# 4. Tabla y barras 30 % vs 50 %
filas = []
for frac in (0.5, 0.3):
    for m in (0, 250, 500, 750, 1000):
        s = simular(caso(frac, m_pasajeros=m, **SUBE), "RK4", 0.01)["E_red_neta"][-1] / WH
        b = simular(caso(frac, m_pasajeros=m, **BAJA), "RK4", 0.01)["E_red_neta"][-1] / WH
        filas.append({"contrapeso_%": int(frac * 100), "carga_kg": m, "sube_Wh": s, "baja_Wh": b, "ida_vuelta_Wh": s + b})
t = pd.DataFrame(filas).round(2)
t.to_csv(OUT / "tabla_30_vs_50.csv", index=False)
fig, ax = plt.subplots(figsize=(5, 3.3))
x = np.arange(5)
for i, frac in enumerate((50, 30)):
    g = t[t["contrapeso_%"] == frac]
    ax.bar(x + (i - 0.5) * 0.38, g["ida_vuelta_Wh"], 0.38, label=f"Contrapeso {frac} %")
ax.set_xticks(x, [f"{m} kg" for m in (0, 250, 500, 750, 1000)])
ax.axhline(0, c="k", lw=0.8)
ax.set_xlabel("Carga en cabina"); ax.set_ylabel("Energía neta ida y vuelta (Wh)")
ax.set_title("Viaje completo de 75 m: 30 % vs 50 %"); ax.legend()
fig.tight_layout(); fig.savefig(OUT / "fig_30_vs_50.png"); plt.close(fig)

# 5. Barrido de masa: condición de recuperación
masas = np.linspace(0, 1.2 * Q, 25)
fig, ax = plt.subplots(figsize=(5, 3.3))
for frac, ls in ((0.5, "-"), (0.3, "--")):
    for nombre, sent in (("sube", SUBE), ("baja", BAJA)):
        S = barrido_masa(caso(frac, **sent), masas, lambda pp: simular(pp, "RK4", 0.02))
        ax.plot(S[:, 0], S[:, 3] / WH, ls, marker=".", label=f"CW {int(frac*100)} %, {nombre}")
    ax.axvline(frac * Q, c="gray", ls=":")
ax.axhline(0, c="k", lw=0.8)
ax.set_xlabel("Masa de pasajeros (kg)"); ax.set_ylabel("Energía neta (Wh)   (<0 recupera)")
ax.set_title("Condición de recuperación según carga y sentido"); ax.legend(fontsize=7)
fig.tight_layout(); fig.savefig(OUT / "fig_barrido_masa.png"); plt.close(fig)

# 6. Día típico (ISO 25745-2): marcha + reposo, con y sin regeneración
from dia_tipico import dia
filas = []
for reg in (True, False):
    for frac in (0.5, 0.3):
        d = dia(frac, regenerativo=reg)
        filas.append({"contrapeso_%": int(frac * 100), "regenerativo": reg, "viajes_dia": d["n_d"],
                      "viaje_medio_m": round(d["s_av"], 1), "carga_media_kg": round(d["carga"]),
                      "E_marcha_kWh": round(d["E_marcha"], 2), "E_reposo_kWh": round(d["E_reposo"], 2),
                      "E_dia_kWh": round(d["E_dia"], 2)})
td = pd.DataFrame(filas)
td.to_csv(OUT / "tabla_dia_tipico.csv", index=False)
fig, ax = plt.subplots(figsize=(5, 3.3))
etiquetas = [f"{r.contrapeso_}%\n{'con' if r.regenerativo else 'sin'} regen." for r in td.rename(columns={"contrapeso_%": "contrapeso_"}).itertuples()]
ax.bar(etiquetas, td["E_marcha_kWh"], label="En marcha")
ax.bar(etiquetas, td["E_reposo_kWh"], bottom=td["E_marcha_kWh"], label="En reposo")
ax.axhline(CASO["Ed_50_Wh_dia"] / 1000, ls="--", c="k", lw=0.8)
ax.axhline(CASO["Ed_30_Wh_dia"] / 1000, ls=":", c="k", lw=0.8)
ax.text(3.45, CASO["Ed_50_Wh_dia"] / 1000, " fuente 50 %", va="bottom", ha="right", fontsize=7)
ax.text(3.45, CASO["Ed_30_Wh_dia"] / 1000, " fuente 30 %", va="bottom", ha="right", fontsize=7)
ax.set_ylabel("Energía (kWh/día)"); ax.set_title("Día típico, categoría de uso 4 (750 viajes/día)")
ax.legend(fontsize=7, loc="upper left")
fig.tight_layout(); fig.savefig(OUT / "fig_dia_tipico.png"); plt.close(fig)

print("Figuras y tablas guardadas en", OUT)
print(td.to_string(index=False))
print(t.to_string(index=False))
