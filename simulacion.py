"""Une modelo + método numérico + balance."""
from modelo import Params, derivadas, perfil_velocidad
from metodos import euler, rk4
from energia import balance
import numpy as np

METODOS = {"Euler": euler, "RK4": rk4}


def simular(p: Params, metodo="RK4", dt=0.01, cola=2.0):
    v_ref, T, _ = perfil_velocidad(p)
    t_f = T + cola                      # cola: deja que el control asiente la cabina
    n = max(1, int(round(t_f / dt)))
    dt_ef = t_f / n                     # ajusta dt para que quepa exacto
    t, Y = METODOS[metodo](derivadas, 0.0, np.array([0.0, 0.0]), t_f, dt_ef, p, v_ref)
    return balance(t, Y, p, v_ref)
