import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()  # Cargar variables desde el archivo .env

# Configuración de la base de datos usando variables de entorno
db_config = {
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

def get_db_connection():
    try:
        conn = psycopg2.connect(**db_config)
        conn.autocommit = True  # Esto asegura que las consultas de actualización se realicen de inmediato
        return conn
    except Exception as e:
        print(f"Error de conexión a la base de datos: {e}")
        return None

def ejecutar_consulta(query, params=None):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

