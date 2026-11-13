"""Balance de energía del recorrido (internamente en J; la interfaz muestra Wh).

Trabajo del motor (mecánico):  W = ∫ F_m v dt     (P = F_m v; P>0 consume, P<0 regenera)
Conservación (verificación):   W = ΔEc + ΔEp_neta + E_fricción
    Ec = ½ m_ef v²,  Ep_neta = (M - m_cw) g y,  E_fricción = ∫ b v² dt
Eléctrica:  E_consumida = ∫ max(P,0) dt / η_motor ;  E_recuperada = η_regen ∫ max(-P,0) dt
"""
from dataclasses import replace
import numpy as np
from modelo import Params, fuerza_motor
from parametros import G

J_POR_WH = 3600.0


def _cumtrapz(y, t):
    out = np.zeros_like(y)
    out[1:] = np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))
    return out


def balance(t, Y, p: Params, v_ref):
    y, v = Y[:, 0], Y[:, 1]
    F = np.array([fuerza_motor(tk, Y[k], p, v_ref) for k, tk in enumerate(t)])
    P = F * v                                   # potencia mecánica del motor (W)
    P_cons = np.maximum(P, 0.0)
    P_rec = np.maximum(-P, 0.0)

    E_mot = _cumtrapz(P, t)                     # trabajo neto del motor
    E_fric = _cumtrapz(p.b * v**2, t)           # disipada por fricción
    Ec = 0.5 * p.m_ef * v**2
    Ep = p.desbalance * G * y                   # Ep neta del sistema cabina + contrapeso

    E_el_cons = _cumtrapz(P_cons, t) / p.eta_motor
    E_rec_bruta = _cumtrapz(P_rec, t)           # mecánica disponible al frenar/bajar
    if p.regenerativo:
        E_rec = E_rec_bruta * p.eta_regen
        E_resistencia = E_rec_bruta * (1 - p.eta_regen)
    else:
        E_rec = np.zeros_like(t)
        E_resistencia = E_rec_bruta
    E_red_neta = E_el_cons - E_rec

    # Error de conservación: W - (ΔEc + ΔEp + E_fric)  (debe ser ≈ 0)
    err_cons = E_mot - (Ec - Ec[0] + Ep - Ep[0] + E_fric)

    return dict(t=t, y=y, v=v, F=F, P=P, Ec=Ec, Ep=Ep,
                E_mot=E_mot, E_fric=E_fric, E_cons=E_el_cons, E_rec=E_rec,
                E_resistencia=E_resistencia, E_red_neta=E_red_neta, err_cons=err_cons)


def barrido_masa(p: Params, masas, simular):
    """Energía (J) consumida, recuperada y neta para distintas masas de pasajeros.
    El cambio consumo/recuperación ocurre cerca de m_p* = m_cw - m_cabina."""
    res = []
    for m in masas:
        B = simular(replace(p, m_pasajeros=float(m)))
        res.append((m, B["E_cons"][-1], B["E_rec"][-1], B["E_red_neta"][-1]))
    return np.array(res)


def interpretar(B, p: Params):
    """Texto de interpretación física del resultado de un escenario."""
    sube = p.distancia > 0
    sentido = "sube" if sube else ("baja" if p.distancia < 0 else "no se mueve")
    d = p.desbalance
    if abs(d) < 1e-9:
        lado = "la cabina y el contrapeso pesan lo mismo"
    elif d > 0:
        lado = f"la cabina cargada pesa {d:.0f} kg más que el contrapeso"
    else:
        lado = f"el contrapeso pesa {-d:.0f} kg más que la cabina cargada"
    neta = B["E_red_neta"][-1] / J_POR_WH
    dEp = (B["Ep"][-1] - B["Ep"][0]) / J_POR_WH
    if neta < 0:
        estado = (f"**recupera {-neta:.1f} Wh** netos: el sistema pierde {-dEp:.1f} Wh de energía potencial "
                  f"y el motor trabaja como generador")
    elif dEp > 0:
        estado = (f"**consume {neta:.1f} Wh** netos: el motor debe aportar {dEp:.1f} Wh de energía potencial "
                  f"más las pérdidas")
    else:
        estado = (f"**consume {neta:.1f} Wh** netos: la energía potencial liberada ({-dEp:.1f} Wh) no alcanza "
                  f"a cubrir las pérdidas por fricción, aceleración y eficiencia")
    if not p.regenerativo and neta >= 0 and B["E_resistencia"][-1] > 0:
        estado += f" (sin variador regenerativo se disipan {B['E_resistencia'][-1]/J_POR_WH:.1f} Wh en la resistencia)"
    return f"La cabina {sentido} y {lado}; en este viaje el ascensor {estado}."
