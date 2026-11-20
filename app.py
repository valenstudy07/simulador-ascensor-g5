"""Simulador de ascensor regenerativo: contrapeso al 50 % frente al 30 % y variador regenerativo.
Streamlit + Plotly. Ejecutar:  streamlit run app.py
"""
from dataclasses import replace
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from parametros import CASO, ISO
from modelo import Params, perfil_velocidad
from simulacion import simular
from energia import barrido_masa, interpretar, J_POR_WH
import validacion as val
from dia_tipico import dia

WH = J_POR_WH
VERDE, NARANJA, GRIS = "#2e9d5b", "#e8822a", "#9aa0a6"
COLORES = {"A": "#1f77b4", "B": "#8e44ad", "C": "#c0392b"}

st.set_page_config(page_title="Ascensor regenerativo · Caso de estudio", layout="wide")
st.markdown("""
<style>
div[data-testid="stMetricValue"] {font-size: 1.35rem;}
.etiqueta {display:inline-block; padding:2px 10px; border-radius:12px; font-weight:600; font-size:0.9rem;}
.recupera {background:#e3f4ea; color:#1f7a45;}
.consume  {background:#fdeedd; color:#b35c14;}
.nota {color:#5f6368; font-size:0.92rem;}
</style>
""", unsafe_allow_html=True)


def chip(neta_wh):
    if neta_wh < 0:
        return f'<span class="etiqueta recupera">Recupera {-neta_wh:.1f} Wh</span>'
    return f'<span class="etiqueta consume">Consume {neta_wh:.1f} Wh</span>'


def dato(col, titulo, valor, nota=None, color=None):
    """Tarjeta de dato: título, valor grande y una nota corta (sin flechas de variación)."""
    estilo = f"color:{color};" if color else ""
    nota_html = f"<div class='nota' style='margin-top:-4px'>{nota}</div>" if nota else ""
    col.markdown(f"<div style='font-size:0.88rem;color:#5f6368'>{titulo}</div>"
                 f"<div style='font-size:1.45rem;font-weight:600;{estilo}'>{valor}</div>{nota_html}",
                 unsafe_allow_html=True)


def ayuda(texto):
    """Bloque plegable 'Cómo leer esta pestaña'."""
    with st.expander("Cómo leer esta pestaña"):
        st.markdown(texto)


st.title("Simulador de ascensor regenerativo")
st.markdown(
    f"<p class='nota'>Caso de estudio: ascensor de oficinas de {CASO['n_paradas']} paradas y {CASO['recorrido']:.0f} m de recorrido, "
    f"cabina de {CASO['m_cabina']:.0f} kg, carga nominal de {CASO['carga_nominal']:.0f} kg y velocidad de {CASO['v_nominal']} m/s. "
    "Los valores de la barra lateral son los del caso; puedes cambiarlos para explorar.</p>", unsafe_allow_html=True)

with st.expander("¿Qué hace este simulador y cómo se usa?", expanded=False):
    st.markdown(
        """
Un ascensor de tracción funciona como una balanza: la **cabina** cuelga de un lado del cable y el **contrapeso** del otro.
El motor solo mueve la diferencia de peso. Cuando **baja el lado más pesado**, el motor frena y funciona como generador:
con un **variador regenerativo** esa energía vuelve a la red del edificio; sin él, se pierde como calor.

**Cómo usarlo**
1. En la barra lateral elige el viaje (piso inicial y final) y el contrapeso (50 % o 30 %).
2. Abajo, en *Escenarios*, elige tres cargas de pasajeros para comparar el mismo viaje.
3. Recorre las pestañas: la animación muestra el movimiento, las demás explican la energía y los métodos numéricos.

**Palabras clave**
- **Contrapeso al 50 % / 30 %:** pesa lo mismo que la cabina vacía más el 50 % o el 30 % de la carga nominal.
- **Carga crítica m\\*:** masa de pasajeros con la que los dos lados pesan lo mismo (m\\* = contrapeso − cabina).
- **Energía neta:** lo que el ascensor toma de la red menos lo que devuelve. **Negativa = recupera energía.**
- **Eficiencia η:** parte de la energía que no se pierde en el motor y la electrónica.
""")

# ---------------- Entradas ----------------
sb = st.sidebar
if sb.button("↺ Restablecer valores del caso"):
    st.session_state.clear()
    st.rerun()

sb.header("1. Viaje")
n_pisos = sb.slider("Número de paradas", 2, 40, CASO["n_paradas"])
h_piso = sb.number_input("Altura entre paradas (m)", 2.0, 6.0, CASO["h_piso"], 0.05, format="%.3f")
sb.caption("La cabina parte del reposo en el piso inicial.")
piso_ini = sb.slider("Piso inicial", 0, n_pisos - 1, 0)
piso_fin = sb.slider("Piso final", 0, n_pisos - 1, n_pisos - 1)
v_max = sb.slider("Velocidad de desplazamiento (m/s)", 0.5, 6.0, CASO["v_nominal"], 0.1)
a_ref = sb.slider("Aceleración del perfil (m/s²)", 0.3, 2.0, CASO["a_nominal"], 0.1)

