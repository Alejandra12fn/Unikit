# ============================================================
# unikit.py - Asistente UniKit MVP con Base de Datos SQLite (Semana 04)
# Electiva Administrativa - Unicomfacauca
# ============================================================

import os
import sys
import re
import time
import json
import sqlite3
import asyncio
import subprocess
import importlib
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

# CONFIGURACIÓN Y CONSTANTES DEL MVP
NOMBRE_NEGOCIO = "UniKit MVP"
USUARIO_BOT = "UniKitMVP_bot"
ESTADOS = ("PENDIENTE", "APROBADO", "NO APROBADO", "CANCELADO")

BASE = Path(__file__).resolve().parent
DB = BASE / "unikit.db"
CARPETA_LIBS = BASE / "libs"
CARPETA_LIBS.mkdir(exist_ok=True)

if str(CARPETA_LIBS) not in sys.path:
    sys.path.insert(0, str(CARPETA_LIBS))

def preparar_librerias():
    requeridas = {
        "python-dotenv": "1.2.4",
        "python-telegram-bot": "22.8",
        "google-genai": "2.30.1"
    }
    try:
        from importlib import metadata
        instaladas = {d.metadata["Name"].lower(): d.version for d in metadata.distributions(path=[str(CARPETA_LIBS)])}
        if all(instaladas.get(n) == v for n, v in requeridas.items()):
            return
    except Exception:
        pass

    print("📦 Preparando librerías automáticamente. Espere...")
    with open(BASE / "instalacion_librerias.log", "a", encoding="utf-8") as registro:
        subprocess.run([
            sys.executable, "-m", "pip", "install", "--upgrade",
            "--target", str(CARPETA_LIBS), "--disable-pip-version-check",
            *[f"{n}=={v}" for n, v in requeridas.items()]
        ], check=True, stdout=registro, stderr=registro)
    importlib.invalidate_caches()

preparar_librerias()

from dotenv import load_dotenv
from google import genai
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# FUNCIÓN AUXILIAR DE ENVÍO SEGURO (Previene BadRequest por Markdown)
async def enviar_mensaje(update: Update, texto, parse_mode="Markdown", reply_markup=None):
    try:
        await update.message.reply_text(texto, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        await update.message.reply_text(texto, parse_mode=None, reply_markup=reply_markup)

# ------------------------------------------------------------
# BASE DE DATOS Y MIGRACIÓN AUTOMÁTICA
# ------------------------------------------------------------
def conectar():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def crear_tabla(con, nombre):
    con.execute(f"""CREATE TABLE {nombre} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        consecutivo TEXT UNIQUE,
        cliente TEXT NOT NULL,
        chat_id INTEGER NOT NULL,
        codigo_producto TEXT NOT NULL,
        nombre_producto TEXT NOT NULL,
        cantidad INTEGER NOT NULL CHECK(cantidad > 0),
        precio_unitario INTEGER NOT NULL CHECK(precio_unitario > 0),
        total INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        hora TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'PENDIENTE'
            CHECK(estado IN ('PENDIENTE', 'APROBADO', 'NO APROBADO', 'CANCELADO')),
        telegram_update_id INTEGER NOT NULL UNIQUE,
        motivo TEXT NOT NULL DEFAULT '',
        actualizado_en TEXT NOT NULL DEFAULT '',
        actualizado_por TEXT NOT NULL DEFAULT '',
        CHECK(total = cantidad * precio_unitario)
    )""")

def iniciar_db():
    con = conectar()
    try:
        con.execute("BEGIN IMMEDIATE")
        existe = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pedidos'").fetchone()
        if not existe:
            crear_tabla(con, "pedidos")
        else:
            columnas = [f[1] for f in con.execute("PRAGMA table_info(pedidos)")]
            base = ["id", "consecutivo", "cliente", "chat_id", "codigo_producto", "nombre_producto", 
                    "cantidad", "precio_unitario", "total", "fecha", "hora", "estado", "telegram_update_id"]
            
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version < 4:
                conteo = con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0]
                secuencia = con.execute("SELECT seq FROM sqlite_sequence WHERE name='pedidos'").fetchone()
                
                crear_tabla(con, "pedidos_semana04")
                campos_destino = base + ["motivo", "actualizado_en", "actualizado_por"]
                
                campos_origen = []
                for c in campos_destino:
                    if c in columnas:
                        campos_origen.append(c)
                    elif c == "telegram_update_id":
                        campos_origen.append("id")
                    else:
                        campos_origen.append("''")
                
                con.execute(
                    "INSERT INTO pedidos_semana04 (" + ",".join(campos_destino) + ") SELECT " +
                    ",".join(campos_origen) + " FROM pedidos"
                )
                
                nuevo = con.execute("SELECT COUNT(*) FROM pedidos_semana04").fetchone()[0]
                if conteo != nuevo:
                    raise ValueError("No coincidió el conteo de pedidos durante la migración.")
                
                con.execute("DROP TABLE pedidos")
                con.execute("ALTER TABLE pedidos_semana04 RENAME TO pedidos")
                
                if secuencia:
                    con.execute("UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name='pedidos'", (secuencia[0],))
                print("🔄 Migración Semana 04 completada: pedidos conservados")

        con.execute("""CREATE TABLE IF NOT EXISTS historial_estados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL REFERENCES pedidos (id),
            estado_anterior TEXT NOT NULL,
            estado_nuevo TEXT NOT NULL,
            actor TEXT NOT NULL,
            motivo TEXT NOT NULL,
            fecha_hora TEXT NOT NULL
        )""")
        
        con.execute("PRAGMA user_version = 4")
        con.commit()
        print("✅ Base de datos verificada (Versión 4):", DB)
    except Exception as err:
        con.rollback()
        print("❌ Error configurando la base de datos:", err)
        raise
    finally:
        con.close()

