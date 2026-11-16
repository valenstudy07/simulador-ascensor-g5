"""Consumo de un día típico (kWh/día) con contrapeso al 50 % y al 30 %.

Método (perfil de uso de la ISO 25745-2, energía de los viajes con el modelo físico del grupo):
  1. Viaje medio: recorre %S del recorrido total (s_av = %S · 75 m) con la carga media %Q · Q.
  2. La mitad de los n_d viajes sube y la otra mitad baja. Cada sentido se simula con RK4 (dt = 0,01 s)
     y se obtiene su energía neta de la red (consumida/η − recuperada·η).
  3. Energía en marcha:   E_marcha = (n_d / 2) · (E_sube + E_baja)
  4. Energía sin marcha:  E_reposo = (24 h − t_marcha) · (R_id · P_id + R_st · P_st)
  5. E_dia = E_marcha + E_reposo

Diferencia con la norma: la ISO 25745-2 parte de un ciclo de referencia medido y lo corrige con el
factor de carga k_L (definido para contrapeso al 50 %). Aquí la energía de cada viaje sale de la
ecuación de movimiento, lo que permite evaluar también el contrapeso al 30 %.
Ejecutar:  python dia_tipico.py
"""
from dataclasses import replace
import numpy as np
from parametros import CASO, ISO
from modelo import Params
from simulacion import simular
from energia import J_POR_WH

DT = 0.01


def viaje_medio(frac_cw, categoria=None, regenerativo=True, eta=None):
    """Energía neta (Wh) de un viaje medio subiendo y bajando, y su duración (s)."""
    cat = ISO["categoria"] if categoria is None else categoria
    s_av = ISO["pct_S"] / 100 * CASO["recorrido"]
    carga = ISO["pct_Q"][cat] / 100 * CASO["carga_nominal"]
    base = Params(m_contrapeso=CASO["m_cabina"] + frac_cw * CASO["carga_nominal"],
                  m_pasajeros=carga, h_piso=s_av, n_pisos=2, regenerativo=regenerativo)
    if eta is not None:
        base = replace(base, eta_motor=eta, eta_regen=eta)
    sube = simular(replace(base, piso_ini=0, piso_fin=1), "RK4", DT)
    baja = simular(replace(base, piso_ini=1, piso_fin=0), "RK4", DT)
    from modelo import perfil_velocidad
    _, T, _ = perfil_velocidad(replace(base, piso_ini=0, piso_fin=1))
    return dict(s_av=s_av, carga=carga, T=T,
                E_sube=sube["E_red_neta"][-1] / J_POR_WH, E_baja=baja["E_red_neta"][-1] / J_POR_WH)


def dia(frac_cw, categoria=None, regenerativo=True, eta=None):
    cat = ISO["categoria"] if categoria is None else categoria
    n_d = ISO["viajes_dia"][cat]
    v = viaje_medio(frac_cw, cat, regenerativo, eta)
    E_marcha = n_d / 2 * (v["E_sube"] + v["E_baja"]) / 1000            # kWh
    t_marcha_h = n_d * v["T"] / 3600
    P_reposo = ISO["R_id"] * ISO["P_id"] + ISO["R_st"] * ISO["P_st"]   # W
    E_reposo = (24 - t_marcha_h) * P_reposo / 1000                      # kWh
    return dict(categoria=cat, n_d=n_d, **v, E_marcha=E_marcha, t_marcha_h=t_marcha_h,
                P_reposo=P_reposo, E_reposo=E_reposo, E_dia=E_marcha + E_reposo)


def tabla_resumen():
    filas = []
    for frac in (0.5, 0.3):
        d = dia(frac)
        filas.append({"Contrapeso": f"{int(frac*100)} %", **d})
    return filas


if __name__ == "__main__":
    f50, f30 = dia(0.5), dia(0.3)
    print(f"Categoría {f50['categoria']}: {f50['n_d']} viajes/día · viaje medio {f50['s_av']:.1f} m · "
          f"carga media {f50['carga']:.0f} kg · duración {f50['T']:.1f} s")
    print(f"Reposo: {f50['P_reposo']:.0f} W medios durante {24-f50['t_marcha_h']:.2f} h")
    for nom, d in (("50 %", f50), ("30 %", f30)):
        print(f"CW {nom}: sube {d['E_sube']:+.2f} Wh, baja {d['E_baja']:+.2f} Wh | "
              f"marcha {d['E_marcha']:.2f} kWh + reposo {d['E_reposo']:.2f} kWh = {d['E_dia']:.2f} kWh/día")
    ah = f50["E_dia"] - f30["E_dia"]
    print(f"Ahorro: {ah:.2f} kWh/día = {ah*365:.0f} kWh/año ({ah/f50['E_dia']*100:.1f} %)")
    print(f"Fuente: 26,074 -> 18,352 kWh/día, ahorro 7,722 kWh/día = 2819 kWh/año (29,6 %)")

    print("\nSensibilidad")
    for etiqueta, kw in (("Cat. 3", dict(categoria=3)), ("Cat. 5", dict(categoria=5)),
                         ("η = 0,70", dict(eta=0.70)), ("Sin regeneración", dict(regenerativo=False))):
        a, b = dia(0.5, **kw), dia(0.3, **kw)
        print(f"{etiqueta:17s} 50 %: {a['E_dia']:6.2f}  30 %: {b['E_dia']:6.2f} kWh/día  "
              f"ahorro {(a['E_dia']-b['E_dia']):5.2f} kWh/día ({(a['E_dia']-b['E_dia'])/a['E_dia']*100:5.1f} %)  "
              f"marcha 50/30: {a['E_marcha']:.2f}/{b['E_marcha']:.2f}")
