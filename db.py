import os
import psycopg2
##from dotenv import load_dotenv
import random

##load_dotenv()

db_config = {
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASS')
}

def get_db_connection():
    try:
        conn = psycopg2.connect(**db_config)
        conn.autocommit = True
        return conn
    except Exception as e:
        print(f"Error de conexión a la base de datos: {e}")
        return None

def crear_sesion():
    import uuid
    session_id = str(uuid.uuid4())
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sesiones_servicios (session_id, paso_actual)
                VALUES (%s, %s)
                RETURNING id
            """, (session_id, 'espera_comuna_region'))
            session_db_id = cur.fetchone()[0]
            return {'session_id': session_id, 'db_id': session_db_id}
    except Exception as e:
        print(f"Error al crear sesión: {e}")
        return None
    finally:
        conn.close()

def obtener_datos_sesion(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT session_id, comuna_id, region_id, servicio_id, pregunta_cliente, celular, paso_actual, codigo_verificacion
        FROM sesiones_servicios
        WHERE session_id = %s
    """, (session_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        return None
    return {
        'session_id': row[0],
        'comuna_id': row[1],
        'region_id': row[2],
        'servicio_id': row[3],
        'pregunta_cliente': row[4],
        'celular': row[5],
        'paso_actual': row[6],
        'codigo_verificacion': row[7]
    }

def actualizar_sesion(session_id, comuna_id=None, region_id=None, servicio_id=None, pregunta_cliente=None, celular=None, paso_actual=None, codigo_verificacion=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    update_fields = []
    params = []

    if comuna_id is not None:
        update_fields.append("comuna_id = %s")
        params.append(comuna_id)

    if region_id is not None:
        update_fields.append("region_id = %s")
        params.append(region_id)

    if servicio_id is not None:
        update_fields.append("servicio_id = %s")
        params.append(servicio_id)

    if pregunta_cliente is not None:
        update_fields.append("pregunta_cliente = %s")
        params.append(pregunta_cliente)

    if celular is not None:
        update_fields.append("celular = %s")
        params.append(celular)

    if paso_actual is not None:
        update_fields.append("paso_actual = %s")
        params.append(paso_actual)

    if codigo_verificacion is not None:
        update_fields.append("codigo_verificacion = %s")
        params.append(codigo_verificacion)

    if update_fields:
        query = f"UPDATE sesiones_servicios SET {', '.join(update_fields)} WHERE session_id = %s"        
        params.append(session_id)
        cursor.execute(query, params)
        conn.commit()

    cursor.close()
    conn.close()

def get_comunas_con_region(nombre_comuna):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                        SELECT c.id, c.nombre, r.id, r.nombre 
                        FROM comunas c
                        JOIN regiones r ON c.region_id = r.id
                        WHERE c.nombre ILIKE %s
                    """, (f"%{nombre_comuna}%",))
            return cur.fetchall()
    except Exception as e:
        print(f"Error en consulta de comunas: {e}")
        return []
    finally:
        conn.close()
ADOPCION_ID = 9999

def get_servicios_por_comuna(comuna_nombre):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT id, servicios
            FROM proveedores
            WHERE LOWER(comuna) LIKE %s
        """, (f"%{comuna_nombre.lower()}%",))
            proveedores = cur.fetchall()

            servicios_set = set()
            for prov in proveedores:
                servicios_texto = prov[1]  # campo servicios
                # Suponiendo que servicios_texto es string con servicios separados por coma
                servicios_list = [s.strip().lower() for s in servicios_texto.split(',')]
                servicios_set.update(servicios_list)

            servicios = list(servicios_set)

            # Insertar "adopción de mascotas" si no está
            if 'adopción de mascotas' not in servicios:
                servicios = ['adopción de mascotas'] + servicios

            # Construir lista con ids ficticios o nombres
            servicios_lista = []
            for s in servicios:
                if s == 'adopción de mascotas':
                    servicios_lista.append((9999, s))
                else:
                    servicios_lista.append((None, s))  # o asigna id real si tienes

            return servicios_lista

    except Exception as e:
        print(f"Error en consulta de servicios: {e}")
        return []
    finally:
        conn.close()


def buscar_servicios_por_comuna_y_texto(comuna_nombre, texto_parcial):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT servicios FROM proveedores
                WHERE LOWER(comuna) LIKE %s AND LOWER(servicios) LIKE %s
                LIMIT 30
            """, (f"%{comuna_nombre}%", f"%{texto_parcial}%"))
            filas = cur.fetchall()
    except Exception as e:
        print(f"Error buscando servicios: {e}")
        return []
    finally:
        conn.close()

    servicios_unicos = set()
    for fila in filas:
        servicios = [s.strip() for s in fila[0].split(",")]
        for servicio in servicios:
            if texto_parcial in servicio.lower():
                servicios_unicos.add(servicio)

    return list(servicios_unicos)

def generar_codigo_verificacion():
    return f"{random.randint(1000, 9999)}"