def pesos(valor):
    return f"${int(valor):,} COP".replace(",", ".")

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

def cambiar_estado(consecutivo, nuevo, actor, motivo="", chat_id=None):
    if nuevo not in ("APROBADO", "NO APROBADO", "CANCELADO"):
        raise ValueError("Decisión no permitida.")
    motivo = motivo.strip()
    if nuevo == "NO APROBADO" and not motivo:
        motivo = "No aprobado por el administrador"

    con = conectar()
    try:
        con.execute("BEGIN IMMEDIATE")
        sql = "SELECT * FROM pedidos WHERE consecutivo=?"
        datos = [consecutivo]
        if chat_id is not None:
            sql += " AND chat_id=?"
            datos.append(chat_id)
        
        fila = con.execute(sql, datos).fetchone()
        if not fila:
            raise ValueError("No se encontró un pedido con ese consecutivo.")
        if fila["estado"] != "PENDIENTE":
            raise ValueError(f"El pedido ya está en estado {fila['estado']}. Solo se pueden modificar pedidos PENDIENTES.")

        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            "UPDATE pedidos SET estado=?, motivo=?, actualizado_en=?, actualizado_por=? WHERE id=? AND estado='PENDIENTE'",
            (nuevo, motivo, ahora, actor, fila["id"])
        )
        con.execute(
            "INSERT INTO historial_estados (pedido_id, estado_anterior, estado_nuevo, actor, motivo, fecha_hora) VALUES (?,?,?,?,?,?)",
            (fila["id"], "PENDIENTE", nuevo, actor, motivo, ahora)
        )
        pedido = dict(con.execute("SELECT * FROM pedidos WHERE id=?", (fila["id"],)).fetchone())
        con.commit()
        return pedido
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

# ------------------------------------------------------------
# CARGA DE CREDENCIALES Y CATÁLOGO
# ------------------------------------------------------------
try:
    from productos import PRODUCTOS
    CATALOGO_DICT = {p["codigo"].upper(): p for p in PRODUCTOS}
except Exception as error:
    print(f"❌ Error al cargar productos.py: {error}")
    PRODUCTOS = []
    CATALOGO_DICT = {}

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

