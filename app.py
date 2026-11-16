"""Simulador de ascensor regenerativo — Caso 1 (contrapeso 50 % vs 30 %, ISO 25745).
Streamlit + Plotly. Ejecutar:  streamlit run app.py
"""
from dataclasses import replace
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from parametros import CASO
from modelo import Params
from simulacion import simular
from energia import barrido_masa, interpretar, J_POR_WH
import validacion as val
from dia_tipico import dia
from parametros import ISO

WH = J_POR_WH
st.set_page_config(page_title="Ascensor regenerativo · Caso 1", layout="wide")
st.title("Simulador de ascensor regenerativo")
st.caption(f"Caso de estudio: edificio de {CASO['n_paradas']} paradas, {CASO['recorrido']:.0f} m de recorrido, "
           f"{CASO['v_nominal']} m/s, cabina de {CASO['m_cabina']:.0f} kg y carga nominal de {CASO['carga_nominal']:.0f} kg. "
           "Los valores por defecto son los del caso; puedes modificarlos para explorar.")

# ---------------- Entradas ----------------
sb = st.sidebar
if sb.button("↺ Restablecer valores del caso"):
    st.session_state.clear()
    st.rerun()

sb.header("Edificio y recorrido")
n_pisos = sb.slider("Número de paradas", 2, 40, CASO["n_paradas"])
h_piso = sb.number_input("Altura entre paradas (m)", 2.0, 6.0, CASO["h_piso"], 0.05, format="%.3f")
sb.markdown("**Condiciones iniciales:** la cabina parte del reposo en el piso inicial.")
piso_ini = sb.slider("Piso inicial", 0, n_pisos - 1, 0)
piso_fin = sb.slider("Piso final", 0, n_pisos - 1, n_pisos - 1)
v_max = sb.slider("Velocidad de desplazamiento (m/s)", 0.5, 6.0, CASO["v_nominal"], 0.1)
a_ref = sb.slider("Aceleración del perfil (m/s²)", 0.3, 2.0, CASO["a_nominal"], 0.1)

sb.header("Ascensor")
m_cab = sb.number_input("Masa de cabina (kg)", 300.0, 3000.0, CASO["m_cabina"], 10.0)
capacidad = sb.number_input("Carga nominal (kg)", 200.0, 3000.0, CASO["carga_nominal"], 10.0)
opcion_cw = sb.radio("Equilibrado del contrapeso",
                     ["50 % (tradicional)", "30 % (ISO 25745)", "Personalizado"])
if opcion_cw.startswith("50"):
    factor_cw = 0.5
elif opcion_cw.startswith("30"):
    factor_cw = 0.3
else:
    factor_cw = sb.slider("Fracción de la carga nominal que equilibra", 0.0, 1.0, 0.4, 0.05)
m_cw = m_cab + factor_cw * capacidad
sb.write(f"Contrapeso = {m_cab:.0f} + {factor_cw:.2f}·{capacidad:.0f} = **{m_cw:.0f} kg**")

sb.header("Pérdidas y variador")
b = sb.number_input("Fricción viscosa b (N·s/m) — supuesto", 0.0, 500.0, CASO["b"], 5.0)
eta = sb.slider("Eficiencia motor/variador", 0.5, 1.0, CASO["eta_motor"], 0.01)
eta_reg = sb.slider("Eficiencia de regeneración", 0.0, 1.0, CASO["eta_regen"], 0.01)
regen = sb.checkbox("Variador regenerativo (devuelve energía a la red)", True)

sb.header("Método numérico")
metodo = sb.radio("Método", ["RK4", "Euler"])
dt = sb.select_slider("Paso dt (s)", [0.2, 0.1, 0.05, 0.02, 0.01, 0.005], 0.01)

st.subheader("Escenarios a comparar (masa de pasajeros)")
mp = CASO["m_pasajero"]
c1, c2, c3 = st.columns(3)
tope = int(capacidad * 1.2)
mA = c1.slider("Escenario A (kg)", 0, tope, 0, 25)
mB = c2.slider("Escenario B (kg)", 0, tope, int(capacidad * 0.5), 25)
mC = c3.slider("Escenario C (kg)", 0, tope, int(capacidad), 25)
for c, m in zip((c1, c2, c3), (mA, mB, mC)):
    c.caption(f"≈ {m/mp:.1f} pasajeros de {mp:.0f} kg")

