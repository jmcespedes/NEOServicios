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
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT region_id, comuna_id, servicio_id, celular, paso_actual, pregunta_cliente
                FROM sesiones_servicios
                WHERE session_id = %s
            """, (session_id,))
            row = cur.fetchone()
            if row:
                return {
                    'region_id': row[0],
                    'comuna_id': row[1],
                    'servicio_id': row[2],
                    'celular': row[3],
                    'paso_actual': row[4],
                    'pregunta_cliente': row[5]
                }
            else:
                return None
    except Exception as e:
        print(f"Error al obtener sesión: {e}")
        return None
    finally:
        conn.close()

def actualizar_sesion(session_id, **kwargs):
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            set_clause = ", ".join([f"{k} = %s" for k in kwargs.keys()])
            values = list(kwargs.values()) + [session_id]
            cur.execute(f"""
                UPDATE sesiones_servicios
                SET {set_clause}, fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE session_id = %s
                RETURNING id
            """, values)
            return cur.fetchone()[0]
    except Exception as e:
        print(f"Error al actualizar sesión: {e}")
        return None
    finally:
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
            return cur.fetchall()
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