if not TELEGRAM_TOKEN:
    print("❌ Falta TELEGRAM_TOKEN en el archivo .env")
    sys.exit()

cliente_gemini = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ESTADOS Y MEMORIA DE NAVEGACIÓN
sesiones = {}
confirmaciones_cancelacion = {}
solicitudes_cancelacion = set()
memoria_conversaciones = {}

def normalizar(texto):
    return re.sub(r"\s+", " ", texto.lower().strip())

def buscar_producto(codigo):
    return CATALOGO_DICT.get(str(codigo).strip().upper())

def impedimento_cancelacion(pedido):
    if pedido["estado"] == "APROBADO":
        return "⚠️ El administrador ya aprobó tu pedido y no se puede cancelar. ¡Lo sentimos!"
    return f"⚠️ Este pedido se encuentra en estado {pedido['estado']}. Solo puedes cancelar pedidos PENDIENTES."

def gestionar_cancelacion(chat_id, comando, partes):
    texto = " ".join(partes).strip()
    limpio = normalizar(texto)
    iniciar_canc = limpio == "cancelar pedido" or comando == "/cancelar_pedido"
    activo = chat_id in solicitudes_cancelacion or chat_id in confirmaciones_cancelacion

    if iniciar_canc:
        pendientes = consultar("pendientes", chat_id=chat_id)
        if not pendientes:
            return "📋 No tienes ningún pedido en estado PENDIENTE para cancelar."

        codigo_solicitado = partes[1].upper() if len(partes) >= 2 and re.fullmatch(r"PED-[0-9]{4}", partes[1].upper()) else None
        pedido = next((p for p in pendientes if p["consecutivo"] == codigo_solicitado), pendientes[0])
        codigo = pedido["consecutivo"]

        confirmaciones_cancelacion[chat_id] = codigo
        solicitudes_cancelacion.discard(chat_id)

        return (
            f"📋 **Cancelación de Pedido**\n\n"
            f"🔹 Pedido: **{codigo}** | {pedido['nombre_producto']} ({pesos(pedido['total'])})\n"
            f"📌 Estado actual: PENDIENTE\n\n"
            f"¿Estás seguro de que quieres cancelar tu pedido?"
        )

    elif activo and (limpio in ("no", "no gracias") or comando == "/cancelar"):
        solicitudes_cancelacion.discard(chat_id)
        confirmaciones_cancelacion.pop(chat_id, None)
        return "👍 Operación cancelada. Tu pedido sigue conservando su estado actual."

    elif chat_id in confirmaciones_cancelacion:
        codigo = confirmaciones_cancelacion[chat_id]
        confirmar = limpio in ("si", "si por favor", "sí") or (
            comando == "/confirmar_cancelacion" and (len(partes) == 1 or (len(partes) == 2 and partes[1].upper() == codigo))
        )
        if not confirmar:
            return f"¿Estás seguro de que quieres cancelar el pedido {codigo}? Selecciona **Sí** o **No**."
        try:
            pedido = cambiar_estado(codigo, "CANCELADO", f"CLIENTE:{chat_id}", "Cancelado por el cliente", chat_id)
            return f"✅ Pedido {codigo} cancelado correctamente.\nEstado: CANCELADO. El registro se conserva para tu historial."
        except ValueError as error:
            propios = consultar("pedido", codigo, chat_id)
            if propios and propios[0]["estado"] != "PENDIENTE":
                return impedimento_cancelacion(propios[0])
            return f"❌ {error}"
        finally:
            solicitudes_cancelacion.discard(chat_id)
            confirmaciones_cancelacion.pop(chat_id, None)

    return None

