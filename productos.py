# ==============================================================================
# productos.py
# Base de conocimiento de UniKit MVP - Vitrina Virtual Universitaria
# Unicomfacauca - Electiva Administrativa
# ==============================================================================

PRODUCTOS = [
    # --------------------------------------------------------------------------
    # CATEGORÍA: PAPELERÍA
    # --------------------------------------------------------------------------
    {
        "codigo": "PAP-01",
        "nombre": "Cuaderno Profesional Norma 100 hojas",
        "descripcion": "El clásico para tus apuntes: cuaderno profesional cuadriculado con tapa dura.",
        "precio": 8900,
        "categoria": "papeleria",
        "marca": "Norma"
    },
    {
        "codigo": "PAP-02",
        "nombre": "Kit 5 Esferos Bic Cristal",
        "descripcion": "Pack de esferos Bic Cristal para escribir con fluidez todo el semestre.",
        "precio": 6900,
        "categoria": "papeleria",
        "marca": "Bic"
    },
    {
        "codigo": "PAP-03",
        "nombre": "Archivador de Palanca Artesco",
        "descripcion": "Organiza tus documentos y parciales con este archivador de palanca.",
        "precio": 15900,
        "categoria": "papeleria",
        "marca": "Artesco"
    },

    # --------------------------------------------------------------------------
    # CATEGORÍA: TECNOLOGÍA
    # --------------------------------------------------------------------------
    {
        "codigo": "TEC-01",
        "nombre": "Audífonos Inalámbricos Redmi Buds 4 Lite",
        "descripcion": "Sonido inalámbrico cómodo para estudiar y asistir a clases virtuales.",
        "precio": 99900,
        "categoria": "tecnologia",
        "marca": "Xiaomi"
    },
    {
        "codigo": "TEC-02",
        "nombre": "Memoria USB SanDisk Cruzer Blade 64GB",
        "descripcion": "Almacenamiento portátil y confiable para trabajos, diapositivas y respaldos.",
        "precio": 39900,
        "categoria": "tecnologia",
        "marca": "SanDisk"
    },
    {
        "codigo": "TEC-03",
        "nombre": "Power Bank Xiaomi 10.000 mAh",
        "descripcion": "Energía de respaldo para que tu celular aguante toda la jornada en la U.",
        "precio": 119900,
        "categoria": "tecnologia",
        "marca": "Xiaomi"
    },

    # --------------------------------------------------------------------------
    # CATEGORÍA: ACCESORIOS
    # --------------------------------------------------------------------------
    {
        "codigo": "ACC-01",
        "nombre": "Termo Acero Inoxidable 750 ml",
        "descripcion": "Hidratación todo el día: frío o caliente donde sea que estudies.",
        "precio": 54900,
        "categoria": "accesorios",
        "marca": "UniKit"
    },
    {
        "codigo": "ACC-02",
        "nombre": "Mochila Antirrobo con Puerto USB",
        "descripcion": "Tu laptop y tus libros seguros, con bolsillo antirrobo y puerto USB.",
        "precio": 129900,
        "categoria": "accesorios",
        "marca": "UniKit"
    },
    {
        "codigo": "ACC-03",
        "nombre": "Estuche Triple Cierre Artesco",
        "descripcion": "Todo tu material de escritura organizado en un solo lugar.",
        "precio": 24900,
        "categoria": "accesorios",
        "marca": "Artesco"
    }
]



'''
def obtener_producto_por_codigo(codigo: str):
    """Busca y retorna un producto según su código (ej: 'PAP-01')."""
    for producto in PRODUCTOS:
        if producto["codigo"].upper() == codigo.strip().upper():
            return producto
    return None

def listar_productos_por_categoria(categoria: str):
    """Filtra y retorna productos según la categoría requerida."""
    return [p for p in PRODUCTOS if p.get("categoria") == categoria.strip().lower()]"""
    '''