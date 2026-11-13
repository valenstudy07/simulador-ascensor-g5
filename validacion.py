"""Validación numérica: solución analítica, errores de Euler y RK4, influencia del paso,
convergencia y (opcional) contraste con un integrador independiente de SciPy.

Caso con solución analítica: misma ecuación (**) del modelo con v_ref constante = v0
(escalón de velocidad), partiendo del reposo en y = 0:
    m_ef dv/dt = (Kp + b)(v0 - v)
    v(t) = v0 (1 - e^{-t/τ}),     τ = m_ef / (Kp + b)
    y(t) = v0 [ t - τ (1 - e^{-t/τ}) ]

Estabilidad de Euler en esta ecuación: |1 - dt/τ| < 1  ->  dt < 2τ.
"""
import numpy as np
from modelo import Params, derivadas
from metodos import euler, rk4

DTS = (0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.001)


def f_escalon(t, s, p, v0):
    return derivadas(t, s, p, lambda _t: v0)


def analitica(t, p, v0):
    tau = p.tau
    v = v0 * (1 - np.exp(-t / tau))
    y = v0 * (t - tau * (1 - np.exp(-t / tau)))
    return y, v


def errores(p: Params, v0=None, t_f=3.0, dts=DTS):
    """Error absoluto máximo y relativo máximo en v(t) para cada dt y método."""
    v0 = p.v_max if v0 is None else v0
    filas = []
    for dt in dts:
        fila = {"dt": dt, "dt/tau": dt / p.tau}
        for nombre, met in (("Euler", euler), ("RK4", rk4)):
            t, Y = met(f_escalon, 0.0, np.array([0.0, 0.0]), t_f, dt, p, v0)
            _, v_a = analitica(t, p, v0)
            fila[f"{nombre}_abs"] = np.max(np.abs(Y[:, 1] - v_a))
            fila[f"{nombre}_rel"] = np.max(np.abs(Y[1:, 1] - v_a[1:]) / np.abs(v_a[1:]))
        filas.append(fila)
    return filas


def orden_convergencia(filas, clave, solo_estables_tau=None, piso=1e-10):
    """Pendiente log-log error vs dt. Excluye errores en el nivel de redondeo y,
    si se da tau, los pasos fuera de la región asintótica (dt > tau/2)."""
    sel = [f for f in filas if f[clave] > piso and (solo_estables_tau is None or f["dt"] <= solo_estables_tau / 2)]
    dts = np.array([f["dt"] for f in sel])
    errs = np.array([f[clave] for f in sel])
    return np.polyfit(np.log(dts), np.log(errs), 1)[0]


def contraste_scipy(p: Params, v0=None, t_f=3.0):
    """Solo para validar: error de solve_ivp (RK45, tolerancias estrictas) frente a la analítica."""
    try:
        from scipy.integrate import solve_ivp
    except ImportError:
        return None
    v0 = p.v_max if v0 is None else v0
    sol = solve_ivp(lambda t, s: f_escalon(t, s, p, v0), (0, t_f), [0.0, 0.0],
                    rtol=1e-10, atol=1e-12, dense_output=True)
    t = np.linspace(0, t_f, 301)
    _, v_a = analitica(t, p, v0)
    return float(np.max(np.abs(sol.sol(t)[1] - v_a)))


if __name__ == "__main__":
    p = Params()
    filas = errores(p)
    print(f"Caso 1 · cabina vacía · m_ef = {p.m_ef:.0f} kg · tau = {p.tau:.4f} s · Euler estable si dt < {2*p.tau:.3f} s")
    print(f"{'dt':>7} {'dt/tau':>7} {'Euler abs':>11} {'RK4 abs':>11} {'Euler rel':>11} {'RK4 rel':>11}")
    for f in filas:
        print(f"{f['dt']:7.3f} {f['dt/tau']:7.2f} {f['Euler_abs']:11.3e} {f['RK4_abs']:11.3e} "
              f"{f['Euler_rel']:11.3e} {f['RK4_rel']:11.3e}")
    print("orden observado Euler ≈", round(orden_convergencia(filas, "Euler_abs", p.tau), 2))
    print("orden observado RK4   ≈", round(orden_convergencia(filas, "RK4_abs", p.tau), 2))
    e = contraste_scipy(p)
    if e is not None:
        print(f"Contraste solve_ivp (solo validación): error abs. máx = {e:.2e} m/s")