def orientar_compra(sesion, texto, chat_id):
    limpio = normalizar(texto)
    if limpio in ("si", "si por favor", "si quiero", "claro"):
        return "Para realizar tu pedido, envía el comando **/comprar**. Luego te solicitaré la cantidad."
    if limpio in ("no", "no gracias"):
        return "Entendido. Puedes seguir explorando el catálogo cuando desees."

    producto = CATALOGO_DICT[sesion["codigo"]]
    m = re.search(r"\b([0-9]+)\b", limpio)
    if m:
        cant = int(m[1])
        total = cant * producto["precio"]
        return (
            f"📊 **Cotización Rápida**\n"
            f"📦 Producto: {producto['nombre']}\n"
            f"🔢 Cantidad: {cant}\n"
            f"💰 Unitario: {pesos(producto['precio'])}\n"
            f"💵 Total: {pesos(total)}\n\n"
            f"¿Deseas comprar? Escribe **/comprar** para iniciar el pedido formal."
        )
    return f"📦 **{producto['nombre']}** tiene un precio de {pesos(producto['precio'])} por unidad.\n¿Cuántas unidades deseas cotizar?"

# ------------------------------------------------------------
# MOTOR DE INTELIGENCIA ARTIFICIAL
# ------------------------------------------------------------
def consultar_groq(mensajes):
    cuerpo = {
        "model": GROQ_MODEL,
        "messages": mensajes,
        "temperature": 0.3,
        "max_completion_tokens": 1024
    }
    solicitud = Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "UniKit-MVP/1.0"
        }
    )
    with urlopen(solicitud, timeout=8) as respuesta:
        datos = json.load(respuesta)
        texto = datos["choices"][0]["message"]["content"]
        if not texto:
            raise ValueError("Groq devolvió un contenido vacío.")
        return texto.strip()

def responder_ia(chat_id, codigo, texto):
    inicio = time.monotonic()
    instrucciones = (
        f"Eres Kit, el asistente de {NOMBRE_NEGOCIO}. Responde en español y en menos de 100 palabras. "
        f"Catálogo oficial: {PRODUCTOS}. Producto consultado: {CATALOGO_DICT.get(codigo, 'Ninguno')}. "
        "Sé breve, servicial y amigable. Si el cliente quiere comprar, dile que envíe /comprar."
    )

    historia = memoria_conversaciones.get(chat_id, [])
    mensajes = [{"role": "system", "content": instrucciones}] + historia[-10:] + [{"role": "user", "content": texto[:2000]}]

    respuesta = None
    proveedor = ""

    if GROQ_API_KEY:
        try:
            respuesta = consultar_groq(mensajes)
            proveedor = "Groq"
        except Exception as error:
            print(f"⚠️ Groq no respondió: {error}. Pasando a Gemini emergente...")

    if respuesta is None and cliente_gemini:
        try:
            prompt = instrucciones + "\nConversación reciente: " + str(mensajes[1:])
            res = cliente_gemini.interactions.create(model=GEMINI_MODEL, input=prompt)
            if res.output_text:
                respuesta = res.output_text.strip()
                proveedor = f"Gemini ({GEMINI_MODEL})"
        except Exception as error:
            print(f"⚠️ Gemini emergente falló: {error}")

    if respuesta is None:
        respuesta = "En este momento estoy consultando el catálogo. Escribe **/comprar** para iniciar tu pedido o **/mis_pedidos** para ver tus compras."

    memoria_conversaciones[chat_id] = (historia + [{"role": "user", "content": texto[:2000]}, {"role": "assistant", "content": respuesta}])[-10:]
    print(f"🤖 Respuesta IA mediante [{proveedor}] en {round(time.monotonic() - inicio, 2)}s")
    return respuesta

def botones_teclado(chat_id):
    if chat_id in confirmaciones_cancelacion:
        return ReplyKeyboardMarkup([["Sí", "No"]], resize_keyboard=True)
    
    sesion = sesiones.get(chat_id, {})
    etapa = sesion.get("etapa")
    
    if etapa in ("cantidad", "cantidad_cotizacion"):
        return ReplyKeyboardMarkup([["/cancelar"]], resize_keyboard=True)
    
    if etapa == "confirmar_seleccion":
        return ReplyKeyboardMarkup([["Confirmar pedido"], ["/mis_pedidos", "/cancelar"]], resize_keyboard=True)

    if etapa == "esperando_codigo_compra":
        return ReplyKeyboardMarkup([["/mis_pedidos", "/cancelar"]], resize_keyboard=True)
        
    return ReplyKeyboardMarkup([["/cotizar", "/comprar"], ["/mis_pedidos", "Cancelar pedido"]], resize_keyboard=True)

