import os
import logging
from flask import Flask, render_template
from contextlib import contextmanager
import psycopg2
import psycopg2.extras
from psycopg2 import pool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Database connection configuration from environment variables
DB_USER = os.getenv('DB_USER', 'myuser')
DB_PASS = os.getenv('DB_PASS', 'mypass')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'dbname')

# Connection pool configuration
minConnection = 2
maxConnection = 10

try:
    connectionPool = psycopg2.pool.ThreadedConnectionPool(
        minConnection, maxConnection,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME
    )
    logger.info("Connection pool created successfully")
except Exception as e:
    logger.error(f"Failed to create connection pool: {e}")
    connectionPool = None


@contextmanager
def get_connection():
    """
    Acquire a connection from the pool and ensure it's returned.

    Yields:
        psycopg2.connection: Database connection from the pool.
    """
    if connectionPool is None:
        raise Exception("Database connection pool is not initialized")

    conn = connectionPool.getconn()
    try:
        yield conn
    finally:
        connectionPool.putconn(conn)


def load_printers():
    """
    Load all printers from the database.

    Returns:
        list: List of printer records as dictionaries.
    """
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    'SELECT printer_id, unique_id, is_active, printer_name, '
                    'inserted, tag '
                    'FROM printers '
                    'ORDER BY printer_id'
                )
                rows = cur.fetchall()
                logger.info(f"Loaded {len(rows)} printers from database")
                return rows
    except Exception as e:
        logger.error(f"Error loading printers: {e}")
        return []


@app.route('/')
def home_page():
    """
    Main page displaying the list of printers from the database.

    Returns:
        str: Rendered HTML template with printer data.
    """
    printers = load_printers()
    db_info = {
        'host': DB_HOST,
        'database': DB_NAME,
        'user': DB_USER
    }
    return render_template('index.html', printers=printers, db_info=db_info)


@app.route('/health')
def health_check():
    """
    Health check endpoint to verify application status.

    Returns:
        dict: Health status information.
    """
    status = 'healthy'
    db_status = 'connected'

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        status = 'unhealthy'
        db_status = f'error: {str(e)}'

    return {
        'status': status,
        'database': db_status,
        'db_host': DB_HOST
    }


@app.errorhandler(404)
def page_not_found(e):
    """
    Handle 404 errors.

    Args:
        e: Error object.

    Returns:
        tuple: Error message and status code.
    """
    return "Page not found", 404


@app.errorhandler(500)
def internal_server_error(e):
    """
    Handle 500 errors.

    Args:
        e: Error object.

    Returns:
        tuple: Error message and status code.
    """
    logger.error(f"Internal server error: {e}")
    return "Internal server error", 500


# Uncomment this line for running in Development environment
# i.e. not with Gunicorn
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
