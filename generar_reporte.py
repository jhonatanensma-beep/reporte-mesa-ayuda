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
        time.sleep(1)
        if page > 50:
            break
    return resultados


def obtener_tickets():
    tickets = obtener_paginado(
        "tickets?updated_since=2015-01-01T00:00:00Z&order_by=created_at&order_type=desc",
        "tickets"
    )
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
            "dias_vencido": max(dias, 0),
            "vencido": dias >= DIAS_PARA_VENCIDO,
        })
    return filas


def generar_html(filas):
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    tickets_json = json.dumps(filas, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reporte Mesa de Ayuda TI - Constructora Capital</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
    :root {{
        --teal: {COLOR_TEAL}; --teal-oscuro: {COLOR_TEAL_OSCURO}; --carbon: {COLOR_CARBON};
        --rojo: {COLOR_ROJO}; --verde: {COLOR_VERDE}; --naranja: {COLOR_NARANJA};
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #F4F6F7; color: var(--carbon); padding: 24px; }}
    header {{
        background: linear-gradient(135deg, var(--teal-oscuro), var(--teal));
        color: white; padding: 24px 32px; border-radius: 12px; margin-bottom: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1); display: flex; align-items: center; gap: 20px;
    }}
    header img {{ height: 60px; background: white; border-radius: 8px; padding: 6px; }}
    header .titulos h1 {{ font-size: 22px; margin-bottom: 4px; }}
    header .titulos p {{ opacity: 0.9; font-size: 13px; }}

    .filtros {{
        background: white; border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06); display: flex; gap: 20px; flex-wrap: wrap; align-items: center;
        position: sticky; top: 12px; z-index: 10;
    }}
    .filtros label {{ font-size: 12px; font-weight: 700; color: var(--teal-oscuro); display: block; margin-bottom: 4px; }}
    .filtros select {{ padding: 8px 12px; border-radius: 6px; border: 1px solid #ddd; font-size: 13px; min-width: 180px; }}
    .filtros button {{
        background: var(--carbon); color: white; border: none; padding: 9px 16px;
        border-radius: 6px; cursor: pointer; font-size: 13px; align-self: flex-end;
    }}
    .filtros button:hover {{ opacity: 0.85; }}
    .filtros .contador {{ margin-left: auto; font-size: 13px; color: #666; align-self: flex-end; }}
    .filtro-activo {{ font-size: 12px; background: #E8F6F9; color: var(--teal-oscuro); padding: 4px 10px; border-radius: 20px; margin-top: 2px; display: inline-block; }}

    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 16px; }}
    .kpi-card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 5px solid var(--teal); transition: all 0.2s; }}
    .kpi-card.alerta {{ border-left-color: var(--rojo); }}
    .kpi-card .valor {{ font-size: 32px; font-weight: 700; }}
    .kpi-card .etiqueta {{ font-size: 13px; color: #666; margin-top: 4px; }}

    .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 16px; }}
    .chart-box {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    .chart-box h3 {{ font-size: 15px; margin-bottom: 4px; color: var(--teal-oscuro); }}
    .chart-box .ayuda {{ font-size: 11px; color: #999; margin-bottom: 10px; }}
    .chart-box canvas {{ cursor: pointer; }}

    .tabla-box {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{ background: var(--carbon); color: white; text-align: left; padding: 10px 12px; position: sticky; top: 0; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
    tr.fila-vencida td:last-child {{ color: var(--rojo); font-weight: 700; }}
    tr.fila-vencida {{ background: #FDEDEC; }}
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

<div class="filtros">
    <div>
        <label>Categoría</label>
        <select id="filtroGrupo"><option value="">Todas</option></select>
    </div>
    <div>
        <label>Técnico</label>
        <select id="filtroAgente"><option value="">Todos</option></select>
    </div>
    <div>
        <label>Prioridad</label>
        <select id="filtroPrioridad"><option value="">Todas</option></select>
    </div>
    <button id="btnLimpiar">Quitar filtros</button>
    <div class="contador" id="contador"></div>
</div>

<div class="kpis">
    <div class="kpi-card">
        <div class="valor" id="kpiTotal">0</div>
        <div class="etiqueta">Tickets abiertos / pendientes</div>
    </div>
    <div class="kpi-card alerta">
        <div class="valor" id="kpiVencidos">0</div>
        <div class="etiqueta">Tickets vencidos (7+ días)</div>
    </div>
    <div class="kpi-card">
        <div class="valor" id="kpiPorcentaje">0%</div>
        <div class="etiqueta">Porcentaje de vencidos</div>
    </div>
</div>

<div class="charts">
    <div class="chart-box">
        <h3>Tickets por categoría</h3>
        <div class="ayuda">Haz clic en una barra para filtrar</div>
        <canvas id="chartGrupo"></canvas>
    </div>
    <div class="chart-box">
        <h3>Tickets por técnico</h3>
        <div class="ayuda">Haz clic en una barra para filtrar</div>
        <canvas id="chartAgente"></canvas>
    </div>
    <div class="chart-box">
        <h3>Tickets por prioridad</h3>
        <div class="ayuda">Haz clic en una porción para filtrar</div>
        <canvas id="chartPrioridad"></canvas>
    </div>
</div>

<div class="tabla-box">
    <h3 style="margin-bottom:12px; color:var(--teal-oscuro);">Detalle de tickets</h3>
    <table id="tablaTickets">
        <thead>
            <tr><th>ID</th><th>Asunto</th><th>Estado</th><th>Prioridad</th><th>Categoría</th><th>Técnico</th><th>Días vencido</th></tr>
        </thead>
        <tbody id="cuerpoTabla"></tbody>
    </table>
</div>

<footer>Generado automáticamente vía GitHub Actions · Constructora Capital Medellín</footer>

<script>
const TODOS_LOS_TICKETS = {tickets_json};
const colorTeal = '{COLOR_TEAL}';
const colorNaranja = '{COLOR_NARANJA}';
const colorRojo = '{COLOR_ROJO}';
const colorVerde = '{COLOR_VERDE}';

const estado = {{ grupo: null, agente: null, prioridad: null }};
let chartGrupo, chartAgente, chartPrioridad;

function poblarSelect(id, valores) {{
    const select = document.getElementById(id);
    valores.forEach(v => {{
        const opt = document.createElement('option');
        opt.value = v; opt.textContent = v;
        select.appendChild(opt);
    }});
}}

function contar(lista, campo) {{
    const conteo = {{}};
    lista.forEach(t => {{ conteo[t[campo]] = (conteo[t[campo]] || 0) + 1; }});
    return conteo;
}}

function ticketsFiltrados() {{
    return TODOS_LOS_TICKETS.filter(t =>
        (!estado.grupo || t.grupo === estado.grupo) &&
        (!estado.agente || t.agente === estado.agente) &&
        (!estado.prioridad || t.prioridad === estado.prioridad)
    );
}}

function renderTabla(lista) {{
    const cuerpo = document.getElementById('cuerpoTabla');
    cuerpo.innerHTML = '';
    const ordenados = [...lista].sort((a, b) => b.dias_vencido - a.dias_vencido);
    ordenados.forEach(t => {{
        const tr = document.createElement('tr');
        if (t.vencido) tr.classList.add('fila-vencida');
        tr.innerHTML = `<td>${{t.id}}</td><td>${{t.asunto}}</td><td>${{t.estado}}</td><td>${{t.prioridad}}</td><td>${{t.grupo}}</td><td>${{t.agente}}</td><td>${{t.dias_vencido}}</td>`;
        cuerpo.appendChild(tr);
    }});
}}

function renderKPIs(lista) {{
    const total = lista.length;
    const vencidos = lista.filter(t => t.vencido).length;
    const pct = total ? ((vencidos / total) * 100).toFixed(1) : 0;
    document.getElementById('kpiTotal').innerText = total;
    document.getElementById('kpiVencidos').innerText = vencidos;
    document.getElementById('kpiPorcentaje').innerText = pct + '%';
}}

function actualizarEtiquetasFiltro() {{
    const partes = [];
    if (estado.grupo) partes.push('Categoría: ' + estado.grupo);
    if (estado.agente) partes.push('Técnico: ' + estado.agente);
    if (estado.prioridad) partes.push('Prioridad: ' + estado.prioridad);
    const contador = document.getElementById('contador');
    const total = ticketsFiltrados().length;
    contador.innerHTML = (partes.length ? partes.join(' · ') + ' — ' : '') + `Mostrando ${{total}} de ${{TODOS_LOS_TICKETS.length}} tickets`;
}}

function crearOActualizarChart(chartRef, canvasId, tipo, labels, data, colores, campoFiltro) {{
    if (chartRef) chartRef.destroy();
    const ctx = document.getElementById(canvasId);
    const nuevo = new Chart(ctx, {{
        type: tipo,
        data: {{ labels: labels, datasets: [{{ data: data, backgroundColor: colores, label: 'Tickets' }}] }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ display: tipo === 'doughnut' }} }},
            onClick: (evt, elementos) => {{
                if (!elementos.length) return;
                const idx = elementos[0].index;
                const valor = labels[idx];
                if (estado[campoFiltro] === valor) {{
                    estado[campoFiltro] = null;
                }} else {{
                    estado[campoFiltro] = valor;
                }}
                sincronizarSelects();
                render();
            }}
        }}
    }});
    return nuevo;
}}

function sincronizarSelects() {{
    document.getElementById('filtroGrupo').value = estado.grupo || '';
    document.getElementById('filtroAgente').value = estado.agente || '';
    document.getElementById('filtroPrioridad').value = estado.prioridad || '';
}}

function render() {{
    const filtrados = ticketsFiltrados();
    renderKPIs(filtrados);
    renderTabla(filtrados);
    actualizarEtiquetasFiltro();

    const porGrupo = contar(filtrados, 'grupo');
    chartGrupo = crearOActualizarChart(chartGrupo, 'chartGrupo', 'bar',
        Object.keys(porGrupo), Object.values(porGrupo), colorTeal, 'grupo');

    const porAgente = contar(filtrados, 'agente');
    chartAgente = crearOActualizarChart(chartAgente, 'chartAgente', 'bar',
        Object.keys(porAgente), Object.values(porAgente), colorNaranja, 'agente');

    const porPrioridad = contar(filtrados, 'prioridad');
    chartPrioridad = crearOActualizarChart(chartPrioridad, 'chartPrioridad', 'doughnut',
        Object.keys(porPrioridad), Object.values(porPrioridad),
        [colorVerde, colorTeal, colorNaranja, colorRojo], 'prioridad');
}}

// Poblar selects con valores únicos (sobre el total, no sobre el filtrado)
poblarSelect('filtroGrupo', [...new Set(TODOS_LOS_TICKETS.map(t => t.grupo))].sort());
poblarSelect('filtroAgente', [...new Set(TODOS_LOS_TICKETS.map(t => t.agente))].sort());
poblarSelect('filtroPrioridad', [...new Set(TODOS_LOS_TICKETS.map(t => t.prioridad))].sort());

document.getElementById('filtroGrupo').addEventListener('change', e => {{ estado.grupo = e.target.value || null; render(); }});
document.getElementById('filtroAgente').addEventListener('change', e => {{ estado.agente = e.target.value || null; render(); }});
document.getElementById('filtroPrioridad').addEventListener('change', e => {{ estado.prioridad = e.target.value || null; render(); }});
document.getElementById('btnLimpiar').addEventListener('click', () => {{
    estado.grupo = null; estado.agente = null; estado.prioridad = null;
    sincronizarSelects(); render();
}});

render();
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
    html = generar_html(filas)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html generado correctamente.")


if __name__ == "__main__":
    main()