# ------------------------------------------------------------
# HANDLERS DE TELEGRAM
# ------------------------------------------------------------
async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    nombre = update.effective_user.first_name or "Estudiante"

    solicitudes_cancelacion.discard(chat_id)
    confirmaciones_cancelacion.pop(chat_id, None)

    if context.args:
        arg = context.args[0].strip().upper()
        if arg == "MIS_PEDIDOS":
            await mis_pedidos(update, context)
            return

        producto = buscar_producto(arg)
        if producto:
            sesiones[chat_id] = {"codigo": arg, "etapa": "consulta"}
            msg = (
                f"¡Hola {nombre}! 👋 bienvenido a **{NOMBRE_NEGOCIO}**\n\n"
                f"Llegaste consultando:\n"
                f"📦 **[{producto['codigo']}] {producto['nombre']}**\n"
                f"💰 **Precio:** {pesos(producto['precio'])}\n"
                f"📝 {producto.get('descripcion', '')}\n\n"
                f"¿Qué deseas hacer? Puedes pulsar **/cotizar** o **/comprar**."
            )
            await enviar_mensaje(update, msg, reply_markup=botones_teclado(chat_id))
            return

    msg = (
        f"¡Hola {nombre}! 🎓 bienvenido a **{NOMBRE_NEGOCIO}**.\n\n"
        f"Explora nuestros productos para estudiantes y dime en qué te puedo ayudar hoy."
    )
    await enviar_mensaje(update, msg, reply_markup=botones_teclado(chat_id))

async def cmd_comprar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sesion = sesiones.get(chat_id, {})
    codigo = sesion.get("codigo")

    if not codigo:
        sesiones[chat_id] = {"codigo": "", "etapa": "esperando_codigo_compra"}
        msg = (
            "🛒 **Iniciar Compra**\n\n"
            "Aún no tienes un producto seleccionado.\n\n"
            "Por favor, escribe el **código del producto** que deseas comprar (ejemplo: `TEC-01`, `PAP-01`)."
        )
        await enviar_mensaje(update, msg, reply_markup=botones_teclado(chat_id))
        return

    producto = CATALOGO_DICT.get(codigo)
    if not producto:
        sesiones[chat_id] = {"codigo": "", "etapa": "esperando_codigo_compra"}
        await enviar_mensaje(update, "⚠️ No encontré el producto seleccionado. Por favor escribe su código (ejemplo: `TEC-01`).")
        return

    sesion["etapa"] = "confirmar_seleccion"
    msg = (
        f"🛒 **Confirmación de Producto**\n\n"
        f"Estás a punto de pedir:\n"
        f"📦 **[{producto['codigo']}] {producto['nombre']}**\n"
        f"💰 **Precio:** {pesos(producto['precio'])}\n\n"
        f"¿Estás seguro de que este es el producto que deseas?\n\n"
        f"✅ Para continuar con tu compra, presiona o escribe **Confirmar pedido**."
    )
    await enviar_mensaje(update, msg, reply_markup=botones_teclado(chat_id))

async def cmd_cotizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sesion = sesiones.get(chat_id, {})

    if not sesion or not sesion.get("codigo"):
        await enviar_mensaje(update, "⚠️ Primero selecciona o escribe el código de un producto (ejemplo: `TEC-01`).")
        return

    sesion["etapa"] = "cantidad_cotizacion"
    await enviar_mensaje(update, "¿Cuántas unidades deseas cotizar? Escribe un número entre 1 y 999 (esta consulta no genera pedido).", reply_markup=botones_teclado(chat_id))