base = Params(m_cabina=m_cab, capacidad=capacidad, m_contrapeso=m_cw, b=b, n_pisos=n_pisos,
              h_piso=h_piso, piso_ini=piso_ini, piso_fin=piso_fin, v_max=v_max, a_ref=a_ref,
              eta_motor=eta, eta_regen=eta_reg, regenerativo=regen)
escenarios = {"A": mA, "B": mB, "C": mC}
colores = {"A": "#1f77b4", "B": "#2ca02c", "C": "#d62728"}


@st.cache_data
def correr(p, metodo, dt):
    return simular(p, metodo, dt)


res = {k: correr(replace(base, m_pasajeros=float(m)), metodo, dt) for k, m in escenarios.items()}

tabs = st.tabs(["Animación", "Cinemática y potencia", "Balance de energía", "Caso 1: 30 % vs 50 %",
                "Día típico (ISO 25745-2)", "Barrido de masa", "Euler vs RK4", "Validación"])

# ---------------- Animación ----------------
with tabs[0]:
    k = st.selectbox("Escenario a animar", list(escenarios))
    B = res[k]
    p = replace(base, m_pasajeros=float(escenarios[k]))
    H = (n_pisos - 1) * h_piso
    y0 = piso_ini * h_piso
    paso = max(1, len(B["t"]) // 150)
    idx = list(range(0, len(B["t"]), paso))
    if idx[-1] != len(B["t"]) - 1:
        idx.append(len(B["t"]) - 1)
    E_neta = B["E_red_neta"] / WH

    alto = max(2.5, 0.85 * h_piso)          # alto de las cajas (m)
    XC, XW = (0.0, 0.8), (2.2, 2.8)         # posición horizontal de cabina y contrapeso

    def caja(x, y0_, color, nombre):
        return go.Scatter(x=[x[0], x[0], x[1], x[1], x[0]], y=[y0_, y0_ + alto, y0_ + alto, y0_, y0_],
                          fill="toself", mode="lines", line=dict(color="#333"), fillcolor=color, name=nombre)

    def cuadro(i):
        ycab = y0 + B["y"][i]
        ycw = H - ycab
        estado = "regenera" if B["P"][i] < 0 else "consume"
        cable = go.Scatter(x=[sum(XC) / 2, sum(XC) / 2, sum(XW) / 2, sum(XW) / 2],
                           y=[ycab + alto, H + 4, H + 4, ycw + alto], mode="lines+markers",
                           marker=dict(size=[0, 9, 9, 0], color="#555"),
                           line=dict(color="#888", width=1.5), name="cable")
        return go.Frame(
            data=[cable, caja(XC, ycab, "#9ecae1", "cabina"), caja(XW, ycw, "#bdbdbd", "contrapeso")],
            name=str(i),
            layout=go.Layout(title=f"t = {B['t'][i]:.1f} s | v = {B['v'][i]:+.2f} m/s | "
                                   f"P = {B['P'][i]/1e3:+.1f} kW ({estado}) | neto acumulado = {E_neta[i]:+.1f} Wh"))

    fig = go.Figure(data=cuadro(0).data, frames=[cuadro(i) for i in idx])
    for j in range(n_pisos):
        fig.add_hline(y=j * h_piso, line=dict(color="#ddd", width=1))
    fig.add_annotation(x=sum(XC) / 2, y=-2.5, text="Cabina", showarrow=False)
    fig.add_annotation(x=sum(XW) / 2, y=-2.5, text="Contrapeso", showarrow=False)
    fig.add_annotation(x=(sum(XC) + sum(XW)) / 4, y=H + 6.5, text="Polea motriz", showarrow=False)
    fig.update_layout(xaxis=dict(range=[-11, 14], visible=False),
                      yaxis=dict(range=[-4, H + 9], title="Altura (m)"),
                      showlegend=False, height=650,
                      updatemenus=[dict(type="buttons", buttons=[
                          dict(label="▶ Play", method="animate",
                               args=[None, dict(frame=dict(duration=40, redraw=True), fromcurrent=True)]),
                          dict(label="⏸ Pausa", method="animate",
                               args=[[None], dict(mode="immediate", frame=dict(duration=0))])])],
                      sliders=[dict(steps=[dict(method="animate", label=f"{B['t'][i]:.0f}",
                                                args=[[str(i)], dict(mode="immediate", frame=dict(duration=0))])
                                           for i in idx], currentvalue=dict(prefix="t (s) = "))])
    st.plotly_chart(fig, width="stretch")
    st.caption("Azul: cabina. Gris: contrapeso (se mueve en sentido contrario).")
    st.info(interpretar(B, p))

# ---------------- Cinemática y potencia ----------------
with tabs[1]:
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        subplot_titles=("Posición y(t) (m)", "Velocidad v(t) (m/s)",
                                        "Potencia mecánica del motor (kW): >0 consume, <0 regenera"))
    for k, B in res.items():
        kw = dict(line=dict(color=colores[k]), legendgroup=k)
        fig.add_scatter(x=B["t"], y=B["y"], row=1, col=1, name=f"{k} ({escenarios[k]} kg)", **kw)
        fig.add_scatter(x=B["t"], y=B["v"], row=2, col=1, showlegend=False, name=k, **kw)
        fig.add_scatter(x=B["t"], y=B["P"] / 1e3, row=3, col=1, showlegend=False, name=k, **kw)
    fig.add_hline(y=0, row=3, col=1, line=dict(color="black", width=1))
    fig.update_xaxes(title_text="t (s)", row=3, col=1)
    fig.update_layout(height=750)
    st.plotly_chart(fig, width="stretch")