sb.header("2. Ascensor y contrapeso")
m_cab = sb.number_input("Masa de cabina vacía (kg)", 300.0, 3000.0, CASO["m_cabina"], 10.0)
capacidad = sb.number_input("Carga nominal (kg)", 200.0, 3000.0, CASO["carga_nominal"], 10.0)
opcion_cw = sb.radio("Equilibrado del contrapeso",
                     ["50 % (tradicional)", "30 % (optimizado)", "Personalizado"])
if opcion_cw.startswith("50"):
    factor_cw = 0.5
elif opcion_cw.startswith("30"):
    factor_cw = 0.3
else:
    factor_cw = sb.slider("Fracción de la carga nominal que equilibra", 0.0, 1.0, 0.4, 0.05)
m_cw = m_cab + factor_cw * capacidad
m_crit = m_cw - m_cab
sb.markdown(f"Contrapeso = {m_cab:.0f} + {factor_cw:.2f} × {capacidad:.0f} = **{m_cw:.0f} kg**  \n"
            f"Carga crítica m\\* = **{m_crit:.0f} kg** (≈ {m_crit/CASO['m_pasajero']:.0f} personas)")

sb.header("3. Pérdidas y variador")
b = sb.number_input("Fricción viscosa b (N·s/m), supuesto", 0.0, 500.0, CASO["b"], 5.0)
eta = sb.slider("Eficiencia del motor y el variador η", 0.5, 1.0, CASO["eta_motor"], 0.01)
eta_reg = sb.slider("Eficiencia de regeneración", 0.0, 1.0, CASO["eta_regen"], 0.01)
regen = sb.checkbox("Variador regenerativo (devuelve energía a la red)", True)

sb.header("4. Método numérico")
metodo = sb.radio("Método", ["RK4", "Euler"])
dt = sb.select_slider("Paso de integración Δt (s)", [0.2, 0.1, 0.05, 0.02, 0.01, 0.005], 0.01)

base = Params(m_cabina=m_cab, capacidad=capacidad, m_contrapeso=m_cw, b=b, n_pisos=n_pisos,
              h_piso=h_piso, piso_ini=piso_ini, piso_fin=piso_fin, v_max=v_max, a_ref=a_ref,
              eta_motor=eta, eta_regen=eta_reg, regenerativo=regen)

# ---------------- Resumen del viaje ----------------
dist = base.distancia
if dist > 0:
    sentido_txt = f"sube {dist:.1f} m"
elif dist < 0:
    sentido_txt = f"baja {-dist:.1f} m"
else:
    sentido_txt = "no se mueve (piso inicial = piso final)"
r1, r2, r3, r4 = st.columns(4)
dato(r1, "Viaje", f"Piso {piso_ini} → {piso_fin}", f"La cabina {sentido_txt}")
dato(r2, "Contrapeso", f"{m_cw:.0f} kg", f"Equilibra el {factor_cw*100:.0f} % de la carga nominal")
dato(r3, "Carga crítica m*", f"{m_crit:.0f} kg", "Con esta carga los dos lados pesan igual")
dato(r4, "Variador", "Regenerativo" if regen else "Sin regeneración", f"Método {metodo}, Δt = {dt} s")

# ---------------- Escenarios ----------------
st.subheader("Escenarios: el mismo viaje con tres cargas de pasajeros")
st.markdown("<p class='nota'>Cada escenario es el viaje de arriba con una cantidad distinta de pasajeros. "
            "Así se ve cómo cambia la energía según el lado que pesa más.</p>", unsafe_allow_html=True)
mp = CASO["m_pasajero"]
tope = int(capacidad * 1.2)
cols = st.columns(3)
defaults = {"A": 0, "B": int(capacidad * 0.5), "C": int(capacidad)}
escenarios = {}
for col, k in zip(cols, "ABC"):
    escenarios[k] = col.slider(f"Escenario {k}: pasajeros (kg)", 0, tope, defaults[k], 25)


@st.cache_data
def correr(p, metodo, dt):
    return simular(p, metodo, dt)


res = {k: correr(replace(base, m_pasajeros=float(m)), metodo, dt) for k, m in escenarios.items()}


def nombre_carga(m):
    if m == 0:
        return "cabina vacía"
    if m >= capacidad:
        return "cabina llena"
    return f"≈ {m/mp:.1f} personas"


def etiqueta(k):
    return f"{k} · {escenarios[k]:.0f} kg ({nombre_carga(escenarios[k])})"


def lado_pesado(m):
    d = m_cab + m - m_cw
    if abs(d) < 1e-9:
        return "Los dos lados pesan igual"
    return f"Pesa más la cabina (+{d:.0f} kg)" if d > 0 else f"Pesa más el contrapeso (+{-d:.0f} kg)"


for col, k in zip(cols, "ABC"):
    with col.container(border=True):
        neta = res[k]["E_red_neta"][-1] / WH
        st.markdown(f"**{etiqueta(k)}**  \n{lado_pesado(escenarios[k])}  \n{chip(neta)}", unsafe_allow_html=True)

tabs = st.tabs(["Animación", "Movimiento y potencia", "Balance de energía", "Caso: 30 % vs 50 %",
                "Día típico (ISO 25745-2)", "Energía según la carga", "Euler vs RK4", "Validación"])

