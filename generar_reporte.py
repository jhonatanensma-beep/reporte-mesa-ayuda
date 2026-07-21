"""
Reporte automático de Mesa de Ayuda TI - Freshservice
Constructora Capital Medellín

Este script se conecta a la API de Freshservice, trae los tickets,
calcula métricas (vencidos, por categoría, por técnico) y genera
un archivo index.html con un dashboard visual.

Se ejecuta automáticamente todos los días vía GitHub Actions.
"""

import os
import sys
import json
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
        print("ERROR: Faltan FRESHSERVICE_DOMAIN o FRESHSERVICE_API_KEY "
              "como variables de entorno / GitHub Secrets.")
        sys.exit(1)


def obtener_paginado(endpoint, campo_lista):
    """Trae todas las páginas de un endpoint de Freshdesk."""
    resultados = []
    page = 1
    while True:
        url = f"https://{DOMINIO}.freshdesk.com/api/v2/{endpoint}"
        params = {"per_page": 100, "page": page}
        resp = requests.get(url, params=params, auth=(API_KEY, "X"), timeout=30)
        if resp.status_code != 200:
            print(f"Error consultando {endpoint}: {resp.status_code} {resp.text}")
            sys.exit(1)
        data = resp.json()
        lote = data.get(campo_lista, [])
        resultados.extend(lote)
        if len(lote) < 100:
            break
        page += 1
        if page > 50:  # freno de seguridad
            break
    return resultados


def obtener_tickets():
    return obtener_paginado("tickets?filter=new_and_my_open", "tickets")


def obtener_agentes():
    agentes = obtener_paginado("agents", "agents")
    return {a["id"]: f"{a['first_name']} {a['last_name']}".strip() for a in agentes}


def obtener_grupos():
    grupos = obtener_paginado("groups", "groups")
    return {g["id"]: g["name"] for g in grupos}


def dias_vencido(due_by):
    if not due_by:
        return 0
    fecha_limite = datetime.fromisoformat(due_by.replace("Z", "+00:00"))
    ahora = datetime.now(timezone.utc)
    return (ahora - fecha_limite).days


def procesar_tickets(tickets, agentes, grupos):
    filas = []
    for t in tickets:
        dias = dias_vencido(t.get("due_by"))
        filas.append({
            "id": t["id"],
            "asunto": t.get("subject", "(sin asunto)"),
            "estado": ESTADOS.get(t.get("status"), "Desconocido"),
            "prioridad": PRIORIDADES.get(t.get("priority"), "N/A"),
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

    filas_tabla = ""
    for f in filas_ordenadas:
        clase = "fila-vencida" if f["vencido"] else ""
        filas_tabla += f"""
        <tr class="{clase}">
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
    body {{
        font-family: 'Segoe UI', Arial, sans-serif;
        background: #F4F6F7;
        color: var(--carbon);
        padding: 24px;
    }}
    header {{
        background: linear-gradient(135deg, var(--teal-oscuro), var(--teal));
        color: white;
        padding: 28px 32px;
        border-radius: 12px;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }}
    header h1 {{ font-size: 24px; margin-bottom: 6px; }}
    header p {{ opacity: 0.9; font-size: 13px; }}
    .kpis {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 24px;
    }}
    .kpi-card {{
        background: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        border-left: 5px solid var(--teal);
    }}
    .kpi-card.alerta {{ border-left-color: var(--rojo); }}
    .kpi-card .valor {{ font-size: 32px; font-weight: 700; color: var(--carbon); }}
    .kpi-card .etiqueta {{ font-size: 13px; color: #666; margin-top: 4px; }}
    .charts {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        gap: 16px;
        margin-bottom: 24px;
    }}
    .chart-box {{
        background: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }}
    .chart-box h3 {{ font-size: 15px; margin-bottom: 12px; color: var(--teal-oscuro); }}
    .tabla-box {{
        background: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        overflow-x: auto;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{
        background: var(--carbon);
        color: white;
        text-align: left;
        padding: 10px 12px;
        position: sticky; top: 0;
    }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
    .fila-vencida {{ background: #FDEDEC; }}
    .fila-vencida td:last-child {{ color: var(--rojo); font-weight: 700; }}
    footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 24px; }}
</style>
</head>
<body>

<header>
    <h1>Reporte Mesa de Ayuda TI — Constructora Capital Medellín</h1>
    <p>Actualizado automáticamente · Última actualización: {ahora}</p>
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
    <div class="chart-box">
        <h3>Tickets por categoría</h3>
        <canvas id="chartGrupo"></canvas>
    </div>
    <div class="chart-box">
        <h3>Tickets por técnico</h3>
        <canvas id="chartAgente"></canvas>
    </div>
    <div class="chart-box">
        <h3>Tickets por prioridad</h3>
        <canvas id="chartPrioridad"></canvas>
    </div>
</div>

<div class="tabla-box">
    <h3 style="margin-bottom:12px; color:var(--teal-oscuro);">Detalle de tickets (ordenados por días vencido)</h3>
    <table>
        <thead>
            <tr>
                <th>ID</th><th>Asunto</th><th>Estado</th><th>Prioridad</th>
                <th>Categoría</th><th>Técnico</th><th>Días vencido</th>
            </tr>
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
const colorCarbon = '{COLOR_CARBON}';

new Chart(document.getElementById('chartGrupo'), {{
    type: 'bar',
    data: {{
        labels: {labels_grupo},
        datasets: [{{ label: 'Tickets', data: {data_grupo}, backgroundColor: colorTeal }}]
    }},
    options: {{ plugins: {{ legend: {{ display: false }} }}, responsive: true }}
}});

new Chart(document.getElementById('chartAgente'), {{
    type: 'bar',
    data: {{
        labels: {labels_agente},
        datasets: [{{ label: 'Tickets', data: {data_agente}, backgroundColor: colorNaranja }}]
    }},
    options: {{ plugins: {{ legend: {{ display: false }} }}, responsive: true }}
}});

new Chart(document.getElementById('chartPrioridad'), {{
    type: 'doughnut',
    data: {{
        labels: {labels_prioridad},
        datasets: [{{ data: {data_prioridad}, backgroundColor: [colorVerde, colorTeal, colorNaranja, colorRojo] }}]
    }},
    options: {{ responsive: true }}
}});
</script>

</body>
</html>"""
    return html


def main():
    validar_credenciales()
    print("Conectando a Freshservice...")
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
