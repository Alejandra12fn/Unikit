# ========================================================
# CONSULTAS.PY — PANEL ADMINISTRATIVO UNIKIT MVP (SEMANA 04)
# ========================================================
import re
import sqlite3
from math import ceil
from html import escape
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse, urlencode
from pathlib import Path

DB = Path(__file__).parent / "unikit.db"
ESTADOS = ("PENDIENTE", "APROBADO", "NO APROBADO", "CANCELADO")
POR_PAGINA = 10

def pesos(valor):
    try:
        return f"${int(valor):,} COP".replace(",", ".")
    except (ValueError, TypeError):
        return "$0 COP"

def conectar():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    return con

def consultar(tipo="todos", consecutivo=None, chat_id=None, desde="", hasta="", estado=""):
    condiciones, parametros = [], []
    if tipo == "pendientes":
        estado = "PENDIENTE"
    
    for campo, operador, valor in (
        ("consecutivo", "=", consecutivo if tipo == "pedido" else None),
        ("chat_id", "=", chat_id),
        ("fecha", ">=", desde or None),
        ("fecha", "<=", hasta or None),
        ("estado", "=", estado or None)
    ):
        if valor is not None:
            condiciones.append(f"{campo} {operador} ?")
            parametros.append(valor)

    sql = "SELECT * FROM pedidos"
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY id DESC"

    con = conectar()
    try:
        return [dict(f) for f in con.execute(sql, parametros)]
    finally:
        con.close()
