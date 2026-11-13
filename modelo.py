"""Modelo físico del ascensor con contrapeso (Proyecto 10, G5) aplicado al Caso 1.

Sistema: cabina (m_c + pasajeros m_p) unida por un cable inextensible y sin deslizamiento,
sobre una polea de radio R e inercia I, a un contrapeso m_cw.
Eje y positivo hacia ARRIBA (y = desplazamiento de la cabina desde su piso de partida).

Leyes de Newton:
    cabina:      T1 - M g       = M a            (M = m_c + m_p)
    contrapeso:  m_cw g - T2    = m_cw a
    polea:       F_m R + (T2 - T1) R = I a / R   (F_m = fuerza equivalente del motor en el cable)
Combinando (eliminando T1 y T2) y con fricción viscosa b v:

    m_ef a = F_m - (M - m_cw) g - b v ,    m_ef = M + m_cw + I/R^2          (*)

Control de velocidad del variador (proporcional + compensación del desbalance y de la fricción):
    F_m = Kp (v_ref - v) + (M - m_cw) g + b v_ref
Sustituyendo en (*):
    m_ef dv/dt = (Kp + b) (v_ref(t) - v) ,     dy/dt = v                    (**)

(**) es lineal: con v_ref constante tiene solución analítica (ver validacion.py).
La compensación b v_ref elimina el error en régimen permanente, así la cabina se detiene en el piso.
"""
from dataclasses import dataclass
import numpy as np
from parametros import CASO, G


@dataclass
class Params:
    m_cabina: float = CASO["m_cabina"]
    m_pasajeros: float = 0.0
    capacidad: float = CASO["carga_nominal"]
    m_contrapeso: float | None = None   # kg; por defecto m_cabina + 0.5*capacidad
    I_polea_eq: float = CASO["I_polea_eq"]
    b: float = CASO["b"]
    Kp: float = CASO["Kp"]
    n_pisos: int = CASO["n_paradas"]
    h_piso: float = CASO["h_piso"]
    piso_ini: int = 0
    piso_fin: int = CASO["n_paradas"] - 1
    v_max: float = CASO["v_nominal"]
    a_ref: float = CASO["a_nominal"]
    eta_motor: float = CASO["eta_motor"]
    eta_regen: float = CASO["eta_regen"]
    regenerativo: bool = True     # False: la energía de frenado se disipa en una resistencia

    def __post_init__(self):
        if self.m_contrapeso is None:
            self.m_contrapeso = self.m_cabina + 0.5 * self.capacidad

    @property
    def M(self):
        return self.m_cabina + self.m_pasajeros

    @property
    def m_ef(self):
        return self.M + self.m_contrapeso + self.I_polea_eq

    @property
    def desbalance(self):
        """(M - m_cw): >0 la cabina pesa más que el contrapeso."""
        return self.M - self.m_contrapeso

    @property
    def tau(self):
        """Constante de tiempo del lazo de velocidad (s)."""
        return self.m_ef / (self.Kp + self.b)

    @property
    def distancia(self):
        return (self.piso_fin - self.piso_ini) * self.h_piso


def perfil_velocidad(p: Params):
    """Perfil trapezoidal (o triangular si el recorrido es corto) de v_ref(t).
    Devuelve (v_ref(t), duración T, signo s). No incluye el jerk (limitación)."""
    D = abs(p.distancia)
    s = 1.0 if p.distancia >= 0 else -1.0
    if D == 0:
        return (lambda t: 0.0), 0.0, s
    v_pico = min(p.v_max, np.sqrt(p.a_ref * D))   # triangular si no alcanza v_max
    t_a = v_pico / p.a_ref
    t_c = (D - v_pico * t_a) / v_pico             # tiempo a velocidad constante
    T = 2 * t_a + t_c

    def v_ref(t):
        if t < 0 or t > T:
            return 0.0
        if t < t_a:
            return s * p.a_ref * t
        if t < t_a + t_c:
            return s * v_pico
        return s * p.a_ref * (T - t)

    return v_ref, T, s


def fuerza_motor(t, estado, p: Params, v_ref):
    y, v = estado
    vr = v_ref(t)
    return p.Kp * (vr - v) + p.desbalance * G + p.b * vr


def derivadas(t, estado, p: Params, v_ref):
    """f(t, [y, v]) -> [dy/dt, dv/dt]  (ecuación (*) con el control)."""
    y, v = estado
    F = fuerza_motor(t, estado, p, v_ref)
    a = (F - p.desbalance * G - p.b * v) / p.m_ef
    return np.array([v, a])
