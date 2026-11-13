"""Parámetros del CASO DE ESTUDIO (única fuente de valores para código y documento).

Caso 1: edificio de 20 paradas con contrapeso equilibrado al 50 % vs. 30 % de la carga
nominal (artículo sobre optimización de la eficiencia energética según ISO 25745,
fuente del cuaderno del grupo).

IMPORTANTE: verificar cada valor marcado "FUENTE" contra el documento original antes
de citarlo en el artículo. Los marcados "SUPUESTO" deben declararse como tales.
"""

G = 9.81  # m/s^2

CASO = {
    # --- Datos del edificio y del ascensor (FUENTE: artículo ISO 25745) ---
    "n_paradas": 20,            # paradas (piso 0 a 19)
    "recorrido": 75.0,          # m, recorrido total
    "v_nominal": 2.5,           # m/s
    "a_nominal": 1.0,           # m/s^2
    "jerk": 1.25,               # m/s^3 (NO se modela: perfil trapezoidal -> limitación)
    "m_cabina": 950.0,          # kg (P)
    "carga_nominal": 1000.0,    # kg (Q)
    "cw_50": 1450.0,            # kg, contrapeso al 50 %  = P + 0.5 Q
    "cw_30": 1250.0,            # kg, contrapeso al 30 %  = P + 0.3 Q
    "Ed_50_Wh_dia": 26074.0,    # Wh/día reportados al 50 % (clase B) -> confirmar unidad en la fuente
    "Ed_30_Wh_dia": 18352.0,    # Wh/día reportados al 30 % (clase A)
    "ahorro_kWh_anio": 2819.0,  # kWh/año reportados

    # --- Eficiencias (FUENTE: rango 70-85 % reportado para variador + inversor regenerativo) ---
    "eta_motor": 0.85,
    "eta_regen": 0.85,

    # --- SUPUESTOS del modelo (declarar en el documento) ---
    "m_pasajero": 75.0,         # kg por pasajero
    "I_polea_eq": 200.0,        # kg, inercia equivalente de polea + rotor (I/R^2)
    "b": 50.0,                  # N·s/m, fricción viscosa equivalente
    "Kp": 15000.0,              # N·s/m, ganancia del lazo de velocidad del variador
}

CASO["h_piso"] = CASO["recorrido"] / (CASO["n_paradas"] - 1)  # ≈ 3.95 m
