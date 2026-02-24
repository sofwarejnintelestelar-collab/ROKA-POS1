# ==============================
# IMPORTS CORRECTOS
# ==============================
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import psycopg2
from datetime import datetime, date, timedelta
import json
import hashlib
from functools import wraps
import os
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_secreta_pos_2024_sistema_login')

# ==============================
# CONEXIÓN A BASE DE DATOS PARA RENDER
# ==============================
def get_db_connection():
    # Para Render: usar DATABASE_URL
    # Para desarrollo local: usar variables locales
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Conexión para Render (PostgreSQL en la nube)
        result = urlparse(database_url)
        return psycopg2.connect(
            host=result.hostname,
            database=result.path[1:],  # Elimina el '/' inicial
            user=result.username,
            password=result.password,
            port=result.port,
            sslmode='require'
        )
    else:
        # Conexión para desarrollo local
        return psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            port=os.environ.get('DB_PORT', '5432'),
            database=os.environ.get('DB_NAME', 'roka'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD', 'pm')
        )

# ==============================
# CREACIÓN DE TABLAS (SI NO EXISTEN)
# ==============================
def create_tables():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        print("📝 Creando/verificando tablas...")
        
        # Tabla usuarios
        cur.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                nombre VARCHAR(100) NOT NULL,
                email VARCHAR(100),
                rol VARCHAR(20) DEFAULT 'cajero',
                activo BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla categorias
        cur.execute('''
            CREATE TABLE IF NOT EXISTS categorias (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla proveedores
        cur.execute('''
            CREATE TABLE IF NOT EXISTS proveedores (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(200) NOT NULL,
                contacto VARCHAR(100),
                telefono VARCHAR(20),
                email VARCHAR(100),
                direccion TEXT,
                activo BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla mesas
        cur.execute('''
            CREATE TABLE IF NOT EXISTS mesas (
                id SERIAL PRIMARY KEY,
                numero INTEGER UNIQUE NOT NULL,
                capacidad INTEGER DEFAULT 4,
                estado VARCHAR(20) DEFAULT 'disponible',
                ubicacion VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla productos
        cur.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id SERIAL PRIMARY KEY,
                codigo_barra VARCHAR(50) UNIQUE,
                nombre VARCHAR(200) NOT NULL,
                precio DECIMAL(10,2) NOT NULL,
                stock INTEGER DEFAULT 0,
                categoria_id INTEGER,
                proveedor_id INTEGER,
                tipo VARCHAR(20) DEFAULT 'producto',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE SET NULL,
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id) ON DELETE SET NULL
            )
        ''')
        
        # Tabla ordenes
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ordenes (
                id SERIAL PRIMARY KEY,
                mesa_id INTEGER NOT NULL,
                mozo_nombre VARCHAR(100) NOT NULL,
                estado VARCHAR(20) DEFAULT 'abierta',
                observaciones TEXT,
                total DECIMAL(10,2) DEFAULT 0,
                fecha_apertura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_cierre TIMESTAMP,
                dispositivo_origen VARCHAR(100),
                FOREIGN KEY (mesa_id) REFERENCES mesas(id) ON DELETE CASCADE
            )
        ''')
        
        # Tabla orden_items
        cur.execute('''
            CREATE TABLE IF NOT EXISTS orden_items (
                id SERIAL PRIMARY KEY,
                orden_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                producto_nombre VARCHAR(200) NOT NULL,
                cantidad INTEGER NOT NULL,
                precio_unitario DECIMAL(10,2) NOT NULL,
                observaciones TEXT,
                estado_item VARCHAR(20) DEFAULT 'pendiente',
                tiempo_inicio TIMESTAMP,
                tiempo_fin TIMESTAMP,
                tiempo_estimado INTEGER DEFAULT 15,
                FOREIGN KEY (orden_id) REFERENCES ordenes(id) ON DELETE CASCADE,
                FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE SET NULL
            )
        ''')
        
        # Tabla caja_turnos
        cur.execute('''
            CREATE TABLE IF NOT EXISTS caja_turnos (
                id SERIAL PRIMARY KEY,
                fecha_apertura TIMESTAMP NOT NULL,
                fecha_cierre TIMESTAMP,
                monto_inicial DECIMAL(10,2) NOT NULL DEFAULT 0,
                monto_final_real DECIMAL(10,2),
                total_ventas DECIMAL(10,2) DEFAULT 0,
                monto_esperado DECIMAL(10,2),
                diferencia DECIMAL(10,2),
                observaciones TEXT,
                estado VARCHAR(20) DEFAULT 'abierta',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla cierres_caja
        cur.execute('''
            CREATE TABLE IF NOT EXISTS cierres_caja (
                id SERIAL PRIMARY KEY,
                turno_id INTEGER,
                fecha_cierre TIMESTAMP NOT NULL,
                monto_total DECIMAL(10,2) NOT NULL,
                monto_efectivo DECIMAL(10,2),
                monto_tarjeta DECIMAL(10,2),
                monto_transferencia DECIMAL(10,2),
                observaciones TEXT,
                usuario_cierre VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (turno_id) REFERENCES caja_turnos(id) ON DELETE SET NULL
            )
        ''')
        
        # Insertar datos iniciales si no existen
        cur.execute("SELECT COUNT(*) FROM usuarios WHERE username = 'admin'")
        if cur.fetchone()[0] == 0:
            print("👤 Creando usuarios por defecto...")
            password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            
            usuarios_default = [
                ('admin', password_hash, 'Administrador', 'admin@sistema.com', 'admin'),
                ('mozo', hashlib.sha256('mozo123'.encode()).hexdigest(), 'Mozo Principal', 'mozo@sistema.com', 'mozo'),
                ('chef', hashlib.sha256('chef123'.encode()).hexdigest(), 'Chef Principal', 'chef@sistema.com', 'chef'),
                ('cajero', hashlib.sha256('cajero123'.encode()).hexdigest(), 'Cajero Principal', 'cajero@sistema.com', 'cajero')
            ]
            
            for user in usuarios_default:
                cur.execute('''
                    INSERT INTO usuarios (username, password_hash, nombre, email, rol) 
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (username) DO NOTHING
                ''', user)
        
        # Insertar mesas por defecto
        for i in range(1, 11):
            cur.execute('''
                INSERT INTO mesas (numero, capacidad) 
                VALUES (%s, %s) 
                ON CONFLICT (numero) DO NOTHING
            ''', (i, 4))
        
        # Insertar categorías por defecto
        categorias_default = ['ENTRADAS', 'PICADAS', 'EMPANADAS', 'MINUTAS', 'GUARNICIONES', 
                             'PASTAS', 'SALSAS', 'PIZZAS', 'PLATOS ESPECIALES', 'POSTRES', 'HELADOS', 'BEBIDAS']
        for categoria in categorias_default:
            cur.execute('''
                INSERT INTO categorias (nombre) 
                VALUES (%s) 
                ON CONFLICT (nombre) DO NOTHING
            ''', (categoria,))
        
        # Insertar productos de ejemplo
        cur.execute("SELECT COUNT(*) FROM productos")
        if cur.fetchone()[0] == 0:
            print("📦 Creando productos de ejemplo...")
            productos_ejemplo = [
                ('Pizza Margarita', 2500.00, 'comida'),
                ('Hamburguesa Clásica', 1800.00, 'comida'),
                ('Ensalada César', 1200.00, 'comida'),
                ('Coca Cola 500ml', 800.00, 'bebida'),
                ('Agua Mineral 500ml', 500.00, 'bebida'),
                ('Jugo de Naranja', 700.00, 'bebida'),
                ('Papas Fritas', 900.00, 'comida'),
                ('Cerveza Artesanal', 1200.00, 'bebida'),
                ('Flan Casero', 600.00, 'comida'),
                ('Café Americano', 400.00, 'bebida')
            ]
            for nombre, precio, tipo in productos_ejemplo:
                cur.execute('''
                    INSERT INTO productos (nombre, precio, tipo) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                ''', (nombre, precio, tipo))
        
        conn.commit()
        print("✅ Tablas creadas/verificadas exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error al crear tablas: {e}")
        return False
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

# Crear tablas al inicio (importante para Render)
create_tables()

# ==============================
# FUNCIONES DE AUTENTICACIÓN
# ==============================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    return hash_password(password) == password_hash

def login_user(username, password):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id, username, password_hash, nombre, rol FROM usuarios WHERE username = %s AND activo = true', (username,))
        usuario = cur.fetchone()
        if usuario and verify_password(password, usuario[2]):
            return {'id': usuario[0], 'username': usuario[1], 'nombre': usuario[3], 'rol': usuario[4]}
        return None
    except Exception as e:
        print(f"❌ Error en login: {e}")
        return None
    finally:
        cur.close()
        conn.close()

def get_usuario_actual():
    """Obtiene usuario actual con manejo de errores mejorado"""
    if 'user_id' not in session:
        return None
    
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            print("❌ No se pudo conectar a DB en get_usuario_actual")
            return None
            
        cur = conn.cursor()
        cur.execute('SELECT id, username, nombre, rol FROM usuarios WHERE id = %s', (session['user_id'],))
        usuario = cur.fetchone()
        
        if usuario:
            return {'id': usuario[0], 'username': usuario[1], 'nombre': usuario[2], 'rol': usuario[3]}
        else:
            # Usuario no existe en DB pero tiene sesión
            print(f"⚠️ Usuario ID {session['user_id']} no encontrado en DB")
            return None
            
    except psycopg2.OperationalError as e:
        print(f"❌ Error de conexión a DB: {e}")
        return None
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return None
    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except:
            pass

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==============================
# FUNCIÓN PARA ABRIR CAJA AUTOMÁTICAMENTE
# ==============================
def abrir_caja_automaticamente():
    """Abre caja automáticamente si no hay una abierta"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar si ya hay caja abierta
        cur.execute("SELECT id FROM caja_turnos WHERE estado = 'abierta'")
        if cur.fetchone():
            return True
        
        # Abrir nueva caja automáticamente
        cur.execute('''
            INSERT INTO caja_turnos (fecha_apertura, monto_inicial, observaciones, estado)
            VALUES (NOW(), 0, 'Caja abierta automáticamente al iniciar sesión', 'abierta')
        ''')
        conn.commit()
        return True
        
    except Exception as e:
        print(f"❌ Error al abrir caja automáticamente: {e}")
        return False
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

# ==============================
# RUTAS PRINCIPALES
# ==============================
@app.route("/")
def index():
    """Página principal"""
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    """Login para sistema - VERSIÓN CORREGIDA (sin loop infinito)"""
    
    # ===== MANEJO DE SESIÓN ACTIVA CON VALIDACIÓN =====
    if 'user_id' in session:
        try:
            usuario_actual = get_usuario_actual()
            
            # CASO 1: Sesión válida - usuario existe en DB
            if usuario_actual:
                flash(f'Ya estás logueado como {usuario_actual["nombre"]}', 'info')
                
                # Redirigir según rol
                if usuario_actual['rol'] == 'chef':
                    return redirect(url_for('chef'))
                elif usuario_actual['rol'] == 'mozo':
                    return redirect(url_for('ordenes'))
                else:
                    # Para admin y cajero: abrir caja automáticamente
                    abrir_caja_automaticamente()
                    return redirect(url_for('caja'))
            
            # CASO 2: Sesión INVÁLIDA - usuario no existe en DB
            else:
                print(f"⚠️ Sesión inválida detectada - limpiando...")
                session.clear()
                flash('Sesión inválida. Por favor, inicia sesión nuevamente.', 'warning')
                # Continúa hacia el formulario de login
                
        except Exception as e:
            # CASO 3: Error grave (DB caída, etc.)
            print(f"❌ Error crítico validando sesión: {e}")
            session.clear()
            flash('Error del sistema. Por favor, intenta más tarde.', 'danger')
            # Renderiza login sin sesión
            return render_template("login.html", ahora=datetime.now())
    
    # ===== PROCESAMIENTO DEL FORMULARIO DE LOGIN =====
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        if not username or not password:
            flash('Usuario y contraseña son requeridos', 'danger')
            return render_template("login.html", ahora=datetime.now())
        
        try:
            usuario = login_user(username, password)
            
            if usuario:
                # Login exitoso
                session['user_id'] = usuario['id']
                session['username'] = usuario['username']
                session['nombre'] = usuario['nombre']
                session['rol'] = usuario['rol']
                flash(f'¡Bienvenido {usuario["nombre"]}!', 'success')
                
                # Redirigir según rol
                if usuario['rol'] == 'chef':
                    return redirect(url_for('chef'))
                elif usuario['rol'] == 'mozo':
                    return redirect(url_for('ordenes'))
                else:
                    # Para admin y cajero: abrir caja automáticamente
                    if abrir_caja_automaticamente():
                        flash('Turno de caja abierto automáticamente', 'info')
                    return redirect(url_for('caja'))
            else:
                flash('Usuario o contraseña incorrectos', 'danger')
                
        except Exception as e:
            print(f"❌ Error en proceso de login: {e}")
            flash('Error al conectar con la base de datos', 'danger')
    
    # ===== MOSTRAR FORMULARIO DE LOGIN =====
    return render_template("login.html", ahora=datetime.now())

# ==============================
# RUTA PARA VERIFICAR/REPARAR TABLAS
# ==============================
@app.route("/verificar-tablas")
def verificar_tablas():
    """Ruta para verificar y reparar tablas si es necesario"""
    try:
        success = create_tables()
        if success:
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Tablas Verificadas</title>
                <style>
                    body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                    .success { color: green; font-size: 24px; margin: 20px 0; }
                    .info { margin: 20px 0; }
                </style>
            </head>
            <body>
                <div class="success">✅ Tablas verificadas y creadas exitosamente</div>
                <div class="info">
                    <a href="/login">Ir al Login</a><br><br>
                    Usuarios disponibles:<br>
                    • admin / admin123 (Administrador)<br>
                    • chef / chef123 (Chef)<br>
                    • mozo / mozo123 (Mozo)<br>
                    • cajero / cajero123 (Cajero)
                </div>
            </body>
            </html>
            '''
        else:
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Error</title>
                <style>
                    body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                    .error { color: red; font-size: 24px; margin: 20px 0; }
                </style>
            </head>
            <body>
                <div class="error">❌ Error al verificar tablas</div>
            </body>
            </html>
            '''
    except Exception as e:
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; text-align: center; }}
                .error {{ color: red; font-size: 24px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="error">❌ Error: {str(e)}</div>
        </body>
        </html>
        '''

# ==============================
# PANEL DE CAJA (MEJORADO PARA RENDER)
# ==============================
@app.route("/caja")
@login_required
def caja():
    """Panel de caja"""
    usuario_actual = get_usuario_actual()
    
    # Solo cajeros y admins pueden acceder
    if usuario_actual['rol'] not in ['cajero', 'admin']:
        flash('Acceso restringido a caja', 'warning')
        return redirect(url_for('ordenes'))
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar si hay caja abierta
        cur.execute("SELECT id, fecha_apertura, monto_inicial FROM caja_turnos WHERE estado = 'abierta'")
        caja_abierta = cur.fetchone()
        
        if not caja_abierta:
            # Si no hay caja abierta, crear una automáticamente
            cur.execute('''
                INSERT INTO caja_turnos (fecha_apertura, monto_inicial, observaciones, estado)
                VALUES (NOW(), 0, 'Caja abierta automáticamente', 'abierta')
                RETURNING id, fecha_apertura, monto_inicial
            ''')
            caja_abierta = cur.fetchone()
            conn.commit()
            flash('Caja abierta automáticamente con monto inicial $0', 'info')
        
        caja_info = {
            'id': caja_abierta[0],
            'fecha_apertura': caja_abierta[1],
            'monto_inicial': float(caja_abierta[2]) if caja_abierta[2] else 0
        }
        
        # Obtener órdenes abiertas
        cur.execute('''
            SELECT o.id, m.numero as mesa_numero, o.mozo_nombre, o.total 
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            WHERE o.estado = 'abierta' 
            ORDER BY o.fecha_apertura DESC
        ''')
        ordenes_abiertas_db = cur.fetchall()
        
        ordenes_abiertas = []
        for o in ordenes_abiertas_db:
            ordenes_abiertas.append({
                'id': o[0],
                'mesa_numero': o[1],
                'mozo_nombre': o[2],
                'total': float(o[3]) if o[3] else 0
            })
        
        cur.close()
        conn.close()
        
        return render_template("caja.html", 
                             usuario=usuario_actual, 
                             ahora=datetime.now(),
                             turno_abierto=caja_info,
                             ordenes_abiertas=ordenes_abiertas)
        
    except Exception as e:
        print(f"Error en panel de caja: {e}")
        flash('Error al cargar panel de caja', 'danger')
        return redirect(url_for('index'))

# ==============================
# RUTAS PARA CHEF (SIN RESTRICCIÓN DE ROL PARA FACILITAR)
# ==============================
@app.route("/chef")
def chef():
    """Panel del chef"""
    usuario_dummy = {'nombre': 'Chef', 'rol': 'chef'}
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Obtener pedidos pendientes
    cur.execute('''
        SELECT o.id, m.numero as mesa_numero, o.mozo_nombre, 
               o.fecha_apertura, COUNT(oi.id) as items_pendientes
        FROM ordenes o 
        JOIN mesas m ON o.mesa_id = m.id 
        LEFT JOIN orden_items oi ON o.id = oi.orden_id AND oi.estado_item = 'pendiente'
        WHERE o.estado = 'abierta'
        GROUP BY o.id, m.numero, o.mozo_nombre, o.fecha_apertura
        ORDER BY o.fecha_apertura ASC
    ''')
    pedidos_db = cur.fetchall()
    
    pedidos = []
    for p in pedidos_db:
        pedidos.append({
            'id': p[0],
            'mesa_numero': p[1],
            'mozo_nombre': p[2],
            'fecha_apertura': p[3],
            'items_pendientes': p[4]
        })
    
    cur.close()
    conn.close()
    
    return render_template("chef.html",
                         usuario=usuario_dummy,
                         pedidos=pedidos,
                         ahora=datetime.now())

# ==============================
# RUTAS PARA MOZO
# ==============================
@app.route("/ordenes")
@login_required
def ordenes():
    """Panel principal del mozo"""
    usuario_actual = get_usuario_actual()
    
    # Solo mozos y admins pueden acceder
    if usuario_actual['rol'] not in ['mozo', 'admin']:
        flash('Acceso restringido a ordenes', 'warning')
        return redirect(url_for('caja'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM mesas ORDER BY numero')
    mesas = cur.fetchall()
    
    cur.execute('''
        SELECT o.*, m.numero as mesa_numero 
        FROM ordenes o 
        JOIN mesas m ON o.mesa_id = m.id 
        WHERE o.estado = 'abierta' 
        ORDER BY o.fecha_apertura DESC
    ''')
    ordenes_activas = cur.fetchall()
    
    mesas_list = []
    for mesa in mesas:
        mesas_list.append({
            'id': mesa[0],
            'numero': mesa[1],
            'capacidad': mesa[2],
            'estado': mesa[3]
        })
    
    ordenes_list = []
    for orden in ordenes_activas:
        ordenes_list.append({
            'id': orden[0],
            'mesa_id': orden[1],
            'mesa_numero': orden[9],
            'mozo_nombre': orden[2],
            'estado': orden[3],
            'total': float(orden[5]) if orden[5] else 0,
            'fecha_apertura': orden[6]
        })
    
    cur.close()
    conn.close()
    
    return render_template("ordenes.html", 
                         usuario=usuario_actual,
                         mesas=mesas_list,
                         ordenes=ordenes_list,
                         ahora=datetime.now())

# ==============================
# RUTAS PARA PRODUCTOS
# ==============================
@app.route("/productos")
@login_required
def productos():
    """Lista de productos"""
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('''
            SELECT p.id, p.nombre, p.precio, p.stock, p.tipo, p.codigo_barra,
                   c.nombre as categoria_nombre
            FROM productos p 
            LEFT JOIN categorias c ON p.categoria_id = c.id
            WHERE p.nombre ILIKE %s
            ORDER BY p.nombre
        ''', (f'%{search}%',))
    else:
        cur.execute('''
            SELECT p.id, p.nombre, p.precio, p.stock, p.tipo, p.codigo_barra,
                   c.nombre as categoria_nombre
            FROM productos p 
            LEFT JOIN categorias c ON p.categoria_id = c.id
            ORDER BY p.nombre
        ''')
    
    productos_db = cur.fetchall()
    
    cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
    categorias_db = cur.fetchall()
    
    productos_list = []
    for p in productos_db:
        productos_list.append({
            'id': p[0],
            'nombre': p[1],
            'precio': float(p[2]) if p[2] else 0.0,
            'stock': p[3] if p[3] is not None else 0,
            'tipo': p[4] if p[4] else 'producto',
            'codigo_barra': p[5] if p[5] else '',
            'categoria_nombre': p[6] if p[6] else 'Sin categoría'
        })
    
    cur.close()
    conn.close()
    
    return render_template("productos.html", 
                         usuario=usuario_actual,
                         productos=productos_list,
                         categorias=[{'id': c[0], 'nombre': c[1]} for c in categorias_db],
                         search=search,
                         ahora=datetime.now())

@app.route("/crear_producto", methods=["GET", "POST"])
@login_required
def crear_producto():
    """Crear nuevo producto"""
    usuario_actual = get_usuario_actual()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
    categorias = cur.fetchall()
    cur.execute('SELECT id, nombre FROM proveedores WHERE activo = true ORDER BY nombre')
    proveedores = cur.fetchall()
    cur.close()
    conn.close()
    
    tipos = [
        {'valor': 'comida', 'nombre': 'Comida (plato del menú)'},
        {'valor': 'bebida', 'nombre': 'Bebida (con stock)'},
        {'valor': 'producto', 'nombre': 'Producto/Insumo (con stock)'}
    ]
    
    if request.method == "POST":
        codigo_barra = request.form.get("codigo_barra", "").strip()
        nombre = request.form.get("nombre", "").strip()
        precio = request.form.get("precio", "0")
        stock = request.form.get("stock", "0")
        categoria_id = request.form.get("categoria_id")
        proveedor_id = request.form.get("proveedor_id")
        tipo = request.form.get("tipo", "producto")
        
        if not nombre or not precio:
            flash('Nombre y precio son requeridos', 'danger')
            return redirect(url_for('crear_producto'))
        
        try:
            precio_float = float(precio)
        except ValueError:
            flash('Precio debe ser un número válido', 'danger')
            return redirect(url_for('crear_producto'))
        
        if tipo == 'comida':
            stock_int = None
            if not codigo_barra:
                codigo_barra = f"COM{datetime.now().strftime('%Y%m%d%H%M%S')}"
        else:
            if not codigo_barra:
                flash('Código de barras requerido para productos y bebidas', 'danger')
                return redirect(url_for('crear_producto'))
            
            try:
                stock_int = int(stock) if stock else 0
            except ValueError:
                flash('Stock debe ser un número válido', 'danger')
                return redirect(url_for('crear_producto'))
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('''
                INSERT INTO productos (codigo_barra, nombre, precio, stock, categoria_id, proveedor_id, tipo) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (codigo_barra, nombre, precio_float, stock_int, 
                  categoria_id if categoria_id else None, 
                  proveedor_id if proveedor_id else None,
                  tipo))
            
            conn.commit()
            flash(f'Producto "{nombre}" creado exitosamente', 'success')
            return redirect(url_for('productos'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Error al crear producto: {str(e)}', 'danger')
            return redirect(url_for('crear_producto'))
        finally:
            cur.close()
            conn.close()
    
    return render_template("crear_producto.html",
                         usuario=usuario_actual,
                         categorias=[{'id': c[0], 'nombre': c[1]} for c in categorias],
                         proveedores=[{'id': p[0], 'nombre': p[1]} for p in proveedores],
                         tipos=tipos,
                         ahora=datetime.now())

@app.route("/editar_producto/<int:id>", methods=["GET", "POST"])
@login_required
def editar_producto(id):
    """Editar producto existente"""
    usuario_actual = get_usuario_actual()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "GET":
        cur.execute('SELECT * FROM productos WHERE id = %s', (id,))
        producto_db = cur.fetchone()
        
        if not producto_db:
            cur.close()
            conn.close()
            flash('Producto no encontrado', 'danger')
            return redirect(url_for('productos'))
        
        producto = {
            'id': producto_db[0],
            'codigo_barra': producto_db[1],
            'nombre': producto_db[2],
            'precio': float(producto_db[3]) if producto_db[3] else 0,
            'stock': producto_db[4],
            'categoria_id': producto_db[5],
            'proveedor_id': producto_db[6],
            'tipo': producto_db[7] if len(producto_db) > 7 else 'producto'
        }
        
        cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
        categorias = cur.fetchall()
        cur.execute('SELECT id, nombre FROM proveedores WHERE activo = true ORDER BY nombre')
        proveedores = cur.fetchall()
        cur.close()
        conn.close()
        
        tipos = [
            {'valor': 'comida', 'nombre': 'Comida (plato del menú)'},
            {'valor': 'bebida', 'nombre': 'Bebida (con stock)'},
            {'valor': 'producto', 'nombre': 'Producto/Insumo (con stock)'}
        ]
        
        return render_template("editar_producto.html",
                             usuario=usuario_actual,
                             producto=producto,
                             categorias=[{'id': c[0], 'nombre': c[1]} for c in categorias],
                             proveedores=[{'id': p[0], 'nombre': p[1]} for p in proveedores],
                             tipos=tipos,
                             ahora=datetime.now())
    
    if request.method == "POST":
        codigo_barra = request.form.get("codigo_barra", "").strip()
        nombre = request.form.get("nombre", "").strip()
        precio = request.form.get("precio", "0")
        stock = request.form.get("stock", "0")
        categoria_id = request.form.get("categoria_id")
        proveedor_id = request.form.get("proveedor_id")
        tipo = request.form.get("tipo", "producto")
        
        if not nombre or not precio:
            flash('Nombre y precio son requeridos', 'danger')
            return redirect(url_for('editar_producto', id=id))
        
        try:
            precio_float = float(precio)
        except ValueError:
            flash('Precio debe ser un número válido', 'danger')
            return redirect(url_for('editar_producto', id=id))
        
        if tipo == 'comida':
            stock_int = None
            if not codigo_barra:
                codigo_barra = None
        else:
            if not codigo_barra:
                flash('Código de barras requerido para productos y bebidas', 'danger')
                return redirect(url_for('editar_producto', id=id))
            
            try:
                stock_int = int(stock) if stock else 0
            except ValueError:
                flash('Stock debe ser un número válido', 'danger')
                return redirect(url_for('editar_producto', id=id))
        
        try:
            cur.execute('''
                UPDATE productos 
                SET codigo_barra = %s, nombre = %s, precio = %s, stock = %s, 
                    categoria_id = %s, proveedor_id = %s, tipo = %s
                WHERE id = %s
            ''', (codigo_barra, nombre, precio_float, stock_int,
                  categoria_id if categoria_id else None,
                  proveedor_id if proveedor_id else None,
                  tipo, id))
            
            conn.commit()
            flash(f'Producto "{nombre}" actualizado exitosamente', 'success')
            return redirect(url_for('productos'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Error al actualizar producto: {str(e)}', 'danger')
            return redirect(url_for('editar_producto', id=id))
        finally:
            cur.close()
            conn.close()

@app.route("/eliminar_producto/<int:id>")
@login_required
def eliminar_producto(id):
    """Eliminar producto"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Verificar si hay órdenes activas con este producto
        cur.execute('''
            SELECT COUNT(*) FROM orden_items oi
            JOIN ordenes o ON oi.orden_id = o.id
            WHERE oi.producto_id = %s AND o.estado = 'abierta'
        ''', (id,))
        
        if cur.fetchone()[0] > 0:
            flash('No se puede eliminar, el producto está en órdenes activas', 'danger')
            return redirect(url_for('productos'))
        
        cur.execute('SELECT nombre FROM productos WHERE id = %s', (id,))
        nombre = cur.fetchone()[0]
        
        cur.execute('DELETE FROM productos WHERE id = %s', (id,))
        conn.commit()
        
        flash(f'Producto "{nombre}" eliminado exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar producto: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('productos'))

# ==============================
# RUTAS PARA MESAS
# ==============================
@app.route("/mesas")
@login_required
def mesas():
    """Lista de mesas"""
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('SELECT * FROM mesas WHERE CAST(numero AS TEXT) ILIKE %s OR ubicacion ILIKE %s ORDER BY numero', (f'%{search}%', f'%{search}%'))
    else:
        cur.execute('SELECT * FROM mesas ORDER BY numero')
    
    mesas_db = cur.fetchall()
    cur.close()
    conn.close()
    
    mesas_list = []
    for mesa in mesas_db:
        mesas_list.append({
            'id': mesa[0],
            'numero': mesa[1],
            'capacidad': mesa[2],
            'estado': mesa[3],
            'ubicacion': mesa[4],
            'created_at': mesa[5]
        })
    
    return render_template("mesas.html",
                         usuario=usuario_actual,
                         mesas=mesas_list,
                         search=search,
                         ahora=datetime.now())

@app.route("/crear_mesa", methods=["GET", "POST"])
@login_required
def crear_mesa():
    """Crear nueva mesa"""
    usuario_actual = get_usuario_actual()
    
    if request.method == "POST":
        numero = request.form.get("numero")
        capacidad = request.form.get("capacidad", 4)
        ubicacion = request.form.get("ubicacion", "")
        
        if not numero:
            flash('Número de mesa requerido', 'danger')
            return redirect(url_for('crear_mesa'))
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('INSERT INTO mesas (numero, capacidad, ubicacion) VALUES (%s, %s, %s)', 
                       (numero, capacidad, ubicacion))
            conn.commit()
            flash(f'Mesa #{numero} creada exitosamente', 'success')
            return redirect(url_for('mesas'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Error al crear mesa: {str(e)}', 'danger')
            return redirect(url_for('crear_mesa'))
        finally:
            cur.close()
            conn.close()
    
    return render_template("crear_mesa.html", usuario=usuario_actual, ahora=datetime.now())

@app.route("/editar_mesa/<int:id>", methods=["GET", "POST"])
@login_required
def editar_mesa(id):
    """Editar mesa existente"""
    usuario_actual = get_usuario_actual()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "GET":
        cur.execute('SELECT * FROM mesas WHERE id = %s', (id,))
        mesa_db = cur.fetchone()
        
        if not mesa_db:
            cur.close()
            conn.close()
            flash('Mesa no encontrada', 'danger')
            return redirect(url_for('mesas'))
        
        mesa = {
            'id': mesa_db[0],
            'numero': mesa_db[1],
            'capacidad': mesa_db[2],
            'estado': mesa_db[3],
            'ubicacion': mesa_db[4]
        }
        
        cur.close()
        conn.close()
        
        return render_template("editar_mesa.html",
                             usuario=usuario_actual,
                             mesa=mesa,
                             ahora=datetime.now())
    
    if request.method == "POST":
        numero = request.form.get("numero")
        capacidad = request.form.get("capacidad", 4)
        ubicacion = request.form.get("ubicacion", "")
        estado = request.form.get("estado", "disponible")
        
        if not numero:
            flash('Número de mesa requerido', 'danger')
            return redirect(url_for('editar_mesa', id=id))
        
        try:
            cur.execute('''
                UPDATE mesas 
                SET numero = %s, capacidad = %s, ubicacion = %s, estado = %s
                WHERE id = %s
            ''', (numero, capacidad, ubicacion, estado, id))
            
            conn.commit()
            flash(f'Mesa #{numero} actualizada exitosamente', 'success')
            return redirect(url_for('mesas'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Error al actualizar mesa: {str(e)}', 'danger')
            return redirect(url_for('editar_mesa', id=id))
        finally:
            cur.close()
            conn.close()

@app.route("/eliminar_mesa/<int:id>")
@login_required
def eliminar_mesa(id):
    """Eliminar mesa"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Verificar si hay órdenes activas en la mesa
        cur.execute('SELECT COUNT(*) FROM ordenes WHERE mesa_id = %s AND estado = %s', (id, 'abierta'))
        
        if cur.fetchone()[0] > 0:
            flash('No se puede eliminar, la mesa tiene órdenes activas', 'danger')
            return redirect(url_for('mesas'))
        
        cur.execute('SELECT numero FROM mesas WHERE id = %s', (id,))
        numero = cur.fetchone()[0]
        
        cur.execute('DELETE FROM mesas WHERE id = %s', (id,))
        conn.commit()
        
        flash(f'Mesa #{numero} eliminada exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar mesa: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('mesas'))

# ==============================
# RUTAS PARA ÓRDENES
# ==============================
@app.route("/crear_orden/<int:mesa_id>")
@login_required
def crear_orden(mesa_id):
    """Crear nueva orden para una mesa"""
    usuario_actual = get_usuario_actual()
    
    tipo_filtro = request.args.get('filtro', 'todos')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Verificar que la mesa esté disponible
    cur.execute('SELECT * FROM mesas WHERE id = %s', (mesa_id,))
    mesa = cur.fetchone()
    
    if not mesa:
        flash('Mesa no encontrada', 'danger')
        return redirect(url_for('ordenes'))
    
    if mesa[3] != 'disponible':
        flash('La mesa no está disponible', 'warning')
        return redirect(url_for('ordenes'))
    
    # Obtener productos según el filtro
    if tipo_filtro == 'todos':
        cur.execute('SELECT * FROM productos ORDER BY tipo, nombre')
    else:
        cur.execute('SELECT * FROM productos WHERE tipo = %s ORDER BY nombre', (tipo_filtro,))
    
    productos_db = cur.fetchall()
    
    productos = []
    for p in productos_db:
        productos.append({
            'id': p[0],
            'nombre': p[2],
            'precio': float(p[3]) if p[3] else 0,
            'tipo': p[7] if len(p) > 7 else 'producto'
        })
    
    cur.close()
    conn.close()
    
    nombres_filtro = {
        'todos': 'Todos los Productos',
        'comida': 'Solo Comidas',
        'bebida': 'Solo Bebidas',
        'producto': 'Solo Productos'
    }
    
    return render_template("crear_orden.html",
                         usuario=usuario_actual,
                         mesa={'id': mesa[0], 'numero': mesa[1], 'capacidad': mesa[2]},
                         productos=productos,
                         tipo_filtro=tipo_filtro,
                         nombre_filtro=nombres_filtro.get(tipo_filtro, 'Todos'),
                         ahora=datetime.now())

@app.route("/api/crear_orden", methods=["POST"])
@login_required
def api_crear_orden():
    """API para crear orden"""
    try:
        data = request.get_json()
        mesa_id = data.get('mesa_id')
        items = data.get('items', [])
        observaciones = data.get('observaciones', '')
        
        if not mesa_id or not items:
            return jsonify({"success": False, "message": "Datos incompletos"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Calcular total
        total = sum(item['precio'] * item['cantidad'] for item in items)
        
        # Crear orden
        cur.execute('''
            INSERT INTO ordenes (mesa_id, mozo_nombre, total, observaciones)
            VALUES (%s, %s, %s, %s) RETURNING id
        ''', (mesa_id, session.get('nombre', 'Mozo'), total, observaciones))
        
        orden_id = cur.fetchone()[0]
        
        # Agregar items
        for item in items:
            cur.execute('''
                INSERT INTO orden_items (orden_id, producto_id, producto_nombre, cantidad, precio_unitario, observaciones)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (orden_id, item['id'], item['nombre'], item['cantidad'], item['precio'], item.get('obs', '')))
        
        # Actualizar estado de la mesa
        cur.execute('UPDATE mesas SET estado = %s WHERE id = %s', ('ocupada', mesa_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "orden_id": orden_id,
            "message": f"Orden #{orden_id} creada exitosamente"
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/ver_orden/<int:orden_id>")
@login_required
def ver_orden(orden_id):
    """Ver detalle de orden"""
    usuario_actual = get_usuario_actual()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        SELECT o.*, m.numero as mesa_numero 
        FROM ordenes o 
        JOIN mesas m ON o.mesa_id = m.id 
        WHERE o.id = %s
    ''', (orden_id,))
    orden_db = cur.fetchone()
    
    if not orden_db:
        flash('Orden no encontrada', 'danger')
        return redirect(url_for('ordenes'))
    
    orden = {
        'id': orden_db[0],
        'mesa_id': orden_db[1],
        'mesa_numero': orden_db[9],
        'mozo_nombre': orden_db[2],
        'estado': orden_db[3],
        'observaciones': orden_db[4],
        'total': float(orden_db[5]) if orden_db[5] else 0,
        'fecha_apertura': orden_db[6]
    }
    
    cur.execute('SELECT * FROM orden_items WHERE orden_id = %s ORDER BY id', (orden_id,))
    items_db = cur.fetchall()
    
    items = []
    for item in items_db:
        items.append({
            'id': item[0],
            'producto_nombre': item[3],
            'cantidad': item[4],
            'precio_unitario': float(item[5]) if item[5] else 0,
            'observaciones': item[6],
            'estado_item': item[7]
        })
    
    cur.close()
    conn.close()
    
    return render_template("ver_orden.html",
                         usuario=usuario_actual,
                         orden=orden,
                         items=items,
                         ahora=datetime.now())

@app.route("/cobrar_orden/<int:orden_id>", methods=["GET", "POST"])
@login_required
def cobrar_orden(orden_id):
    """Cobrar una orden"""
    if request.method == "POST":
        metodo_pago = request.form.get("metodo_pago", "Efectivo")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            # Obtener información de la orden
            cur.execute('SELECT total, mesa_id FROM ordenes WHERE id = %s', (orden_id,))
            orden_info = cur.fetchone()
            
            if not orden_info:
                flash('Orden no encontrada', 'danger')
                return redirect(url_for('ordenes'))
            
            total = orden_info[0]
            mesa_id = orden_info[1]
            
            # Cerrar orden
            cur.execute('''
                UPDATE ordenes 
                SET estado = 'cerrada', fecha_cierre = CURRENT_TIMESTAMP 
                WHERE id = %s
            ''', (orden_id,))
            
            # Liberar mesa
            cur.execute('UPDATE mesas SET estado = %s WHERE id = %s', ('disponible', mesa_id))
            
            conn.commit()
            
            flash(f'Orden #{orden_id} cobrada exitosamente - ${float(total):.2f}', 'success')
            return redirect(url_for('ordenes'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Error al cobrar orden: {str(e)}', 'danger')
            return redirect(url_for('ver_orden', orden_id=orden_id))
        finally:
            cur.close()
            conn.close()
    
    # GET request - mostrar formulario de cobro
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT total FROM ordenes WHERE id = %s', (orden_id,))
    total_db = cur.fetchone()
    
    cur.close()
    conn.close()
    
    if not total_db:
        flash('Orden no encontrada', 'danger')
        return redirect(url_for('ordenes'))
    
    total = float(total_db[0]) if total_db[0] else 0
    
    return render_template("cobrar_orden.html",
                         usuario=get_usuario_actual(),
                         orden_id=orden_id,
                         total=total,
                         ahora=datetime.now())

# ==============================
# RUTAS DE API
# ==============================
@app.route("/api/mesas_disponibles")
def api_mesas_disponibles():
    """API para obtener mesas disponibles"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT id, numero, capacidad FROM mesas WHERE estado = %s ORDER BY numero', ('disponible',))
        mesas_db = cur.fetchall()
        
        mesas = []
        for mesa in mesas_db:
            mesas.append({
                'id': mesa[0],
                'numero': mesa[1],
                'capacidad': mesa[2]
            })
        
        return jsonify(mesas)
    except Exception as e:
        print(f"Error obteniendo mesas disponibles: {e}")
        return jsonify([])
    finally:
        cur.close()
        conn.close()

@app.route("/api/marcar_listo/<int:item_id>")
def marcar_listo(item_id):
    """Marcar item como listo en cocina"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('UPDATE orden_items SET estado_item = %s WHERE id = %s', ('listo', item_id))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item marcado como listo"})
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/productos")
def api_productos():
    """API para obtener productos"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT id, nombre, precio, tipo FROM productos ORDER BY nombre')
        productos_db = cur.fetchall()
        
        productos = []
        for p in productos_db:
            productos.append({
                'id': p[0],
                'nombre': p[1],
                'precio': float(p[2]) if p[2] else 0,
                'tipo': p[3] if p[3] else 'producto'
            })
        
        return jsonify(productos)
    except Exception as e:
        print(f"Error en api_productos: {e}")
        return jsonify([])
    finally:
        cur.close()
        conn.close()

@app.route("/api/ordenes_activas")
def api_ordenes_activas():
    """API para obtener órdenes activas"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT o.id, m.numero as mesa_numero, o.mozo_nombre, o.total, o.estado
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            WHERE o.estado = 'abierta'
            ORDER BY o.fecha_apertura DESC
        ''')
        ordenes_db = cur.fetchall()
        
        ordenes = []
        for o in ordenes_db:
            ordenes.append({
                'id': o[0],
                'mesa_numero': o[1],
                'mozo_nombre': o[2],
                'total': float(o[3]) if o[3] else 0,
                'estado': o[4]
            })
        
        return jsonify(ordenes)
    except Exception as e:
        print(f"Error en api_ordenes_activas: {e}")
        return jsonify([])
    finally:
        cur.close()
        conn.close()

# ==============================
# RUTAS PARA PROVEEDORES
# ==============================
@app.route("/proveedores")
@login_required
def proveedores():
    """Lista de proveedores"""
    usuario_actual = get_usuario_actual()
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM proveedores ORDER BY nombre')
    proveedores_db = cur.fetchall()
    
    cur.close()
    conn.close()
    
    proveedores_list = []
    for prov in proveedores_db:
        proveedores_list.append({
            'id': prov[0],
            'nombre': prov[1],
            'contacto': prov[2],
            'telefono': prov[3],
            'email': prov[4],
            'direccion': prov[5],
            'activo': prov[6],
            'created_at': prov[7]
        })
    
    return render_template("proveedores.html",
                         usuario=usuario_actual,
                         proveedores=proveedores_list,
                         ahora=datetime.now())

@app.route("/crear_proveedor", methods=["GET", "POST"])
@login_required
def crear_proveedor():
    """Crear nuevo proveedor"""
    usuario_actual = get_usuario_actual()
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        contacto = request.form.get("contacto", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip()
        direccion = request.form.get("direccion", "").strip()
        
        if not nombre:
            flash('Nombre del proveedor es requerido', 'danger')
            return redirect(url_for('crear_proveedor'))
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('''
                INSERT INTO proveedores (nombre, contacto, telefono, email, direccion) 
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            ''', (nombre, contacto if contacto else None, telefono if telefono else None, 
                  email if email else None, direccion if direccion else None))
            
            proveedor_id = cur.fetchone()[0]
            conn.commit()
            
            flash(f'Proveedor "{nombre}" creado exitosamente', 'success')
            return redirect(url_for('proveedores'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Error al crear proveedor: {str(e)}', 'danger')
            return redirect(url_for('crear_proveedor'))
        finally:
            cur.close()
            conn.close()
    
    return render_template("crear_proveedor.html",
                         usuario=usuario_actual,
                         ahora=datetime.now())

@app.route("/editar_proveedor/<int:id>", methods=["GET", "POST"])
@login_required
def editar_proveedor(id):
    """Editar proveedor existente"""
    usuario_actual = get_usuario_actual()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == "GET":
        cur.execute('SELECT * FROM proveedores WHERE id = %s', (id,))
        proveedor_db = cur.fetchone()
        
        if not proveedor_db:
            cur.close()
            conn.close()
            flash('Proveedor no encontrado', 'danger')
            return redirect(url_for('proveedores'))
        
        proveedor = {
            'id': proveedor_db[0],
            'nombre': proveedor_db[1],
            'contacto': proveedor_db[2] if proveedor_db[2] else '',
            'telefono': proveedor_db[3] if proveedor_db[3] else '',
            'email': proveedor_db[4] if proveedor_db[4] else '',
            'direccion': proveedor_db[5] if proveedor_db[5] else '',
            'activo': proveedor_db[6]
        }
        
        cur.close()
        conn.close()
        
        return render_template("crear_proveedor.html",
                             usuario=usuario_actual,
                             proveedor=proveedor,
                             ahora=datetime.now())
    
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        contacto = request.form.get("contacto", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip()
        direccion = request.form.get("direccion", "").strip()
        activo = request.form.get("activo") == 'true'
        
        if not nombre:
            flash('Nombre del proveedor es requerido', 'danger')
            return redirect(url_for('editar_proveedor', id=id))
        
        try:
            cur.execute('''
                UPDATE proveedores 
                SET nombre = %s, contacto = %s, telefono = %s, email = %s, 
                    direccion = %s, activo = %s
                WHERE id = %s
            ''', (nombre, contacto if contacto else None, telefono if telefono else None,
                  email if email else None, direccion if direccion else None, activo, id))
            
            conn.commit()
            flash(f'Proveedor "{nombre}" actualizado exitosamente', 'success')
            return redirect(url_for('proveedores'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Error al actualizar proveedor: {str(e)}', 'danger')
            return redirect(url_for('editar_proveedor', id=id))
        finally:
            cur.close()
            conn.close()

@app.route("/eliminar_proveedor/<int:id>")
@login_required
def eliminar_proveedor(id):
    """Eliminar proveedor"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Verificar si hay productos asociados al proveedor
        cur.execute('SELECT COUNT(*) FROM productos WHERE proveedor_id = %s', (id,))
        
        if cur.fetchone()[0] > 0:
            flash('No se puede eliminar, hay productos asociados a este proveedor', 'danger')
            return redirect(url_for('proveedores'))
        
        cur.execute('SELECT nombre FROM proveedores WHERE id = %s', (id,))
        nombre = cur.fetchone()[0]
        
        cur.execute('DELETE FROM proveedores WHERE id = %s', (id,))
        conn.commit()
        
        flash(f'Proveedor "{nombre}" eliminado exitosamente', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Error al eliminar proveedor: {str(e)}', 'danger')
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('proveedores'))

# ==============================
# RUTAS PARA CATEGORÍAS
# ==============================
@app.route("/categorias")
@login_required
def categorias():
    """Lista de categorías"""
    usuario_actual = get_usuario_actual()
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM categorias ORDER BY nombre')
    categorias_db = cur.fetchall()
    
    cur.close()
    conn.close()
    
    categorias_list = []
    for cat in categorias_db:
        categorias_list.append({
            'id': cat[0],
            'nombre': cat[1],
            'created_at': cat[2]
        })
    
    return render_template("categorias.html",
                         usuario=usuario_actual,
                         categorias=categorias_list,
                         ahora=datetime.now())

@app.route("/crear_categoria", methods=["POST"])
@login_required
def crear_categoria():
    """Crear nueva categoría (API)"""
    try:
        nombre = request.form.get("nombre", "").strip().upper()
        
        if not nombre:
            return jsonify({"success": False, "message": "Nombre requerido"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('INSERT INTO categorias (nombre) VALUES (%s) RETURNING id', (nombre,))
        categoria_id = cur.fetchone()[0]
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "id": categoria_id,
            "nombre": nombre,
            "message": f"Categoría '{nombre}' creada exitosamente"
        })
        
    except Exception as e:
        if "unique" in str(e).lower():
            return jsonify({"success": False, "message": "La categoría ya existe"}), 400
        return jsonify({"success": False, "message": str(e)}), 500

# ==============================
# RUTAS PARA ESTADÍSTICAS
# ==============================
@app.route("/estadisticas")
@login_required
def estadisticas():
    """Panel de estadísticas"""
    usuario_actual = get_usuario_actual()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Ventas del día
    cur.execute('''
        SELECT COUNT(*) as cantidad, COALESCE(SUM(total), 0) as total
        FROM ordenes 
        WHERE estado = 'cerrada' 
        AND DATE(fecha_cierre) = CURRENT_DATE
    ''')
    ventas_hoy = cur.fetchone()
    
    # Ventas del mes
    cur.execute('''
        SELECT COUNT(*) as cantidad, COALESCE(SUM(total), 0) as total
        FROM ordenes 
        WHERE estado = 'cerrada' 
        AND EXTRACT(MONTH FROM fecha_cierre) = EXTRACT(MONTH FROM CURRENT_DATE)
        AND EXTRACT(YEAR FROM fecha_cierre) = EXTRACT(YEAR FROM CURRENT_DATE)
    ''')
    ventas_mes = cur.fetchone()
    
    # Productos más vendidos
    cur.execute('''
        SELECT oi.producto_nombre, 
               SUM(oi.cantidad) as cantidad_total,
               COUNT(DISTINCT oi.orden_id) as ordenes_count
        FROM orden_items oi
        JOIN ordenes o ON oi.orden_id = o.id
        WHERE o.estado = 'cerrada'
        GROUP BY oi.producto_nombre
        ORDER BY cantidad_total DESC
        LIMIT 10
    ''')
    top_productos = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template("estadisticas.html",
                         usuario=usuario_actual,
                         ventas_hoy={
                             'cantidad': ventas_hoy[0] if ventas_hoy else 0,
                             'total': float(ventas_hoy[1]) if ventas_hoy and ventas_hoy[1] else 0
                         },
                         ventas_mes={
                             'cantidad': ventas_mes[0] if ventas_mes else 0,
                             'total': float(ventas_mes[1]) if ventas_mes and ventas_mes[1] else 0
                         },
                         top_productos=[{
                             'nombre': p[0],
                             'cantidad': p[1],
                             'ordenes': p[2]
                         } for p in top_productos],
                         ahora=datetime.now())

# ==============================
# LOGOUT
# ==============================
@app.route("/logout")
def logout():
    """Cerrar sesión"""
    session.clear()
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('login'))

# ==============================
# MANEJO DE ERRORES
# ==============================
@app.errorhandler(404)
def pagina_no_encontrada(e):
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Página no encontrada</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #666; }
            a { color: #3498db; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>404 - Página no encontrada</h1>
        <p>La página que buscas no existe.</p>
        <p><a href="/">Volver al inicio</a></p>
    </body>
    </html>
    ''', 404

@app.errorhandler(500)
def error_servidor(e):
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Error del servidor</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #e74c3c; }
            a { color: #3498db; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>500 - Error del servidor</h1>
        <p>Algo salió mal. Por favor, intenta nuevamente más tarde.</p>
        <p><a href="/">Volver al inicio</a></p>
    </body>
    </html>
    ''', 500

# ==============================
# EJECUCIÓN PRINCIPAL (ADAPTADA PARA RENDER)
# ==============================
if __name__ == "__main__":
    # Obtener el puerto de Render o usar 5000 por defecto
    port = int(os.environ.get("PORT", 5000))
    
    # En Render, necesitamos ejecutar en el host 0.0.0.0
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False  # En producción, debug debe ser False
    )