# ---------------- Energía ----------------
with tabs[2]:
    k = st.selectbox("Escenario", list(escenarios), key="e")
    B = res[k]
    fig = go.Figure()
    for nombre, clave in [("Energía cinética", "Ec"), ("Energía potencial neta (ΔEp)", "Ep"),
                          ("Disipada por fricción", "E_fric"), ("Consumida de la red", "E_cons"),
                          ("Recuperada a la red", "E_rec"), ("Disipada en resistencia/pérdidas de regeneración", "E_resistencia"),
                          ("Trabajo neto del motor", "E_mot")]:
        fig.add_scatter(x=B["t"], y=B[clave] / WH, name=nombre)
    fig.update_layout(xaxis_title="t (s)", yaxis_title="Energía (Wh)", height=450)
    st.plotly_chart(fig, width="stretch")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Consumida", f"{B['E_cons'][-1]/WH:.1f} Wh")
    m2.metric("Recuperada", f"{B['E_rec'][-1]/WH:.1f} Wh")
    m3.metric("Neta de la red", f"{B['E_red_neta'][-1]/WH:.1f} Wh")
    m4.metric("Error de conservación (máx)", f"{abs(B['err_cons']).max():.2f} J")
    st.info(interpretar(B, replace(base, m_pasajeros=float(escenarios[k]))))
    st.markdown("**Verificación de conservación:** W_motor = ΔEc + ΔEp + E_fricción. "
                "La curva de error debe mantenerse cerca de 0 (con Euler crece; con RK4 es despreciable).")
    st.line_chart(pd.DataFrame({"t (s)": B["t"], "error (J)": B["err_cons"]}).set_index("t (s)"))
    tabla = pd.DataFrame({f"{k2} ({escenarios[k2]} kg)": {
        "Consumida (Wh)": R["E_cons"][-1] / WH, "Recuperada (Wh)": R["E_rec"][-1] / WH,
        "Neta (Wh)": R["E_red_neta"][-1] / WH, "Fricción (Wh)": R["E_fric"][-1] / WH,
        "Situación": "RECUPERA" if R["E_red_neta"][-1] < 0 else "CONSUME"} for k2, R in res.items()}).T
    st.dataframe(tabla)

# ---------------- Caso 1: 30 % vs 50 % ----------------
with tabs[3]:
    st.markdown(f"Viaje completo entre el piso 0 y el piso {n_pisos-1} con los parámetros actuales, "
                "para los dos equilibrados del caso. Negativo = el viaje devuelve energía a la red.")
    cargas = [0.0, 0.25 * capacidad, 0.5 * capacidad, 0.75 * capacidad, capacidad]

    @st.cache_data
    def tabla_caso(base_, cargas_):
        filas = []
        for frac in (0.5, 0.3):
            q0 = replace(base_, m_contrapeso=base_.m_cabina + frac * base_.capacidad)
            for m in cargas_:
                fila = {"Contrapeso": f"{int(frac*100)} % ({q0.m_contrapeso:.0f} kg)", "Carga (kg)": m}
                for nombre, (a, c) in {"Sube (Wh)": (0, base_.n_pisos - 1), "Baja (Wh)": (base_.n_pisos - 1, 0)}.items():
                    R = simular(replace(q0, m_pasajeros=m, piso_ini=a, piso_fin=c), "RK4", 0.02)
                    fila[nombre] = R["E_red_neta"][-1] / WH
                fila["Ida y vuelta (Wh)"] = fila["Sube (Wh)"] + fila["Baja (Wh)"]
                filas.append(fila)
        return pd.DataFrame(filas)

    df = tabla_caso(base, cargas)
    st.dataframe(df.style.format({"Carga (kg)": "{:.0f}", "Sube (Wh)": "{:+.1f}",
                                  "Baja (Wh)": "{:+.1f}", "Ida y vuelta (Wh)": "{:+.1f}"}), hide_index=True)
    fig = go.Figure()
    for cw, g in df.groupby("Contrapeso", sort=False):
        fig.add_bar(x=g["Carga (kg)"].astype(int).astype(str) + " kg", y=g["Ida y vuelta (Wh)"], name=cw)
    fig.update_layout(barmode="group", xaxis_title="Carga en cabina", yaxis_title="Energía neta ida y vuelta (Wh)",
                      height=420)
    st.plotly_chart(fig, width="stretch")
    st.caption("Con 30 % se gasta menos con cabina vacía o poco cargada (lo más frecuente) y más con cabina llena. "
               "Qué opción ahorra en el día depende del patrón de tráfico del edificio.")