def cambiar_estado(consecutivo, nuevo, actor, motivo=""):
    if nuevo not in ("APROBADO", "NO APROBADO", "CANCELADO"):
        raise ValueError("Decisión no permitida.")
    
    motivo = motivo.strip()
    if not motivo:
        if nuevo == "APROBADO":
            motivo = "Aprobado por el administrador"
        elif nuevo == "NO APROBADO":
            motivo = "No aprobado por el administrador"
        elif nuevo == "CANCELADO":
            motivo = "Cancelado por el administrador"

    con = conectar()
    try:
        con.execute("BEGIN IMMEDIATE")
        fila = con.execute("SELECT * FROM pedidos WHERE consecutivo=?", (consecutivo,)).fetchone()
        if not fila:
            raise ValueError("Pedido no encontrado.")
        if fila["estado"] != "PENDIENTE":
            raise ValueError(f"El pedido ya está {fila['estado']}. Solo se pueden modificar pedidos PENDIENTES.")

        from datetime import datetime
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            "UPDATE pedidos SET estado=?, motivo=?, actualizado_en=?, actualizado_por=? WHERE id=? AND estado='PENDIENTE'",
            (nuevo, motivo, ahora, actor, fila["id"])
        )
        con.execute(
            "INSERT INTO historial_estados (pedido_id, estado_anterior, estado_nuevo, actor, motivo, fecha_hora) VALUES (?,?,?,?,?,?)",
            (fila["id"], "PENDIENTE", nuevo, actor, motivo, ahora)
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
        
    if nuevo not in ("APROBADO", "NO APROBADO", "CANCELADO"):
        raise ValueError("Decisión no permitida.")
    motivo = motivo.strip()
    if nuevo in ("NO APROBADO", "CANCELADO") and not motivo:
        raise ValueError("Debe indicar el motivo de la decisión.")

    con = conectar()
    try:
        con.execute("BEGIN IMMEDIATE")
        fila = con.execute("SELECT * FROM pedidos WHERE consecutivo=?", (consecutivo,)).fetchone()
        if not fila:
            raise ValueError("Pedido no encontrado.")
        if fila["estado"] != "PENDIENTE":
            raise ValueError(f"El pedido ya está {fila['estado']}. Solo se pueden modificar pedidos PENDIENTES.")

        from datetime import datetime
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            "UPDATE pedidos SET estado=?, motivo=?, actualizado_en=?, actualizado_por=? WHERE id=? AND estado='PENDIENTE'",
            (nuevo, motivo, ahora, actor, fila["id"])
        )
        con.execute(
            "INSERT INTO historial_estados (pedido_id, estado_anterior, estado_nuevo, actor, motivo, fecha_hora) VALUES (?,?,?,?,?,?)",
            (fila["id"], "PENDIENTE", nuevo, actor, motivo, ahora)
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def obtener_historial(pedido_id):
    con = conectar()
    try:
        return [dict(f) for f in con.execute("SELECT * FROM historial_estados WHERE pedido_id=? ORDER BY id DESC", (pedido_id,))]
    finally:
        con.close()

def leer_filtros(params):
    return {
        'desde': params.get('desde', [''])[0].strip(),
        'hasta': params.get('hasta', [''])[0].strip(),
        'estado': params.get('estado', [''])[0].strip(),
        'buscar': params.get('buscar', [''])[0].strip(),
        'vista': params.get('vista', ['pedidos'])[0].strip(),
        'pagina': int(params.get('pagina', ['1'])[0]),
        'detalle': params.get('detalle', [''])[0].strip()
    }

def enlace(filtros, **kwargs):
    f = dict(filtros)
    f.update(kwargs)
    return "/?" + urlencode({k: v for k, v in f.items() if v})

PLANTILLA = '''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UniKit MVP - Panel de Administración</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root { --bg: #0f172a; --surface: #1e293b; --line: #334155; --ink: #f8fafc; --muted: #94a3b8; --indigo: #6366f1; --sky: #38bdf8; --emerald: #10b981; --rose: #f43f5e; }
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:'Poppins',sans-serif;line-height:1.5}
.barra{background:#090d16;border-bottom:1px solid var(--line);padding:16px 5%;display:flex;align-items:center;gap:12px}
.marca{width:40px;height:40px;background:linear-gradient(135deg,var(--indigo),var(--sky));color:#fff;border-radius:10px;display:grid;place-items:center;font-weight:bold;font-size:18px}
main{max-width:1400px;margin:auto;padding:30px 4%}
.resumen{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}
.dato{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px;flex:1;min-width:180px}
.dato span{display:block;font-size:12px;color:var(--muted)} .dato strong{font-size:22px;display:block;margin-top:4px}
.tabs{display:flex;gap:10px;margin-bottom:20px}
.tabs a{padding:10px 20px;border-radius:8px;background:var(--surface);border:1px solid var(--line);color:#fff;text-decoration:none;font-weight:600;font-size:14px}
.tabs a.activo{background:var(--indigo);border-color:var(--indigo)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:20px}
.filtros{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:20px}
label{font-size:12px;color:var(--muted);display:block}
input,select,textarea{background:#0f172a;border:1px solid var(--line);border-radius:8px;color:#fff;padding:8px 12px;font-size:13px;margin-top:4px}
button,.btn{background:var(--indigo);border:none;color:#fff;padding:9px 16px;border-radius:8px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}
.btn-rose{background:var(--rose)} .btn-emerald{background:var(--emerald)}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:13px}
th{text-align:left;color:var(--sky);padding:12px;border-bottom:2px solid var(--line);text-transform:uppercase;font-size:11px}
td{padding:12px;border-bottom:1px solid var(--line)}
.estado{display:inline-block;padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700}
.PENDIENTE{background:#422006;color:#fef08a} .APROBADO{background:#064e3b;color:#a7f3d0} .NO_APROBADO{background:#450a0a;color:#fecaca} .CANCELADO{background:#334155;color:#cbd5e1}
.bar-container{background:#0f172a;border-radius:6px;height:12px;overflow:hidden;margin-top:4px}
.bar-fill{height:100%;background:var(--sky)}
</style>
</head>
<body>
<header class="barra">
  <div class="marca">U</div>
  <div><strong>UniKit MVP</strong> <small style="display:block;color:var(--muted);font-size:11px">Panel de Control de Pedidos</small></div>
</header>
<main>
  <div class="tabs">
    <a href="@@TAB_PEDIDOS@@" class="@@ACTIVO_PEDIDOS@@">📋 Pedidos</a>
    <a href="@@TAB_STATS@@" class="@@ACTIVO_STATS@@">📊 Estadísticas</a>
  </div>

  <section class="resumen">
    <div class="dato"><span>Total Pedidos</span><strong>@@STAT_TOTAL@@</strong></div>
    <div class="dato"><span>Aprobados</span><strong style="color:var(--emerald)">@@STAT_APROBADOS@@</strong></div>
    <div class="dato"><span>Pendientes</span><strong style="color:#fef08a">@@STAT_PENDIENTES@@</strong></div>
    <div class="dato"><span>Valor Aprobado</span><strong style="color:var(--sky)">@@STAT_VALOR@@</strong></div>
  </section>

  <section class="panel">
    <form method="get" class="filtros">
      <input type="hidden" name="vista" value="@@VISTA_ACTUAL@@">
      <div><label>Desde</label><input type="date" name="desde" value="@@FILTRO_DESDE@@"></div>
      <div><label>Hasta</label><input type="date" name="hasta" value="@@FILTRO_HASTA@@"></div>
      <div>
        <label>Estado</label>
        <select name="estado">
          <option value="">Todos</option>
          <option value="PENDIENTE" @@SEL_PENDIENTE@@>Pendientes</option>
          <option value="APROBADO" @@SEL_APROBADO@@>Aprobados</option>
          <option value="NO APROBADO" @@SEL_NO_APROBADO@@>No Aprobados</option>
          <option value="CANCELADO" @@SEL_CANCELADO@@>Cancelados</option>
        </select>
      </div>
      <div><label>Buscar Consecutivo</label><input type="text" name="buscar" placeholder="PED-0001" value="@@FILTRO_BUSCAR@@"></div>
      <button type="submit">Filtrar</button>
      <a href="/?vista=@@VISTA_ACTUAL@@" class="btn" style="background:var(--surface)">Limpiar</a>
    </form>

    @@CONTENIDO_VISTA@@
  </section>
</main>
</body>
</html>
'''

def render_pedidos(pedidos, filtros):
    if filtros['detalle']:
        pedido = next((p for p in pedidos if p['consecutivo'] == filtros['detalle']), None)
        if pedido:
            historial = obtener_historial(pedido['id'])
            html_hist = "".join([f"<li><strong>{h['estado_anterior']} ➔ {h['estado_nuevo']}</strong> por {h['actor']} el {h['fecha_hora']} <br><small>Motivo: {escape(h['motivo'])}</small></li>" for h in historial]) or "<li>Sin cambios registrados.</li>"
            
            form_decisión = ""
            if pedido['estado'] == 'PENDIENTE':
                form_decisión = f'''
                <hr style="border-color:var(--line);margin:20px 0;">
                <h3>Tomar Decisión</h3>
                <form method="post" action="/decidir" style="display:flex;flex-direction:column;gap:10px;max-width:500px;">
                    <input type="hidden" name="consecutivo" value="{pedido['consecutivo']}">
                    <label>Motivo de la decisión (obligatorio para No Aprobar o Cancelar):
                        <textarea name="motivo" rows="3" style="width:100%"></textarea>
                    </label>
                    <div style="display:flex;gap:10px;">
                        <button type="submit" name="accion" value="APROBADO" class="btn btn-emerald">Aprobar Pedido</button>
                        <button type="submit" name="accion" value="NO APROBADO" class="btn btn-rose">No Aprobar</button>
                        <button type="submit" name="accion" value="CANCELADO" class="btn" style="background:var(--muted)">Cancelar</button>
                    </div>
                </form>
                '''

            return f'''
            <a href="{enlace(filtros, detalle='')}" class="btn" style="margin-bottom:15px;">← Volver a la lista</a>
            <h2>Detalle del Pedido {pedido['consecutivo']}</h2>
            <p><strong>Cliente:</strong> {escape(pedido['cliente'])} | <strong>Producto:</strong> {escape(pedido['nombre_producto'])} (x{pedido['cantidad']})</p>
            <p><strong>Total:</strong> {pesos(pedido['total'])} | <strong>Fecha:</strong> {pedido['fecha']} {pedido['hora']}</p>
            <p><strong>Estado Actual:</strong> <span class="estado {pedido['estado'].replace(' ', '_')}">{pedido['estado']}</span></p>
            {f"<p><strong>Motivo Actual:</strong> {escape(pedido['motivo'])}</p>" if pedido['motivo'] else ""}
            
            <h3>Historial de Cambios</h3>
            <ul>{html_hist}</ul>
            {form_decisión}
            '''

    total_paginas = max(1, ceil(len(pedidos) / POR_PAGINA))
    pagina = min(max(1, filtros['pagina']), total_paginas)
    visibles = pedidos[(pagina - 1) * POR_PAGINA : pagina * POR_PAGINA]

    filas = ""
    for p in visibles:
        est_class = p['estado'].replace(" ", "_")
        url_det = enlace(filtros, detalle=p['consecutivo'])
        filas += f'''<tr>
            <td><strong>{p['consecutivo']}</strong></td>
            <td>{escape(p['cliente'])}</td>
            <td>{escape(p['nombre_producto'])}</td>
            <td>{p['cantidad']}</td>
            <td>{pesos(p['total'])}</td>
            <td>{p['fecha']} {p['hora']}</td>
            <td><span class="estado {est_class}">{p['estado']}</span></td>
            <td><a href="{url_det}" class="btn" style="padding:4px 8px;font-size:11px">Ver detalle</a></td>
        </tr>'''

    if not filas:
        filas = '<tr><td colspan="8" style="text-align:center;padding:30px">No hay pedidos para el filtro seleccionado.</td></tr>'

    paginacion = f'''<div style="margin-top:15px;display:flex;justify-content:space-between;align-items:center;">
        <span>Página {pagina} de {total_paginas} ({len(pedidos)} registros)</span>
        <div>
            {f'<a href="{enlace(filtros, pagina=pagina-1)}" class="btn">Anterior</a>' if pagina > 1 else ''}
            {f'<a href="{enlace(filtros, pagina=pagina+1)}" class="btn">Siguiente</a>' if pagina < total_paginas else ''}
        </div>
    </div>'''

    return f'''<table><thead><tr><th>Pedido</th><th>Cliente</th><th>Producto</th><th>Cant.</th><th>Total</th><th>Fecha</th><th>Estado</th><th>Acción</th></tr></thead><tbody>{filas}</tbody></table>{paginacion}'''

def render_estadisticas(pedidos):
    conteos = Counter(p['estado'] for p in pedidos)
    prods = Counter(p['nombre_producto'] for p in pedidos)
    total = len(pedidos) or 1

    bars_estados = ""
    for est in ESTADOS:
        cant = conteos[est]
        pct = round((cant / total) * 100)
        bars_estados += f'''<div style="margin-bottom:12px">
            <div style="display:flex;justify-content:space-between;font-size:12px"><span>{est}</span><span>{cant} ({pct}%)</span></div>
            <div class="bar-container"><div class="bar-fill" style="width:{pct}%"></div></div>
        </div>'''

    bars_prods = ""
    for prod, cant in prods.most_common(5):
        pct = round((cant / total) * 100)
        bars_prods += f'''<div style="margin-bottom:12px">
            <div style="display:flex;justify-content:space-between;font-size:12px"><span>{escape(prod)}</span><span>{cant} uds</span></div>
            <div class="bar-container"><div class="bar-fill" style="width:{pct}%;background:var(--indigo)"></div></div>
        </div>'''

    return f'''
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-top:10px;">
        <div style="background:#0f172a;padding:16px;border-radius:10px"><h3>Pedidos por Estado</h3>{bars_estados}</div>
        <div style="background:#0f172a;padding:16px;border-radius:10px"><h3>Top Productos Solicitados</h3>{bars_prods or "<p>Sin datos.</p>"}</div>
    </div>
    '''

def pagina(filtros):
    pedidos = consultar('pedido' if filtros['buscar'] else 'todos', filtros['buscar'] or None,
                        desde=filtros['desde'], hasta=filtros['hasta'], estado=filtros['estado'])

    conteos = Counter(p['estado'] for p in pedidos)
    aprobados = [p for p in pedidos if p['estado'] == 'APROBADO']
    val_aprobado = sum(p['total'] for p in aprobados)

    contenido = render_estadisticas(pedidos) if filtros['vista'] == 'estadisticas' else render_pedidos(pedidos, filtros)

    reemplazos = {
        '@@TAB_PEDIDOS@@': enlace(filtros, vista='pedidos', detalle=''),
        '@@TAB_STATS@@': enlace(filtros, vista='estadisticas', detalle=''),
        '@@ACTIVO_PEDIDOS@@': 'activo' if filtros['vista'] == 'pedidos' else '',
        '@@ACTIVO_STATS@@': 'activo' if filtros['vista'] == 'estadisticas' else '',
        '@@VISTA_ACTUAL@@': filtros['vista'],
        '@@STAT_TOTAL@@': str(len(pedidos)),
        '@@STAT_APROBADOS@@': str(conteos['APROBADO']),
        '@@STAT_PENDIENTES@@': str(conteos['PENDIENTE']),
        '@@STAT_VALOR@@': pesos(val_aprobado),
        '@@FILTRO_DESDE@@': escape(filtros['desde']),
        '@@FILTRO_HASTA@@': escape(filtros['hasta']),
        '@@FILTRO_BUSCAR@@': escape(filtros['buscar']),
        '@@SEL_PENDIENTE@@': 'selected' if filtros['estado'] == 'PENDIENTE' else '',
        '@@SEL_APROBADO@@': 'selected' if filtros['estado'] == 'APROBADO' else '',
        '@@SEL_NO_APROBADO@@': 'selected' if filtros['estado'] == 'NO APROBADO' else '',
        '@@SEL_CANCELADO@@': 'selected' if filtros['estado'] == 'CANCELADO' else '',
        '@@CONTENIDO_VISTA@@': contenido
    }

    html = PLANTILLA
    for k, v in reemplazos.items():
        html = html.replace(k, v)
    return html

class ServidorAdmin(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/decidir":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            params = parse_qs(body)

            consecutivo = params.get("consecutivo", [""])[0]
            accion = params.get("accion", [""])[0]
            motivo = params.get("motivo", [""])[0]

            try:
                cambiar_estado(consecutivo, accion, "ADMINISTRADOR LOCAL", motivo)
            except Exception as e:
                print("❌ Error procesando decisión:", e)

            self.send_response(303)
            self.send_header("Location", f"/?vista=pedidos&detalle={consecutivo}")
            self.end_headers()
            return

        self.send_error(404)

    def do_GET(self):
        ruta = urlparse(self.path)
        if ruta.path != "/":
            self.send_error(404)
            return

        params = parse_qs(ruta.query)
        filtros = leer_filtros(params)
        contenido = pagina(filtros).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(contenido)))
        self.end_headers()
        self.wfile.write(contenido)

def main():
    servidor = HTTPServer(("127.0.0.1", 8000), ServidorAdmin)
    print("==================================================")
    print("🎓 PANEL DE CONTROL UNIKIT MVP (SEMANA 04)")
    print("🌐 Ingrese a http://127.0.0.1:8000 en su navegador")
    print("==================================================")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        servidor.server_close()

if __name__ == "__main__":
    main()