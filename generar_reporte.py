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

DOMINIO = os.environ.get("FRESHSERVICE_DOMAIN", "")
API_KEY = os.environ.get("FRESHSERVICE_API_KEY", "")
DIAS_PARA_VENCIDO = 7
ARCHIVO_HISTORIAL = "historial_semanal.json"
MAX_PUNTOS_HISTORIAL = 90

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


def dias_desde(fecha_iso):
    if not fecha_iso:
        return 0
    fecha = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
    ahora = datetime.now(timezone.utc)
    return (ahora - fecha).days


def bucket_antiguedad(dias):
    if dias <= 3:
        return "0-3 días"
    elif dias <= 7:
        return "4-7 días"
    elif dias <= 14:
        return "8-14 días"
    else:
        return "15+ días"


def procesar_tickets(tickets, agentes, grupos):
    filas = []
    for t in tickets:
        dias_vencido = dias_desde(t.get("due_by")) if t.get("due_by") else 0
        dias_abierto = dias_desde(t.get("created_at"))
        prioridad = PRIORIDADES.get(t.get("priority"), "N/A")
        vencido = dias_vencido >= DIAS_PARA_VENCIDO
        filas.append({
            "id": t["id"],
            "asunto": t.get("subject", "(sin asunto)"),
            "estado": ESTADOS.get(t.get("status"), "Desconocido"),
            "prioridad": prioridad,
            "grupo": grupos.get(t.get("group_id"), "Sin grupo"),
            "agente": agentes.get(t.get("responder_id"), "Sin asignar"),
            "dias_vencido": max(dias_vencido, 0),
            "vencido": vencido,
            "dias_abierto": dias_abierto,
            "antiguedad": bucket_antiguedad(dias_abierto),
            "critico": vencido and prioridad == "Urgente",
        })
    return filas