# ---------------- Día típico ----------------
with tabs[4]:
    st.markdown("Consumo diario con el perfil de uso de la ISO 25745-2: viaje medio de "
                f"{ISO['pct_S']:.0f} % del recorrido con la carga media de la categoría, la mitad de los viajes "
                "subiendo y la otra mitad bajando, más el consumo en reposo el resto del día. "
                "Usa los datos fijos del caso (no los controles de la barra lateral).")
    cA, cB = st.columns(2)
    cat = cA.radio("Categoría de uso", [3, 4, 5], index=1, horizontal=True,
                   format_func=lambda c: f"{c} ({ISO['viajes_dia'][c]} viajes/día)")
    eta_d = cB.slider("Eficiencia η del día típico", 0.70, 0.85, CASO["eta_motor"], 0.01)

    @st.cache_data
    def dias(cat_, eta_):
        return {(reg, f): dia(f, cat_, reg, eta_) for reg in (True, False) for f in (0.5, 0.3)}

    D = dias(cat, eta_d)
    filas = []
    for (reg, f), d in D.items():
        filas.append({"Configuración": f"CW {int(f*100)} % · {'con' if reg else 'sin'} regeneración",
                      "En marcha (kWh/día)": d["E_marcha"], "En reposo (kWh/día)": d["E_reposo"],
                      "Total (kWh/día)": d["E_dia"]})
    dfd = pd.DataFrame(filas)
    fig = go.Figure()
    fig.add_bar(x=dfd["Configuración"], y=dfd["En marcha (kWh/día)"], name="En marcha")
    fig.add_bar(x=dfd["Configuración"], y=dfd["En reposo (kWh/día)"], name="En reposo")
    fig.add_hline(y=CASO["Ed_50_Wh_dia"] / 1000, line=dict(dash="dash"), annotation_text="Fuente 50 %")
    fig.add_hline(y=CASO["Ed_30_Wh_dia"] / 1000, line=dict(dash="dot"), annotation_text="Fuente 30 %")
    fig.update_layout(barmode="stack", yaxis_title="kWh/día", height=450)
    st.plotly_chart(fig, width="stretch")
    st.dataframe(dfd.style.format({c: "{:.2f}" for c in dfd.columns[1:]}), hide_index=True)
    d4 = D[(True, 0.5)]
    st.caption(f"Viaje medio: {d4['s_av']:.0f} m con {d4['carga']:.0f} kg, {d4['T']:.1f} s · "
               f"{d4['n_d']} viajes/día · reposo medio {d4['P_reposo']:.0f} W durante {24-d4['t_marcha_h']:.1f} h. "
               "Las líneas punteadas son los valores de la fuente del caso.")