# ---------------- Animación ----------------
with tabs[0]:
    c_sel, c_txt = st.columns([1, 2])
    k = c_sel.selectbox("Escenario a animar", list(escenarios), format_func=etiqueta)
    B = res[k]
    p = replace(base, m_pasajeros=float(escenarios[k]))
    c_txt.markdown(f"**Qué pasa en este viaje:** {interpretar(B, p)}")

    H = (n_pisos - 1) * h_piso
    y0 = piso_ini * h_piso
    paso = max(1, len(B["t"]) // 150)
    idx = list(range(0, len(B["t"]), paso))
    if idx[-1] != len(B["t"]) - 1:
        idx.append(len(B["t"]) - 1)
    E_neta = B["E_red_neta"] / WH
    _, T_ref, _ = perfil_velocidad(p)
    t_a = min(p.v_max, np.sqrt(p.a_ref * abs(p.distancia))) / p.a_ref if p.distancia else 0.0

    alto = max(4.0, 0.9 * h_piso)           # alto de las cajas (m)
    XC, XW = (0.0, 2.4), (3.6, 4.6)         # posición horizontal de cabina y contrapeso
    xc, xw = sum(XC) / 2, sum(XW) / 2
    XP = 6.6                                # columna del panel de lectura

    def caja(x, y0_, color, nombre):
        return go.Scatter(x=[x[0], x[0], x[1], x[1], x[0]], y=[y0_, y0_ + alto, y0_ + alto, y0_, y0_],
                          fill="toself", mode="lines", line=dict(color="#333"), fillcolor=color, name=nombre,
                          hoverinfo="name")

    def fase(t):
        if t > T_ref:
            return "detenido"
        if t < t_a:
            return "acelerando"
        if t < T_ref - t_a:
            return "velocidad constante"
        return "frenando"

    def anotaciones(i):
        P = B["P"][i]
        if abs(B["v"][i]) < 1e-3 and abs(P) < 50:
            estado, color = "en reposo", GRIS
        elif P < 0:
            estado, color = "el motor GENERA: devuelve energía", VERDE
        else:
            estado, color = "el motor CONSUME energía de la red", NARANJA
        dir_v = "sube" if B["v"][i] > 1e-3 else ("baja" if B["v"][i] < -1e-3 else "quieta")
        fijas = [
            dict(x=xc, y=-2.6, text="① Cabina", showarrow=False, font=dict(size=13)),
            dict(x=xw, y=-2.6, text="② Contrapeso", showarrow=False, font=dict(size=13)),
            dict(x=(xc + xw) / 2 - 1.4, y=H + 6.2, xanchor="right", text="③ Polea y motor", showarrow=False, font=dict(size=13)),
        ]
        filas = [
            ("④ Lo que pasa en este instante", None, 15),
            (f"Tiempo: <b>{B['t'][i]:.1f} s</b> ({fase(B['t'][i])})", None, 13),
            (f"Velocidad de la cabina: <b>{B['v'][i]:+.2f} m/s</b> ({dir_v})", None, 13),
            (f"Potencia del motor: <b>{P/1e3:+.1f} kW</b>", None, 13),
            (estado, color, 14),
            (f"Energía neta acumulada: <b>{E_neta[i]:+.1f} Wh</b>", None, 13),
            ("(negativa = el ascensor ya devolvió más de lo que tomó)", "#5f6368", 11),
        ]
        panel = [dict(x=XP, y=H * (0.92 - 0.075 * j), xanchor="left", text=txt, showarrow=False,
                      font=dict(size=sz, color=col or "#202124")) for j, (txt, col, sz) in enumerate(filas)]
        return fijas + panel, color

    def cuadro(i):
        ycab = y0 + B["y"][i]
        ycw = H - ycab
        anot, color = anotaciones(i)
        cable = go.Scatter(x=[xc, xc, xw, xw], y=[ycab + alto, H + 5.2, H + 5.2, ycw + alto], mode="lines",
                           line=dict(color="#888", width=1.5), hoverinfo="skip", name="cable")
        polea = go.Scatter(x=[(xc + xw) / 2], y=[H + 5.2], mode="markers",
                           marker=dict(size=30, color=color, line=dict(color="#333", width=2)),
                           hoverinfo="skip", name="polea")
        flecha = go.Scatter(x=[xc], y=[ycab + alto / 2], mode="markers", hoverinfo="skip", name="sentido",
                            marker=dict(symbol="triangle-up" if B["v"][i] >= 0 else "triangle-down",
                                        size=16 if abs(B["v"][i]) > 1e-3 else 0, color="#1f3b57"))
        return go.Frame(data=[cable, polea, caja(XC, ycab, "#9ecae1", "cabina"),
                              caja(XW, ycw, "#bdbdbd", "contrapeso"), flecha],
                        name=str(i), layout=go.Layout(annotations=anot))

    frames = [cuadro(i) for i in idx]
    fig = go.Figure(data=frames[0].data, frames=frames)
    for j in range(n_pisos):
        fig.add_hline(y=j * h_piso, line=dict(color="#e6e6e6", width=1))
    fig.update_layout(annotations=frames[0].layout.annotations,
                      xaxis=dict(range=[-1.5, 16], visible=False),
                      yaxis=dict(range=[-4, H + 10], title="Altura (m)"),
                      showlegend=False, height=640, margin=dict(t=20),
                      updatemenus=[dict(type="buttons", x=0.0, y=1.06, xanchor="left", direction="left", buttons=[
                          dict(label="▶ Reproducir", method="animate",
                               args=[None, dict(frame=dict(duration=40, redraw=True), fromcurrent=True)]),
                          dict(label="⏸ Pausa", method="animate",
                               args=[[None], dict(mode="immediate", frame=dict(duration=0))])])],
                      sliders=[dict(steps=[dict(method="animate", label=f"{B['t'][i]:.0f}",
                                                args=[[str(i)], dict(mode="immediate", frame=dict(duration=0))])
                                           for i in idx], currentvalue=dict(prefix="Tiempo (s) = "))])
    fig.add_shape(type="rect", x0=XP - 0.3, x1=15.8, y0=H * 0.4, y1=H * 0.98, fillcolor="#f8f9fa",
                  line=dict(color="#dadce0"), layer="below")
    st.plotly_chart(fig, width="stretch")
    st.markdown(
        f"<p class='nota'>① La cabina (azul) y ② el contrapeso (gris) se mueven en sentidos opuestos; la flecha indica hacia dónde va la cabina. "
        f"③ La polea se pone <b style='color:{VERDE}'>verde</b> cuando el motor genera energía y "
        f"<b style='color:{NARANJA}'>naranja</b> cuando la consume. ④ El panel de la derecha muestra los valores en cada instante. "
        "Pulsa ▶ Reproducir o arrastra la barra de tiempo.</p>", unsafe_allow_html=True)

# ---------------- Movimiento y potencia ----------------
with tabs[1]:
    st.markdown("**Cómo se mueve la cabina en los tres escenarios y cuánta potencia usa el motor.** "
                "Las franjas marcan las fases del viaje: aceleración, velocidad constante y frenado.")
    ayuda("""
- **Posición y velocidad** son casi iguales en los tres escenarios: el control del motor hace que la cabina siga
  la misma velocidad pedida sin importar la carga.
- **Potencia del motor:** lo que cambia con la carga. **Zona naranja (arriba de 0):** el motor consume energía.
  **Zona verde (abajo de 0):** el motor genera y, con variador regenerativo, devuelve energía a la red.
- Los picos al inicio y al final son la energía para acelerar y la que se recupera al frenar.
""")
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        subplot_titles=("Posición de la cabina (m)", "Velocidad de la cabina (m/s)",
                                        "Potencia del motor (kW)"))
    for k, B in res.items():
        kw = dict(line=dict(color=COLORES[k]), legendgroup=k)
        fig.add_scatter(x=B["t"], y=B["y"], row=1, col=1, name=etiqueta(k), **kw)
        fig.add_scatter(x=B["t"], y=B["v"], row=2, col=1, showlegend=False, name=k, **kw)
        fig.add_scatter(x=B["t"], y=B["P"] / 1e3, row=3, col=1, showlegend=False, name=k, **kw)
    pmax = max(np.abs(B["P"]).max() for B in res.values()) / 1e3 * 1.15 + 1
    fig.add_hrect(y0=0, y1=pmax, fillcolor=NARANJA, opacity=0.08, line_width=0, row=3, col=1)
    fig.add_hrect(y0=-pmax, y1=0, fillcolor=VERDE, opacity=0.08, line_width=0, row=3, col=1)
    fig.add_annotation(text="consume", x=0.99, xref="x3 domain", y=pmax * 0.85, yref="y3", showarrow=False,
                       xanchor="right", font=dict(color=NARANJA))
    fig.add_annotation(text="genera / recupera", x=0.99, xref="x3 domain", y=-pmax * 0.85, yref="y3",
                       showarrow=False, xanchor="right", font=dict(color=VERDE))
    fig.update_yaxes(range=[-pmax, pmax], row=3, col=1)
    _, T_ref, _ = perfil_velocidad(base)
    if base.distancia:
        t_a = min(base.v_max, np.sqrt(base.a_ref * abs(base.distancia))) / base.a_ref
        for x0, x1, nombre in [(0, t_a, "acelera"), (t_a, T_ref - t_a, "velocidad constante"), (T_ref - t_a, T_ref, "frena")]:
            if x1 > x0:
                fig.add_vrect(x0=x0, x1=x1, fillcolor="#e8eaed" if nombre != "velocidad constante" else "white",
                              opacity=0.6, line_width=0, layer="below", row="all", col=1)
                fig.add_annotation(text=nombre, x=(x0 + x1) / 2, xref="x2", y=0.03, yref="y2 domain",
                                   showarrow=False, yanchor="bottom", font=dict(size=11, color="#5f6368"))
    fig.add_hline(y=0, row=3, col=1, line=dict(color="black", width=1))
    fig.update_xaxes(title_text="Tiempo (s)", row=3, col=1)
    fig.update_layout(height=760, legend=dict(orientation="h", y=-0.08))
    st.plotly_chart(fig, width="stretch")