def actualizar_historial(total, vencidos):
    historial = []
    if os.path.exists(ARCHIVO_HISTORIAL):
        try:
            with open(ARCHIVO_HISTORIAL, "r", encoding="utf-8") as f:
                historial = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            historial = []

    hoy = datetime.now().strftime("%Y-%m-%d")
    # Si ya hay un registro de hoy, lo reemplaza (por si corre más de una vez al día)
    historial = [h for h in historial if h["fecha"] != hoy]
    historial.append({"fecha": hoy, "total": total, "vencidos": vencidos})
    historial = historial[-MAX_PUNTOS_HISTORIAL:]

    with open(ARCHIVO_HISTORIAL, "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=2)

    return historial


def generar_resumen_ejecutivo(historial, total, vencidos):
    if len(historial) < 2:
        return f"Primer reporte generado. Hay {total} tickets abiertos, de los cuales {vencidos} están vencidos."

    anterior = historial[-2]
    dif_total = total - anterior["total"]
    dif_vencidos = vencidos - anterior["vencidos"]

    def texto_diferencia(dif, singular):
        if dif > 0:
            return f"subieron {dif} {singular}"
        elif dif < 0:
            return f"bajaron {abs(dif)} {singular}"
        else:
            return f"se mantuvieron igual en {singular}"

    frase_total = texto_diferencia(dif_total, "tickets abiertos")
    frase_vencidos = texto_diferencia(dif_vencidos, "tickets vencidos")

    return (f"Hoy hay {total} tickets abiertos ({vencidos} vencidos). "
            f"Frente a la actualización del {anterior['fecha']}, {frase_total} y {frase_vencidos}.")


def generar_html(filas, historial, resumen):
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    tickets_json = json.dumps(filas, ensure_ascii=False)
    historial_json = json.dumps(historial, ensure_ascii=False)

    total = len(filas)
    vencidos = sum(1 for f in filas if f["vencido"])

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reporte Mesa de Servicios - Constructora Capital Medellín</title>
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

    .resumen {{
        background: white; border-left: 5px solid var(--teal); border-radius: 12px;
        padding: 16px 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        font-size: 14px; line-height: 1.5;
    }}
    .resumen strong {{ color: var(--teal-oscuro); }}

    .filtros {{
        background: white; border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06); display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-end;
        position: sticky; top: 12px; z-index: 10;
    }}
    .filtros label {{ font-size: 12px; font-weight: 700; color: var(--teal-oscuro); display: block; margin-bottom: 4px; }}
    .filtros select, .filtros input {{ padding: 8px 12px; border-radius: 6px; border: 1px solid #ddd; font-size: 13px; }}
    .filtros select {{ min-width: 160px; }}
    .filtros input {{ min-width: 200px; }}
    .filtros button {{ background: var(--carbon); color: white; border: none; padding: 9px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
    .filtros button:hover {{ opacity: 0.85; }}
    .filtros button.exportar {{ background: var(--verde); }}
    .filtros .contador {{ margin-left: auto; font-size: 13px; color: #666; }}

    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 16px; }}
    .kpi-card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 5px solid var(--teal); }}
    .kpi-card.alerta {{ border-left-color: var(--rojo); }}
    .kpi-card .valor {{ font-size: 32px; font-weight: 700; }}
    .kpi-card .etiqueta {{ font-size: 13px; color: #666; margin-top: 4px; }}

    .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 16px; }}
    .chart-box {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    .chart-box.ancho {{ grid-column: 1 / -1; }}
    .chart-box h3 {{ font-size: 15px; margin-bottom: 4px; color: var(--teal-oscuro); }}
    .chart-box .ayuda {{ font-size: 11px; color: #999; margin-bottom: 10px; }}

    .ranking-box {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 16px; }}
    .ranking-box h3 {{ font-size: 15px; margin-bottom: 12px; color: var(--teal-oscuro); }}

    .tabla-box {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{ background: var(--carbon); color: white; text-align: left; padding: 10px 12px; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
    tr.fila-vencida td:last-child {{ color: var(--rojo); font-weight: 700; }}
    tr.fila-vencida {{ background: #FDEDEC; }}
    tr.fila-critica {{ background: #F5C6CB !important; }}
    tr.fila-critica td {{ font-weight: 700; }}
    .badge-critico {{ background: var(--rojo); color: white; font-size: 10px; padding: 2px 8px; border-radius: 10px; margin-left: 6px; }}
    footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 24px; }}

    @media print {{
        .filtros button, .filtros select, .filtros input {{ display: none; }}
        .filtros {{ position: static; }}
    }}
</style>
</head>
<body>

<header>
    <img src="logo.png" alt="Constructora Capital" onerror="this.style.display='none'">
    <div class="titulos">
        <h1>Reporte Mesa de Servicios</h1>
        <p>Constructora Capital Medellín · Actualizado automáticamente · Última actualización: {ahora}</p>
    </div>
</header>

<div class="resumen">📋 <strong>Resumen ejecutivo:</strong> {resumen}</div>

<div class="filtros">
    <div><label>Categoría</label><select id="filtroGrupo"><option value="">Todas</option></select></div>
    <div><label>Técnico</label><select id="filtroAgente"><option value="">Todos</option></select></div>
    <div><label>Prioridad</label><select id="filtroPrioridad"><option value="">Todas</option></select></div>
    <div><label>Buscar</label><input type="text" id="buscador" placeholder="Asunto o ID..."></div>
    <button id="btnLimpiar">Quitar filtros</button>
    <button id="btnExportar" class="exportar">Exportar CSV</button>
    <button id="btnImprimir">Imprimir / PDF</button>
    <div class="contador" id="contador"></div>
</div>

<div class="kpis">
    <div class="kpi-card"><div class="valor" id="kpiTotal">0</div><div class="etiqueta">Tickets abiertos / pendientes</div></div>
    <div class="kpi-card alerta"><div class="valor" id="kpiVencidos">0</div><div class="etiqueta">Tickets vencidos (7+ días)</div></div>
    <div class="kpi-card"><div class="valor" id="kpiPorcentaje">0%</div><div class="etiqueta">Porcentaje de vencidos</div></div>
    <div class="kpi-card alerta"><div class="valor" id="kpiCriticos">0</div><div class="etiqueta">Críticos (Urgente + Vencido)</div></div>
</div>

<div class="charts">
  
    <div class="chart-box"><h3>Tickets por categoría</h3><div class="ayuda">Clic para filtrar</div><canvas id="chartGrupo"></canvas></div>
    <div class="chart-box"><h3>Tickets por técnico</h3><div class="ayuda">Clic para filtrar</div><canvas id="chartAgente"></canvas></div>
    <div class="chart-box"><h3>Antigüedad del backlog</h3><div class="ayuda">Clic para filtrar</div><canvas id="chartAntiguedad"></canvas></div>
    <div class="chart-box"><h3>Tickets por prioridad</h3><div class="ayuda">Clic para filtrar</div><canvas id="chartPrioridad"></canvas></div>
</div>

<div class="tabla-box">
    <h3 style="margin-bottom:12px; color:var(--teal-oscuro);" id="tituloTabla">Detalle de tickets</h3>
    <table id="tablaTickets">
        <thead><tr><th>ID</th><th>Asunto</th><th>Estado</th><th>Prioridad</th><th>Categoría</th><th>Técnico</th><th>Días vencido</th></tr></thead>
        <tbody id="cuerpoTabla"></tbody>
    </table>
</div>

<footer>Generado automáticamente vía GitHub Actions · Constructora Capital Medellín</footer>

<script>
const TODOS_LOS_TICKETS = {tickets_json};
const HISTORIAL = {historial_json};
const colorTeal = '{COLOR_TEAL}', colorNaranja = '{COLOR_NARANJA}', colorRojo = '{COLOR_ROJO}', colorVerde = '{COLOR_VERDE}';

const estado = {{ grupo: null, agente: null, prioridad: null, antiguedad: null, texto: '' }};
let chartGrupo, chartAgente, chartPrioridad, chartAntiguedad;

function poblarSelect(id, valores) {{
    const select = document.getElementById(id);
    valores.forEach(v => {{ const opt = document.createElement('option'); opt.value = v; opt.textContent = v; select.appendChild(opt); }});
}}
function contar(lista, campo) {{
    const conteo = {{}};
    lista.forEach(t => {{ conteo[t[campo]] = (conteo[t[campo]] || 0) + 1; }});
    return conteo;
}}
function ticketsFiltrados() {{
    const texto = estado.texto.toLowerCase();
    return TODOS_LOS_TICKETS.filter(t =>
        (!estado.grupo || t.grupo === estado.grupo) &&
        (!estado.agente || t.agente === estado.agente) &&
        (!estado.prioridad || t.prioridad === estado.prioridad) &&
        (!estado.antiguedad || t.antiguedad === estado.antiguedad) &&
        (!texto || t.asunto.toLowerCase().includes(texto) || String(t.id).includes(texto))
    );
}}
function renderTabla(lista) {{
    const cuerpo = document.getElementById('cuerpoTabla');
    cuerpo.innerHTML = '';
    [...lista].sort((a, b) => b.dias_vencido - a.dias_vencido).forEach(t => {{
        const tr = document.createElement('tr');
        if (t.critico) tr.classList.add('fila-critica');
        else if (t.vencido) tr.classList.add('fila-vencida');
        const badge = t.critico ? '<span class="badge-critico">CRÍTICO</span>' : '';
        tr.innerHTML = `<td>${{t.id}}</td><td>${{t.asunto}}${{badge}}</td><td>${{t.estado}}</td><td>${{t.prioridad}}</td><td>${{t.grupo}}</td><td>${{t.agente}}</td><td>${{t.dias_vencido}}</td>`;
        cuerpo.appendChild(tr);
    }});
}}
function renderKPIs(lista) {{
    const total = lista.length;
    const vencidos = lista.filter(t => t.vencido).length;
    const criticos = lista.filter(t => t.critico).length;
    document.getElementById('kpiTotal').innerText = total;
    document.getElementById('kpiVencidos').innerText = vencidos;
    document.getElementById('kpiPorcentaje').innerText = (total ? (vencidos/total*100).toFixed(1) : 0) + '%';
    document.getElementById('kpiCriticos').innerText = criticos;
}}
function actualizarContador() {
    const partes = [];
    if (estado.grupo) partes.push('Categoría: ' + estado.grupo);
    if (estado.agente) partes.push('Técnico: ' + estado.agente);
    if (estado.prioridad) partes.push('Prioridad: ' + estado.prioridad);
    if (estado.antiguedad) partes.push('Antigüedad: ' + estado.antiguedad);
    const total = ticketsFiltrados().length;
    document.getElementById('contador').innerHTML = (partes.length ? partes.join(' · ') + ' — ' : '') + `Mostrando ${total} de ${TODOS_LOS_TICKETS.length} tickets`;

    const tituloTabla = document.getElementById('tituloTabla');
    tituloTabla.innerText = partes.length ? `Detalle de tickets — ${partes.join(' · ')}` : 'Detalle de tickets (todos)';
}
function crearChart(ref, canvasId, tipo, labels, data, colores, campoFiltro) {{
    if (ref) ref.destroy();
    return new Chart(document.getElementById(canvasId), {{
        type: tipo,
        data: {{ labels, datasets: [{{ data, backgroundColor: colores, label: 'Tickets' }}] }},
        options: {{
            responsive: true,
            plugins: {{ legend: {{ display: tipo === 'doughnut' }} }},
            onClick: (evt, els) => {{
                if (!els.length) return;
                const valor = labels[els[0].index];
                estado[campoFiltro] = (estado[campoFiltro] === valor) ? null : valor;
                sincronizarSelects(); render();
            }}
        }}
    }});
}}
function sincronizarSelects() {{
    document.getElementById('filtroGrupo').value = estado.grupo || '';
    document.getElementById('filtroAgente').value = estado.agente || '';
    document.getElementById('filtroPrioridad').value = estado.prioridad || '';
}}
function render() {{
    const filtrados = ticketsFiltrados();
    renderKPIs(filtrados); renderTabla(filtrados); actualizarContador();
    const pg = contar(filtrados, 'grupo');
    chartGrupo = crearChart(chartGrupo, 'chartGrupo', 'bar', Object.keys(pg), Object.values(pg), colorTeal, 'grupo');
    const pa = contar(filtrados, 'agente');
    chartAgente = crearChart(chartAgente, 'chartAgente', 'bar', Object.keys(pa), Object.values(pa), colorNaranja, 'agente');
    const pp = contar(filtrados, 'prioridad');
    chartPrioridad = crearChart(chartPrioridad, 'chartPrioridad', 'doughnut', Object.keys(pp), Object.values(pp), [colorVerde, colorTeal, colorNaranja, colorRojo], 'prioridad');
    const ordenAntig = ['0-3 días', '4-7 días', '8-14 días', '15+ días'];
    const pAnt = contar(filtrados, 'antiguedad');
    const labelsAnt = ordenAntig.filter(l => pAnt[l]);
    chartAntiguedad = crearChart(chartAntiguedad, 'chartAntiguedad', 'bar', labelsAnt, labelsAnt.map(l => pAnt[l]), colorNaranja, 'antiguedad');
}}


poblarSelect('filtroGrupo', [...new Set(TODOS_LOS_TICKETS.map(t => t.grupo))].sort());
poblarSelect('filtroAgente', [...new Set(TODOS_LOS_TICKETS.map(t => t.agente))].sort());
poblarSelect('filtroPrioridad', [...new Set(TODOS_LOS_TICKETS.map(t => t.prioridad))].sort());

document.getElementById('filtroGrupo').addEventListener('change', e => {{ estado.grupo = e.target.value || null; render(); }});
document.getElementById('filtroAgente').addEventListener('change', e => {{ estado.agente = e.target.value || null; render(); }});
document.getElementById('filtroPrioridad').addEventListener('change', e => {{ estado.prioridad = e.target.value || null; render(); }});
document.getElementById('buscador').addEventListener('input', e => {{ estado.texto = e.target.value; render(); }});
document.getElementById('btnLimpiar').addEventListener('click', () => {{
    estado.grupo = null; estado.agente = null; estado.prioridad = null; estado.antiguedad = null; estado.texto = '';
    document.getElementById('buscador').value = '';
    sincronizarSelects(); render();
}});
document.getElementById('btnImprimir').addEventListener('click', () => window.print());
document.getElementById('btnExportar').addEventListener('click', () => {{
    const lista = ticketsFiltrados();
    let csv = 'ID,Asunto,Estado,Prioridad,Categoria,Tecnico,Dias Vencido\\n';
    lista.forEach(t => {{
        csv += `${{t.id}},"${{t.asunto.replace(/"/g,'""')}}",${{t.estado}},${{t.prioridad}},${{t.grupo}},${{t.agente}},${{t.dias_vencido}}\\n`;
    }});
    const blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'tickets_' + new Date().toISOString().slice(0,10) + '.csv';
    link.click();
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

    total = len(filas)
    vencidos = sum(1 for f in filas if f["vencido"])
    historial = actualizar_historial(total, vencidos)
    resumen = generar_resumen_ejecutivo(historial, total, vencidos)

    html = generar_html(filas, historial, resumen)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("index.html generado correctamente.")
    print(resumen)


if __name__ == "__main__":
    main()