# ---------------- Barrido de masa ----------------
with tabs[5]:
    masas = np.linspace(0, capacidad * 1.2, 25)

    @st.cache_data
    def barrido(base_, masas_):
        out = {}
        for frac in (0.5, 0.3):
            q0 = replace(base_, m_contrapeso=base_.m_cabina + frac * base_.capacidad)
            for nombre, (a, c) in {"sube": (0, base_.n_pisos - 1), "baja": (base_.n_pisos - 1, 0)}.items():
                out[(frac, nombre)] = barrido_masa(replace(q0, piso_ini=a, piso_fin=c), masas_,
                                                   lambda pp: simular(pp, "RK4", 0.02))
        return out

    S = barrido(base, masas)
    fig = go.Figure()
    for (frac, nombre), arr in S.items():
        fig.add_scatter(x=arr[:, 0], y=arr[:, 3] / WH, mode="lines+markers",
                        name=f"CW {int(frac*100)} %, {nombre}",
                        line=dict(dash="solid" if frac == 0.5 else "dash"))
        fig.add_vline(x=frac * capacidad, line=dict(dash="dot", color="gray"),
                      annotation_text=f"m* ({int(frac*100)} %)")
    fig.add_hline(y=0, line=dict(color="black", width=1))
    fig.update_layout(xaxis_title="Masa de pasajeros (kg)", yaxis_title="Energía neta de la red (Wh)  (<0 = recupera)",
                      height=480)
    st.plotly_chart(fig, width="stretch")
    st.caption("Condición de recuperación: subiendo con menos carga que m* = m_cw − m_cabina, "
               "o bajando con más carga que m*, el ascensor devuelve energía (si el variador es regenerativo).")

# ---------------- Euler vs RK4 ----------------
with tabs[6]:
    k = st.selectbox("Escenario", list(escenarios), key="m")
    p = replace(base, m_pasajeros=float(escenarios[k]))
    ref = simular(p, "RK4", 0.001)                    # solución de referencia de paso pequeño
    Be, Br = simular(p, "Euler", dt), simular(p, "RK4", dt)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        subplot_titles=("Velocidad v(t) (m/s)", "Error absoluto en v frente a la referencia (m/s)"))
    fig.add_scatter(x=ref["t"], y=ref["v"], name="Referencia RK4 (dt = 0.001 s)", line=dict(dash="dot", color="black"), row=1, col=1)
    for nombre, B, col in (("Euler", Be, "#ff7f0e"), ("RK4", Br, "#1f77b4")):
        fig.add_scatter(x=B["t"], y=B["v"], name=f"{nombre} (dt = {dt} s)", line=dict(color=col), row=1, col=1)
        fig.add_scatter(x=B["t"], y=np.abs(B["v"] - np.interp(B["t"], ref["t"], ref["v"])),
                        name=f"error {nombre}", line=dict(color=col), showlegend=False, row=2, col=1)
    fig.update_yaxes(type="log", row=2, col=1)
    fig.update_xaxes(title_text="t (s)", row=2, col=1)
    fig.update_layout(height=600)
    st.plotly_chart(fig, width="stretch")
    c1, c2 = st.columns(2)
    for c, nombre, B in ((c1, "Euler", Be), (c2, "RK4", Br)):
        c.metric(f"{nombre}: energía neta", f"{B['E_red_neta'][-1]/WH:.2f} Wh",
                 f"{(B['E_red_neta'][-1]-ref['E_red_neta'][-1])/WH:+.3f} Wh vs referencia", delta_color="off")
    st.write(f"τ = {p.tau:.3f} s · dt/τ = {dt/p.tau:.2f} · Euler es estable solo si dt < 2τ = {2*p.tau:.3f} s.")

# ---------------- Validación ----------------
with tabs[7]:
    st.markdown("Caso con solución analítica: escalón de velocidad (v_ref constante) con la misma ecuación del modelo.  \n"
                r"$v(t)=v_0\,(1-e^{-t/\tau}),\qquad \tau=\dfrac{m_{ef}}{K_p+b}$")
    p = replace(base, m_pasajeros=float(escenarios["A"]))
    filas = val.errores(p)
    df = pd.DataFrame(filas)
    st.dataframe(df.style.format("{:.3e}"), hide_index=True)
    fig = go.Figure()
    fig.add_scatter(x=df["dt"], y=df["Euler_abs"], name="Euler", mode="lines+markers")
    fig.add_scatter(x=df["dt"], y=df["RK4_abs"], name="RK4", mode="lines+markers")
    fig.update_xaxes(type="log", title="dt (s)")
    fig.update_yaxes(type="log", title="Error abs. máx. en v (m/s)")
    st.plotly_chart(fig, width="stretch")
    st.write(f"Orden de convergencia observado (pasos con dt ≤ τ/2): "
             f"Euler ≈ {val.orden_convergencia(filas, 'Euler_abs', p.tau):.2f} (teórico 1), "
             f"RK4 ≈ {val.orden_convergencia(filas, 'RK4_abs', p.tau):.2f} (teórico 4).")
    e = val.contraste_scipy(p)
    if e is not None:
        st.caption(f"Contraste independiente (solo validación) con solve_ivp de SciPy: error abs. máx. = {e:.1e} m/s.")