# ---------------- Balance de energía ----------------
with tabs[2]:
    c_sel, c_txt = st.columns([1, 2])
    k = c_sel.selectbox("Escenario", list(escenarios), format_func=etiqueta, key="e")
    B = res[k]
    p = replace(base, m_pasajeros=float(escenarios[k]))
    c_txt.markdown(f"**Qué pasa en este viaje:** {interpretar(B, p)}")

    dEp = (B["Ep"][-1] - B["Ep"][0]) / WH
    fric = B["E_fric"][-1] / WH
    cons, rec, neta = B["E_cons"][-1] / WH, B["E_rec"][-1] / WH, B["E_red_neta"][-1] / WH
    m1, m2, m3, m4 = st.columns(4)
    dato(m1, "Tomada de la red", f"{cons:.1f} Wh", "Lo que el motor consume")
    dato(m2, "Devuelta a la red", f"{rec:.1f} Wh", "Lo que el motor genera y llega a la red")
    dato(m3, "Energía neta", f"{neta:+.1f} Wh", "Negativa: el viaje recupera" if neta < 0 else "Positiva: el viaje consume",
         VERDE if neta < 0 else NARANJA)
    dato(m4, "Error de conservación", f"{abs(B['err_cons']).max():.2f} J", "Debe ser casi 0")

    st.markdown("**¿De dónde sale y a dónde va la energía del viaje?**")
    ayuda("""
Cada barra se lee de izquierda a derecha, como una cuenta:
1. **Energía potencial:** lo que el sistema gana (barra hacia arriba) o libera (hacia abajo) porque el lado más pesado sube o baja.
2. **Fricción:** energía que se pierde por rozamiento.
3. **Motor y variador:** lo que se pierde por la eficiencia η (siempre se pierde algo, al consumir y al generar).
4. **Neta de la red:** el resultado. **Negativa = el ascensor devolvió energía.**

Ejemplo del caso (cabina vacía subiendo al 50 %): el contrapeso libera 102,2 Wh, la fricción se lleva 2,5 Wh,
el motor y el variador unos 15 Wh, y vuelven a la red 84,7 Wh.
""")
    # Cuenta: E_red_neta = ΔEp + E_fric + pérdidas eléctricas  (energía cinética final ≈ 0)
    perd_el = neta - dEp - fric - (B["Ec"][-1] - B["Ec"][0]) / WH
    fig = go.Figure(go.Waterfall(
        orientation="v", measure=["relative", "relative", "relative", "total"],
        x=["Energía potencial<br>(sube + / baja −)", "Pérdida por<br>fricción", "Pérdida en motor<br>y variador", "Neta de la red"],
        y=[dEp, fric, perd_el, 0], text=[f"{dEp:+.1f}", f"+{fric:.1f}", f"+{perd_el:.1f}", f"{neta:+.1f}"],
        textposition="outside", connector=dict(line=dict(color="#bbb")),
        increasing=dict(marker=dict(color=NARANJA)), decreasing=dict(marker=dict(color=VERDE)),
        totals=dict(marker=dict(color=VERDE if neta < 0 else NARANJA))))
    fig.add_hline(y=0, line=dict(color="black", width=1))
    fig.update_layout(yaxis_title="Energía (Wh)", height=420, showlegend=False, margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")

    with st.expander("Ver cómo cambia cada energía durante el viaje"):
        fig = go.Figure()
        curvas = [("Energía potencial neta (ΔEp)", "Ep", True), ("Pérdida por fricción", "E_fric", True),
                  ("Tomada de la red", "E_cons", True), ("Devuelta a la red", "E_rec", True),
                  ("Energía cinética", "Ec", "legendonly"), ("Trabajo neto del motor", "E_mot", "legendonly"),
                  ("Disipada en resistencia / pérdidas al regenerar", "E_resistencia", "legendonly")]
        for nombre, clave, vis in curvas:
            y = (B[clave] - (B[clave][0] if clave == "Ep" else 0)) / WH
            fig.add_scatter(x=B["t"], y=y, name=nombre, visible=vis)
        fig.update_layout(xaxis_title="Tiempo (s)", yaxis_title="Energía acumulada (Wh)", height=420)
        st.plotly_chart(fig, width="stretch")
        st.caption("Haz clic en la leyenda para mostrar u ocultar curvas. Las curvas ocultas al inicio son las de apoyo.")

    with st.expander("Verificación de la conservación de la energía"):
        st.markdown("El trabajo del motor debe ser igual al cambio de energía cinética, más el de energía potencial, "
                    "más lo perdido por fricción: **W_motor = ΔEc + ΔEp + E_fricción**. "
                    "La curva muestra la diferencia en cada instante; debe quedarse cerca de 0. "
                    "Con RK4 es despreciable; con Euler y un paso grande crece.")
        figc = go.Figure(go.Scatter(x=B["t"], y=B["err_cons"], line=dict(color="#555")))
        figc.update_layout(xaxis_title="Tiempo (s)", yaxis_title="Diferencia (J)", height=280, margin=dict(t=10))
        st.plotly_chart(figc, width="stretch")

    st.markdown("**Los tres escenarios**")
    tabla = pd.DataFrame({etiqueta(k2): {
        "Tomada de la red (Wh)": R["E_cons"][-1] / WH, "Devuelta a la red (Wh)": R["E_rec"][-1] / WH,
        "Neta (Wh)": R["E_red_neta"][-1] / WH, "Fricción (Wh)": R["E_fric"][-1] / WH,
        "Resultado": "Recupera" if R["E_red_neta"][-1] < 0 else "Consume"} for k2, R in res.items()}).T
    st.dataframe(tabla.style.format({c: "{:.1f}" for c in tabla.columns if c != "Resultado"}))

# ---------------- Caso: 30 % vs 50 % ----------------
with tabs[3]:
    st.markdown(f"**¿Qué contrapeso gasta menos?** Se simula el viaje completo entre el piso 0 y el piso {n_pisos-1}, "
                "subiendo y bajando, con los dos contrapesos del caso y cinco cargas de pasajeros.")
    ayuda("""
- **Gráfica:** energía de un viaje de **ida y vuelta** (subir y volver a bajar). Barras más bajas = menos consumo.
- **Con poca carga** (lo normal en una oficina) gana el contrapeso al **30 %**; **con mucha carga** gana el de **50 %**.
  Los dos gastan lo mismo con unos 400 kg.
- **Tabla:** el detalle de cada sentido. Un valor **negativo** significa que ese viaje devuelve energía a la red.
- Usa la masa de la cabina, la carga nominal, las pérdidas y el variador de la barra lateral; siempre con RK4 y Δt = 0,01 s.
""")
    cargas = [0.0, 0.25 * capacidad, 0.5 * capacidad, 0.75 * capacidad, capacidad]

    @st.cache_data
    def tabla_caso(base_, cargas_):
        filas = []
        for frac in (0.5, 0.3):
            q0 = replace(base_, m_contrapeso=base_.m_cabina + frac * base_.capacidad)
            for m in cargas_:
                fila = {"Contrapeso": f"{int(frac*100)} % ({q0.m_contrapeso:.0f} kg)", "Carga (kg)": m}
                for nombre, (a, c) in {"Sube (Wh)": (0, base_.n_pisos - 1), "Baja (Wh)": (base_.n_pisos - 1, 0)}.items():
                    R = simular(replace(q0, m_pasajeros=m, piso_ini=a, piso_fin=c), "RK4", 0.01)
                    fila[nombre] = R["E_red_neta"][-1] / WH
                fila["Ida y vuelta (Wh)"] = fila["Sube (Wh)"] + fila["Baja (Wh)"]
                filas.append(fila)
        return pd.DataFrame(filas)

    df = tabla_caso(base, cargas)
    fig = go.Figure()
    for (cw, g), color in zip(df.groupby("Contrapeso", sort=False), ["#5b8def", "#f2a541"]):
        fig.add_bar(x=g["Carga (kg)"].astype(int).astype(str) + " kg", y=g["Ida y vuelta (Wh)"], name=f"Contrapeso {cw}",
                    marker_color=color, text=g["Ida y vuelta (Wh)"].map(lambda v: f"{v:.1f}"), textposition="outside")
    fig.update_layout(barmode="group", xaxis_title="Pasajeros en la cabina", yaxis_title="Energía neta ida y vuelta (Wh)",
                      height=440, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(df.style.format({"Carga (kg)": "{:.0f}", "Sube (Wh)": "{:+.1f}",
                                  "Baja (Wh)": "{:+.1f}", "Ida y vuelta (Wh)": "{:+.1f}"}), hide_index=True)

# ---------------- Día típico ----------------
with tabs[4]:
    st.markdown("**¿Cuánto gasta el ascensor en un día de oficina?** Se suma la energía de todos los viajes del día "
                "y la del ascensor parado esperando llamadas.")
    ayuda("""
- **Categoría de uso:** cuánto se usa el ascensor según la norma ISO 25745-2. La **categoría 4** (750 viajes al día)
  corresponde a un edificio de oficinas, que es el caso. La 3 y la 5 sirven para ver qué pasa con menos o más uso.
- Cada viaje es el **viaje medio** de la norma (49, 44 o 39 % del recorrido, con la carga media de la categoría),
  la mitad subiendo y la otra mitad bajando.
- **Barras:** azul oscuro = energía en movimiento; claro = energía en reposo (luces y electrónica encendidas).
  El reposo es igual con los dos contrapesos, así que no cambia el ahorro.
- **Líneas punteadas:** consumo que reporta la fuente del caso, que no tiene variador regenerativo.
  Por eso se compara con las barras **sin regeneración**.
- Esta pestaña usa los datos fijos del caso, no los de la barra lateral.
""")
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
    ah_con = D[(True, 0.5)]["E_dia"] - D[(True, 0.3)]["E_dia"]
    ah_sin = D[(False, 0.5)]["E_dia"] - D[(False, 0.3)]["E_dia"]
    m1, m2 = st.columns(2)
    dato(m1, "Ahorro del contrapeso al 30 %, con regeneración", f"{ah_con:.2f} kWh/día",
         f"{100*ah_con/D[(True, 0.5)]['E_dia']:.1f} % menos que con el de 50 %", VERDE)
    dato(m2, "Ahorro del contrapeso al 30 %, sin regeneración", f"{ah_sin:.2f} kWh/día",
         f"{100*ah_sin/D[(False, 0.5)]['E_dia']:.1f} % menos que con el de 50 %", VERDE)
    fig = go.Figure()
    fig.add_bar(x=dfd["Configuración"], y=dfd["En marcha (kWh/día)"], name="En movimiento", marker_color="#1f5f99")
    fig.add_bar(x=dfd["Configuración"], y=dfd["En reposo (kWh/día)"], name="En reposo", marker_color="#a9c8e8")
    fig.add_hline(y=CASO["Ed_50_Wh_dia"] / 1000, line=dict(dash="dash", color="#555"), annotation_text="Fuente, 50 %")
    fig.add_hline(y=CASO["Ed_30_Wh_dia"] / 1000, line=dict(dash="dot", color="#555"), annotation_text="Fuente, 30 %")
    fig.update_layout(barmode="stack", yaxis_title="kWh/día", height=450, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(dfd.style.format({c: "{:.2f}" for c in dfd.columns[1:]}), hide_index=True)
    d4 = D[(True, 0.5)]
    st.caption(f"Viaje medio: {d4['s_av']:.0f} m con {d4['carga']:.0f} kg, {d4['T']:.1f} s · "
               f"{d4['n_d']} viajes/día · reposo medio {d4['P_reposo']:.0f} W durante {24-d4['t_marcha_h']:.1f} h.")

# ---------------- Energía según la carga ----------------
with tabs[5]:
    st.markdown("**¿Con cuántos pasajeros el ascensor deja de recuperar y empieza a consumir?** "
                "Energía de un viaje completo según la carga, para los dos contrapesos y los dos sentidos.")
    ayuda("""
- **Zona verde (abajo de 0):** el viaje devuelve energía. **Zona naranja (arriba de 0):** el viaje consume.
- Cada línea cruza el cero cerca de la **carga crítica m\\*** (líneas punteadas verticales): 500 kg con el
  contrapeso al 50 % y 300 kg con el de 30 %.
- **Subiendo**, se recupera con menos carga que m\\* (baja el contrapeso, que pesa más).
  **Bajando**, se recupera con más carga que m\\* (baja la cabina, que pesa más).
- Con la carga exactamente igual a m\\* el viaje no cuesta cero: consume unos pocos Wh por las pérdidas.
""")
    masas = np.linspace(0, capacidad * 1.2, 25)

    @st.cache_data
    def barrido(base_, masas_):
        out = {}
        for frac in (0.5, 0.3):
            q0 = replace(base_, m_contrapeso=base_.m_cabina + frac * base_.capacidad)
            for nombre, (a, c) in {"sube": (0, base_.n_pisos - 1), "baja": (base_.n_pisos - 1, 0)}.items():
                out[(frac, nombre)] = barrido_masa(replace(q0, piso_ini=a, piso_fin=c), masas_,
                                                   lambda pp: simular(pp, "RK4", 0.01))
        return out

    S = barrido(base, masas)
    fig = go.Figure()
    emax = max(np.abs(arr[:, 3]).max() for arr in S.values()) / WH * 1.1
    fig.add_hrect(y0=0, y1=emax, fillcolor=NARANJA, opacity=0.07, line_width=0)
    fig.add_hrect(y0=-emax, y1=0, fillcolor=VERDE, opacity=0.07, line_width=0)
    fig.add_annotation(text="consume", x=0.01, xref="x domain", y=emax * 0.9, showarrow=False, xanchor="left",
                       font=dict(color=NARANJA))
    fig.add_annotation(text="recupera", x=0.01, xref="x domain", y=-emax * 0.9, showarrow=False, xanchor="left",
                       font=dict(color=VERDE))
    estilos = {(0.5, "sube"): ("#1f5f99", "solid"), (0.5, "baja"): ("#1f5f99", "dash"),
               (0.3, "sube"): ("#d9822b", "solid"), (0.3, "baja"): ("#d9822b", "dash")}
    for (frac, nombre), arr in S.items():
        color, dash = estilos[(frac, nombre)]
        fig.add_scatter(x=arr[:, 0], y=arr[:, 3] / WH, mode="lines+markers", marker=dict(size=5),
                        name=f"Contrapeso {int(frac*100)} %, cabina {nombre}", line=dict(color=color, dash=dash))
    for frac in (0.5, 0.3):
        fig.add_vline(x=frac * capacidad, line=dict(dash="dot", color="gray"),
                      annotation_text=f"m* = {frac*capacidad:.0f} kg ({int(frac*100)} %)", annotation_position="top")
    fig.add_hline(y=0, line=dict(color="black", width=1))
    fig.update_yaxes(range=[-emax, emax])
    fig.update_layout(xaxis_title="Masa de pasajeros (kg)", yaxis_title="Energía neta del viaje (Wh)",
                      height=500, legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch")

# ---------------- Euler vs RK4 ----------------
with tabs[6]:
    st.markdown(f"**¿Qué tan bien resuelve cada método la ecuación?** Se compara Euler y RK4 con el paso elegido en la barra "
                f"lateral (Δt = {dt} s) contra una solución de referencia con un paso muy pequeño (RK4, Δt = 0,001 s).")
    ayuda("""
- **Gráfica de arriba:** la velocidad de la cabina. Si un método se separa de la línea negra punteada, está cometiendo error.
- **Gráfica de abajo:** el tamaño del error en cada instante (escala logarítmica: cada línea horizontal es 10 veces más).
  RK4 queda muy por debajo de Euler con el mismo paso.
- Prueba un paso grande (0,1 o 0,2 s) en la barra lateral: Euler se separa de la referencia cuando la velocidad cambia (al arrancar y al frenar).
- Euler solo es **estable** si Δt < 2τ, pero estable no quiere decir preciso.
""")
    k = st.selectbox("Escenario", list(escenarios), format_func=etiqueta, key="m")
    p = replace(base, m_pasajeros=float(escenarios[k]))
    ref = simular(p, "RK4", 0.001)                    # solución de referencia de paso pequeño
    Be, Br = simular(p, "Euler", dt), simular(p, "RK4", dt)
    c1, c2, c3 = st.columns(3)
    for c, nombre, B in ((c1, "Euler", Be), (c2, "RK4", Br)):
        dato(c, f"{nombre}: energía neta", f"{B['E_red_neta'][-1]/WH:.2f} Wh",
             f"{(B['E_red_neta'][-1]-ref['E_red_neta'][-1])/WH:+.4f} Wh de diferencia con la referencia")
    dato(c3, "Constante de tiempo τ", f"{p.tau:.3f} s", f"Δt/τ = {dt/p.tau:.2f}; Euler es estable si Δt < {2*p.tau:.3f} s")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=("Velocidad de la cabina (m/s)", "Error en la velocidad frente a la referencia (m/s)"))
    fig.add_scatter(x=ref["t"], y=ref["v"], name="Referencia (RK4, Δt = 0,001 s)", line=dict(dash="dot", color="black"), row=1, col=1)
    for nombre, B, col in (("Euler", Be, "#e8822a"), ("RK4", Br, "#1f77b4")):
        fig.add_scatter(x=B["t"], y=B["v"], name=f"{nombre} (Δt = {dt} s)", line=dict(color=col), row=1, col=1)
        fig.add_scatter(x=B["t"], y=np.abs(B["v"] - np.interp(B["t"], ref["t"], ref["v"])),
                        name=f"error {nombre}", line=dict(color=col), showlegend=False, row=2, col=1)
    fig.update_yaxes(type="log", row=2, col=1)
    fig.update_xaxes(title_text="Tiempo (s)", row=2, col=1)
    fig.update_layout(height=600, legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig, width="stretch")

# ---------------- Validación ----------------
with tabs[7]:
    st.markdown("**¿Cómo sabemos que los métodos están bien programados?** Se resuelve un caso que tiene solución exacta: "
                "la cabina parte del reposo y se le pide una velocidad constante. Con la solución exacta se mide el error "
                "de cada método.")
    st.latex(r"v(t)=v_0\,(1-e^{-t/\tau}),\qquad \tau=\frac{m_{ef}}{K_p+b}")
    ayuda("""
- **Tabla:** error máximo de cada método para varios pasos Δt (absoluto en m/s y relativo).
- **Gráfica:** el mismo error en escala logarítmica. La **pendiente** de cada recta es el orden del método:
  Euler baja 2 veces cuando el paso se reduce a la mitad (orden 1) y RK4 baja 16 veces (orden 4).
- El contraste con SciPy solo sirve para comprobar la solución exacta; no se usa en ningún resultado.
- Se calcula con el escenario A.
""")
    p = replace(base, m_pasajeros=float(escenarios["A"]))
    filas = val.errores(p)
    df = pd.DataFrame(filas)
    oe = val.orden_convergencia(filas, "Euler_abs", p.tau)
    orr = val.orden_convergencia(filas, "RK4_abs", p.tau)
    c1, c2 = st.columns(2)
    dato(c1, "Orden observado de Euler", f"{oe:.2f}", "Teórico: 1")
    dato(c2, "Orden observado de RK4", f"{orr:.2f}", "Teórico: 4")
    fig = go.Figure()
    fig.add_scatter(x=df["dt"], y=df["Euler_abs"], name="Euler", mode="lines+markers", line=dict(color="#e8822a"))
    fig.add_scatter(x=df["dt"], y=df["RK4_abs"], name="RK4", mode="lines+markers", line=dict(color="#1f77b4"))
    fig.add_vline(x=2 * p.tau, line=dict(dash="dot", color="gray"), annotation_text="límite de estabilidad de Euler (2τ)")
    fig.update_xaxes(type="log", title="Paso de integración Δt (s)", range=[np.log10(0.0007), np.log10(max(0.3, 2.6 * p.tau))])
    fig.update_yaxes(type="log", title="Error máximo en la velocidad (m/s)")
    fig.update_layout(height=440)
    st.plotly_chart(fig, width="stretch")
    tabla_v = df.rename(columns={"dt": "Δt (s)", "dt/tau": "Δt/τ", "Euler_abs": "Euler, error abs. (m/s)",
                                 "Euler_rel": "Euler, error rel.", "RK4_abs": "RK4, error abs. (m/s)",
                                 "RK4_rel": "RK4, error rel."})
    st.dataframe(tabla_v.style.format("{:.3e}"), hide_index=True)
    e = val.contraste_scipy(p)
    if e is not None:
        st.caption(f"Contraste independiente con solve_ivp de SciPy: diferencia máxima con la solución exacta = {e:.1e} m/s.")
