"""Métodos numéricos implementados A MANO (sin solve_ivp): Euler y Runge-Kutta 4."""
import numpy as np


def euler(f, t0, y0, t_f, dt, *args):
    n = int(round((t_f - t0) / dt))
    t = t0 + dt * np.arange(n + 1)
    Y = np.zeros((n + 1, len(y0)))
    Y[0] = y0
    for k in range(n):
        Y[k + 1] = Y[k] + dt * f(t[k], Y[k], *args)
    return t, Y


def rk4(f, t0, y0, t_f, dt, *args):
    n = int(round((t_f - t0) / dt))
    t = t0 + dt * np.arange(n + 1)
    Y = np.zeros((n + 1, len(y0)))
    Y[0] = y0
    for k in range(n):
        tk, yk = t[k], Y[k]
        k1 = f(tk, yk, *args)
        k2 = f(tk + dt / 2, yk + dt / 2 * k1, *args)
        k3 = f(tk + dt / 2, yk + dt / 2 * k2, *args)
        k4 = f(tk + dt, yk + dt * k3, *args)
        Y[k + 1] = yk + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    return t, Y