async def mis_pedidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    nombre = update.effective_user.first_name or "Cliente"
    pedidos = consultar("todos", chat_id=chat_id)

    if not pedidos:
        await enviar_mensaje(
            update,
            f"📋 Control de pedidos del cliente — {nombre}\n"
            f"Aún no ha realizado pedidos. Escriba /comprar para realizar su primer pedido."
        )
        return

    txt = f"📋 Control de pedidos del cliente — {nombre}\n\n"
    for p in pedidos:
        txt += f"🔹 Pedido {p['consecutivo']} | {p['nombre_producto']} | Cantidad: {p['cantidad']} | Total: {pesos(p['total'])} | Estado: {p['estado']}\n"
        if p.get("motivo"):
            txt += f"   Motivo: {p['motivo']}\n"
    
    await enviar_mensaje(update, txt, reply_markup=botones_teclado(chat_id))

async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    nombre = update.effective_user.first_name or "Estudiante"
    texto = update.message.text.strip()
    partes = texto.split()
    comando = partes[0].lower() if partes else ""
    limpio = normalizar(texto)

    sesion = sesiones.setdefault(chat_id, {"codigo": "", "etapa": "consulta"})

    # 1. ATENCIÓN AL COMANDO /cancelar MIENTRAS SE INGRESA CANTIDAD O EN COMPRA
    if comando == "/cancelar" or limpio in ("cancelar", "cancelar solicitud"):
        if chat_id in confirmaciones_cancelacion:
            confirmaciones_cancelacion.pop(chat_id, None)
            await enviar_mensaje(update, "👍 Operación cancelada. Tu pedido sigue conservando su estado actual.", reply_markup=botones_teclado(chat_id))
            return

        if sesion.get("etapa") in ("cantidad", "cantidad_cotizacion", "confirmar_seleccion", "esperando_codigo_compra"):
            sesion["etapa"] = "consulta"
            await enviar_mensaje(update, "👍 Solicitud cancelada. No se ha registrado ningún pedido.", reply_markup=botones_teclado(chat_id))
            return

    # 2. Gestionar proceso de cancelación (Botón Cancelar pedido -> "¿Estás seguro...?")
    resp_canc = gestionar_cancelacion(chat_id, comando, partes)
    if resp_canc is not None:
        await enviar_mensaje(update, resp_canc, reply_markup=botones_teclado(chat_id))
        return

    # 3. Si estaba esperando el código para comprar directamente
    if sesion.get("etapa") == "esperando_codigo_compra":
        codigo_ingresado = texto.upper().strip()
        producto = buscar_producto(codigo_ingresado)
        if not producto:
            await enviar_mensaje(
                update,
                f"⚠️ No encontré el producto `{codigo_ingresado}`.\n"
                f"Por favor escribe un código válido (ejemplo: `TEC-01`, `PAP-01`)."
            )
            return

        sesion["codigo"] = codigo_ingresado
        sesion["etapa"] = "confirmar_seleccion"
        msg = (
            f"🛒 **Confirmación de Producto**\n\n"
            f"Estás a punto de pedir:\n"
            f"📦 **[{producto['codigo']}] {producto['nombre']}**\n"
            f"💰 **Precio:** {pesos(producto['precio'])}\n\n"
            f"¿Estás seguro de que este es el producto que deseas?\n\n"
            f"✅ Para continuar con tu compra, presiona o escribe **Confirmar pedido**."
        )
        await enviar_mensaje(update, msg, reply_markup=botones_teclado(chat_id))
        return

    # 4. Si el usuario envía "Confirmar pedido"
    if sesion.get("etapa") == "confirmar_seleccion" or limpio in ("confirmar pedido", "confirmar_pedido", "confirmar"):
        if sesion.get("codigo"):
            sesion["etapa"] = "cantidad"
            await enviar_mensaje(
                update,
                "¿Cuántas unidades desea? Escriba un número de 1 a 999.",
                reply_markup=ReplyKeyboardMarkup([["/cancelar"]], resize_keyboard=True)
            )
            return

    # 5. Gestionar ingreso de cantidad para cotización
    if sesion.get("etapa") == "cantidad_cotizacion":
        if not texto.isdigit() or int(texto) <= 0 or int(texto) > 999:
            await enviar_mensaje(update, "⚠️ Por favor ingresa un número de unidades válido (1 a 999) o envía /cancelar.")
            return
        sesion["etapa"] = "consulta"
        resp = orientar_compra(sesion, texto, chat_id)
        await enviar_mensaje(update, resp, reply_markup=botones_teclado(chat_id))
        return

    # 6. Gestionar ingreso de cantidad para compra
    if sesion.get("etapa") == "cantidad":
        if not texto.isdigit() or int(texto) <= 0 or int(texto) > 999:
            await enviar_mensaje(update, "⚠️ Por favor ingrese un número válido entre 1 y 999 o envíe /cancelar.")
            return

        cantidad = int(texto)
        producto = CATALOGO_DICT.get(sesion["codigo"])
        
        if not producto:
            sesion["etapa"] = "consulta"
            await enviar_mensaje(update, "⚠️ Ocurrió un inconveniente con el producto. Selecciona de nuevo el producto deseado.")
            return

        total = cantidad * producto["precio"]

        con = conectar()
        cursor = con.cursor()
        ahora = datetime.now()
        fecha_str = ahora.strftime("%Y-%m-%d")
        hora_str = ahora.strftime("%H:%M:%S")

        cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM pedidos")
        siguiente_id = cursor.fetchone()[0]
        consecutivo = f"PED-{siguiente_id:04d}"

        cursor.execute("""
            INSERT INTO pedidos (consecutivo, cliente, chat_id, codigo_producto, nombre_producto, cantidad, precio_unitario, total, fecha, hora, estado, telegram_update_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE', ?)
        """, (consecutivo, nombre, chat_id, producto["codigo"], producto["nombre"], cantidad, producto["precio"], total, fecha_str, hora_str, update.update_id))

        con.commit()
        con.close()

        sesion["etapa"] = "consulta"

        msg_confirmacion = (
            f"📋 Control de pedidos del cliente — {nombre}\n"
            f"✅ Pedido {consecutivo} registrado.\n"
            f"📦 Producto: {producto['nombre']}\n"
            f"Cantidad: {cantidad}\n"
            f"Unitario: {pesos(producto['precio'])}\n"
            f"Total: {pesos(total)}\n"
            f"📌 Estado: PENDIENTE\n\n"
            f"Puede cancelar este pedido mientras el administrador no lo haya aprobado.\n"
            f"Para consultar sus pedidos: /mis_pedidos"
        )
        await enviar_mensaje(update, msg_confirmacion, reply_markup=botones_teclado(chat_id))
        return

    # 7. Auto-captura de códigos ingresados por el usuario
    for cod in CATALOGO_DICT:
        if cod in texto.upper():
            sesion["codigo"] = cod
            break

    # 8. Atención mediante Inteligencia Artificial
    codigo_prod = sesion.get("codigo", "")
    respuesta_ia = await asyncio.to_thread(responder_ia, chat_id, codigo_prod, texto)

    # Auto-captura de productos sugeridos por la IA
    for cod in CATALOGO_DICT:
        if cod in respuesta_ia.upper():
            sesion["codigo"] = cod
            break

    await enviar_mensaje(update, respuesta_ia, reply_markup=botones_teclado(chat_id))

# ------------------------------------------------------------
# INICIALIZACIÓN PRINCIPAL
# ------------------------------------------------------------
def main():
    iniciar_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", iniciar))
    app.add_handler(CommandHandler("comprar", cmd_comprar))
    app.add_handler(CommandHandler("cotizar", cmd_cotizar))
    app.add_handler(CommandHandler("mis_pedidos", mis_pedidos))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje))

    print("==================================================")
    print(f"🚀 Bot {NOMBRE_NEGOCIO} activo y escuchando en Telegram...")
    print("==================================================")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()