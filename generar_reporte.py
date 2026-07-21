"""
Reporte automático de Mesa de Ayuda TI - Freshdesk
Constructora Capital Medellín
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from collections import Counter
import requests

# ============ CONFIGURACIÓN ============
DOMINIO = os.environ.get("FRESHSERVICE_DOMAIN", "")
API_KEY = os.environ.get("FRESHSERVICE_API_KEY", "")
DIAS_PARA_VENCIDO = 7

COLOR_TEAL = "#0092B7"
COLOR_TEAL_OSCURO = "#00839C"
COLOR_CARBON = "#1D1D1B"
COLOR_ROJO = "#C0392B"
COLOR_VERDE = "#27AE60"
COLOR_NARANJA = "#E67E22"

ESTADOS = {2: "Abierto", 3: "Pendiente", 4: "Resuelto", 5: "Cerrado"}
PRIORIDADES = {1: "Baja", 2: "Media", 3: "Alta", 4: "Urgente"}


def validar_credenciales():
    if not DOMINIO or not API_KEY:
        print("ERROR: Faltan FRESHSERVICE_DOMAIN o FRESHSERVICE_API_KEY.")
        sys.exit(1)


import time  # agrega este import junto a los otros, arriba del archivo

def obtener_paginado(endpoint, campo_lista):
    resultados = []
    page = 1
    while True:
        url = f"https://{DOMINIO}.freshdesk.com/api/v2/{endpoint}"
        separador = "&" if "?" in url else "?"
        url_final = f"{url}{separador}per_page=100&page={page}"

        intentos = 0
        while True:
            resp = requests.get(url_final, auth=(API_KEY, "X"), timeout=30)
            if resp.status_code == 429:
                # Freshdesk nos dice cuántos segundos esperar
                espera = int(resp.headers.get("Retry-After", 10))
                print(f"Límite de peticiones alcanzado, esperando {espera}s...")
                time.sleep(espera + 1)
                intentos += 1
                if intentos > 5:
                    print("Demasiados reintentos por límite de peticiones.")
                    sys.exit(1)
                continue
            break

        if resp.status_code != 200:
            print(f"Error consultando {endpoint}: {resp.status_code} {resp.text}")
            sys.exit(1)

        data = resp.json()
        lote = data if isinstance(data, list) else data.get(campo_lista, [])
        resultados.extend(lote)
        if len(lote) < 100:
            break
        page += 1
        time.sleep(1)  # pequeña pausa entre páginas para no saturar la API
        if page > 50:
            break
    return resultados


def obtener_tickets():
    # Sin filtro -> trae TODOS los tickets (cualquier agente, cualquier grupo).
    # updated_since muy antiguo para traer el historial completo, no solo 30 días.
    tickets = obtener_paginado(
        "tickets?updated_since=2015-01-01T00:00:00Z&order_by=created_at&order_type=desc",
        "tickets"
    )
    # Nos quedamos solo con Abiertos (2) y Pendientes (3)
    return [t for t in tickets if t.get("status") in (2, 3)]


def obtener_agentes():
    agentes = obtener_paginado("agents", "agents")
    mapa = {}
    for a in agentes:
        contacto = a.get("contact") or {}
        nombre = contacto.get("name") or contacto.get("email") or f"Agente {a.get('id')}"
        mapa[a["id"]] = nombre
    return mapa


def obtener_grupos():
    grupos = obtener_paginado("groups", "groups")
    return {g["id"]: g["name"] for g in grupos}


def dias_vencido(due_by):
    if not due_by:
        return 0
    fecha_limite = datetime.fromisoformat(due_by.replace("Z", "+00:00"))
    ahora = datetime.now(timezone.utc)
    return (ahora - fecha_limite).days


def estado_texto(codigo):
    return ESTADOS.get(codigo, "Desconocido")


def prioridad_texto(p):
    return PRIORIDADES.get(p, "N/A")


def procesar_tickets(tickets, agentes, grupos):
    filas = []
    for t in tickets:
        dias = dias_vencido(t.get("due_by"))
        filas.append({
            "id": t["id"],
            "asunto": t.get("subject", "(sin asunto)"),
            "estado": estado_texto(t.get("status")),
            "prioridad": prioridad_texto(t.get("priority")),
            "grupo": grupos.get(t.get("group_id"), "Sin grupo"),
            "agente": agentes.get(t.get("responder_id"), "Sin asignar"),
            "creado": t.get("created_at"),
            "vence": t.get("due_by"),
            "dias_vencido": max(dias, 0),
            "vencido": dias >= DIAS_PARA_VENCIDO,
        })
    return filas


def calcular_metricas(filas):
    total = len(filas)
    vencidos = sum(1 for f in filas if f["vencido"])
    porcentaje = round((vencidos / total * 100), 1) if total else 0
    por_grupo = Counter(f["grupo"] for f in filas)
    por_agente = Counter(f["agente"] for f in filas)
    por_prioridad = Counter(f["prioridad"] for f in filas)
    return {
        "total": total,
        "vencidos": vencidos,
        "porcentaje_vencidos": porcentaje,
        "por_grupo": dict(por_grupo.most_common()),
        "por_agente": dict(por_agente.most_common()),
        "por_prioridad": dict(por_prioridad.most_common()),
    }


def generar_html(filas, metricas):
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    filas_ordenadas = sorted(filas, key=lambda f: f["dias_vencido"], reverse=True)

    grupos_unicos = sorted(set(f["grupo"] for f in filas))
    agentes_unicos = sorted(set(f["agente"] for f in filas))

    opciones_grupo = "".join(f'<option value="{g}">{g}</option>' for g in grupos_unicos)
    opciones_agente = "".join(f'<option value="{a}">{a}</option>' for a in agentes_unicos)

    filas_tabla = ""
    for f in filas_ordenadas:
        clase = "fila-vencida" if f["vencido"] else ""
        filas_tabla += f"""
        <tr class="{clase}" data-grupo="{f['grupo']}" data-agente="{f['agente']}">
            <td>{f['id']}</td>
            <td>{f['asunto']}</td>
            <td>{f['estado']}</td>
            <td>{f['prioridad']}</td>
            <td>{f['grupo']}</td>
            <td>{f['agente']}</td>
            <td>{f['dias_vencido']}</td>
        </tr>"""

    labels_grupo = json.dumps(list(metricas["por_grupo"].keys()))
    data_grupo = json.dumps(list(metricas["por_grupo"].values()))
    labels_agente = json.dumps(list(metricas["por_agente"].keys()))
    data_agente = json.dumps(list(metricas["por_agente"].values()))
    labels_prioridad = json.dumps(list(metricas["por_prioridad"].keys()))
    data_prioridad = json.dumps(list(metricas["por_prioridad"].values()))

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reporte Mesa de Ayuda TI - Constructora Capital</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
    :root {{
        --teal: {COLOR_TEAL};
        --teal-oscuro: {COLOR_TEAL_OSCURO};
        --carbon: {COLOR_CARBON};
        --rojo: {COLOR_ROJO};
        --verde: {COLOR_VERDE};
        --naranja: {COLOR_NARANJA};
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #F4F6F7; color: var(--carbon); padding: 24px; }}
    header {{
        background: linear-gradient(135deg, var(--teal-oscuro), var(--teal));
        color: white; padding: 24px 32px; border-radius: 12px; margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        display: flex; align-items: center; gap: 20px;
    }}
    header img {{ height: 60px; background: white; border-radius: 8px; padding: 6px; }}
    header .titulos h1 {{ font-size: 22px; margin-bottom: 4px; }}
    header .titulos p {{ opacity: 0.9; font-size: 13px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
    .kpi-card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 5px solid var(--teal); }}
    .kpi-card.alerta {{ border-left-color: var(--rojo); }}
    .kpi-card .valor {{ font-size: 32px; font-weight: 700; }}
    .kpi-card .etiqueta {{ font-size: 13px; color: #666; margin-top: 4px; }}
    .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 24px; }}
    .chart-box {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    .chart-box h3 {{ font-size: 15px; margin-bottom: 12px; color: var(--teal-oscuro); }}
    .filtros {{ background: white; border-radius: 12px; padding: 16px 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); display: flex; gap: 20px; flex-wrap: wrap; align-items: center; }}
    .filtros label {{ font-size: 13px; font-weight: 600; color: var(--teal-oscuro); margin-right: 6px; }}
    .filtros select {{ padding: 8px 12px; border-radius: 6px; border: 1px solid #ddd; font-size: 13px; }}
    .filtros .contador {{ margin-left: auto; font-size: 13px; color: #666; }}
    .tabla-box {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{ background: var(--carbon); color: white; text-align: left; padding: 10px 12px; position: sticky; top: 0; cursor: pointer; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
    .fila-vencida {{ background: #FDEDEC; }}
    .fila-vencida td:last-child {{ color: var(--rojo); font-weight: 700; }}
    .oculto {{ display: none; }}
    footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 24px; }}
</style>
</head>
<body>

<header>
    <img src="logo.png" alt="Constructora Capital" onerror="this.style.display='none'">
    <div class="titulos">
        <h1>Reporte Mesa de Ayuda TI</h1>
        <p>Constructora Capital Medellín · Actualizado automáticamente · Última actualización: {ahora}</p>
    </div>
</header>

<div class="kpis">
    <div class="kpi-card">
        <div class="valor">{metricas['total']}</div>
        <div class="etiqueta">Tickets abiertos / pendientes</div>
    </div>
    <div class="kpi-card alerta">
        <div class="valor">{metricas['vencidos']}</div>
        <div class="etiqueta">Tickets vencidos (7+ días)</div>
    </div>
    <div class="kpi-card">
        <div class="valor">{metricas['porcentaje_vencidos']}%</div>
        <div class="etiqueta">Porcentaje de vencidos</div>
    </div>
</div>

<div class="charts">
    <div class="chart-box"><h3>Tickets por categoría</h3><canvas id="chartGrupo"></canvas></div>
    <div class="chart-box"><h3>Tickets por técnico</h3><canvas id="chartAgente"></canvas></div>
    <div class="chart-box"><h3>Tickets por prioridad</h3><canvas id="chartPrioridad"></canvas></div>
</div>

<div class="filtros">
    <div>
        <label>Categoría</label>
        <select id="filtroGrupo">
            <option value="">Todas</option>
            {opciones_grupo}
        </select>
    </div>
    <div>
        <label>Técnico</label>
        <select id="filtroAgente">
            <option value="">Todos</option>
            {opciones_agente}
        </select>
    </div>
    <div class="contador" id="contador"></div>
</div>

<div class="tabla-box">
    <h3 style="margin-bottom:12px; color:var(--teal-oscuro);">Detalle de tickets</h3>
    <table id="tablaTickets">
        <thead>
            <tr><th>ID</th><th>Asunto</th><th>Estado</th><th>Prioridad</th><th>Categoría</th><th>Técnico</th><th>Días vencido</th></tr>
        </thead>
        <tbody>
            {filas_tabla}
        </tbody>
    </table>
</div>

<footer>Generado automáticamente vía GitHub Actions · Constructora Capital Medellín</footer>

<script>
const colorTeal = '{COLOR_TEAL}';
const colorNaranja = '{COLOR_NARANJA}';
const colorRojo = '{COLOR_ROJO}';
const colorVerde = '{COLOR_VERDE}';

new Chart(document.getElementById('chartGrupo'), {{
    type: 'bar',
    data: {{ labels: {labels_grupo}, datasets: [{{ label: 'Tickets', data: {data_grupo}, backgroundColor: colorTeal }}] }},
    options: {{ plugins: {{ legend: {{ display: false }} }}, responsive: true }}
}});
new Chart(document.getElementById('chartAgente'), {{
    type: 'bar',
    data: {{ labels: {labels_agente}, datasets: [{{ label: 'Tickets', data: {data_agente}, backgroundColor: colorNaranja }}] }},
    options: {{ plugins: {{ legend: {{ display: false }} }}, responsive: true }}
}});
new Chart(document.getElementById('chartPrioridad'), {{
    type: 'doughnut',
    data: {{ labels: {labels_prioridad}, datasets: [{{ data: {data_prioridad}, backgroundColor: [colorVerde, colorTeal, colorNaranja, colorRojo] }}] }},
    options: {{ responsive: true }}
}});

function aplicarFiltros() {{
    const grupo = document.getElementById('filtroGrupo').value;
    const agente = document.getElementById('filtroAgente').value;
    const filas = document.querySelectorAll('#tablaTickets tbody tr');
    let visibles = 0;
    filas.forEach(fila => {{
        const coincideGrupo = !grupo || fila.dataset.grupo === grupo;
        const coincideAgente = !agente || fila.dataset.agente === agente;
        if (coincideGrupo && coincideAgente) {{
            fila.classList.remove('oculto');
            visibles++;
        }} else {{
            fila.classList.add('oculto');
        }}
    }});
    document.getElementById('contador').innerText = `Mostrando ${{visibles}} de ${{filas.length}} tickets`;
}}

document.getElementById('filtroGrupo').addEventListener('change', aplicarFiltros);
document.getElementById('filtroAgente').addEventListener('change', aplicarFiltros);
aplicarFiltros();
</script>

</body>
</html>"""
    return html


def main():
    validar_credenciales()
    print("Conectando a Freshdesk...")
    tickets = obtener_tickets()
    agentes = obtener_agentes()
    grupos = obtener_grupos()
    print(f"Tickets encontrados: {len(tickets)}")
    filas = procesar_tickets(tickets, agentes, grupos)
    metricas = calcular_metricas(filas)
    html = generar_html(filas, metricas)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html generado correctamente.")
    print(f"Total: {metricas['total']} | Vencidos: {metricas['vencidos']}")


if __name__ == "__main__":
    main()
