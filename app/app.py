import os
import logging
from flask import Flask, render_template
from contextlib import contextmanager
import psycopg2
import psycopg2.extras
from psycopg2 import pool, OperationalError

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
DB_USER = os.getenv('DB_USER', 'uuuu')
DB_PASS = os.getenv('DB_PASS', 'ppppppp')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'ddd')

# Connection pool configuration
minConnection = 2
maxConnection = 10

# Global connection pool variable
connectionPool = None


def create_connection_pool():
    """
    Create a new connection pool.

    Returns:
        psycopg2.pool.ThreadedConnectionPool: Connection pool or None on failure.
    """
    try:
        pool_instance = psycopg2.pool.ThreadedConnectionPool(
            minConnection, maxConnection,
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME
        )
        logger.info("Connection pool created successfully")
        return pool_instance
    except Exception as e:
        logger.error(f"Failed to create connection pool: {e}")
        return None


def reinit_connection_pool():
    """
    Reinitialize the connection pool by closing all connections and creating a new pool.
    """
    global connectionPool

    try:
        if connectionPool:
            logger.info("Closing existing connection pool...")
            connectionPool.closeall()
    except Exception as e:
        logger.warning(f"Error while closing old pool: {e}")

    connectionPool = create_connection_pool()
    return connectionPool is not None


# Initialize connection pool on startup
connectionPool = create_connection_pool()


def validate_connection(conn):
    """
    Validate that a connection is still alive by executing a simple query.

    Args:
        conn: Database connection to validate.

    Returns:
        bool: True if connection is valid, False otherwise.
    """
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
        return True
    except (OperationalError, psycopg2.InterfaceError) as e:
        logger.warning(f"Connection validation failed: {e}")
        return False


@contextmanager
def get_connection(max_retries=3):
    """
    Acquire a connection from the pool with automatic reconnection on failure.

    Args:
        max_retries (int): Maximum number of retry attempts.

    Yields:
        psycopg2.connection: Database connection from the pool.
    """
    global connectionPool

    if connectionPool is None:
        logger.warning("Connection pool is not initialized, attempting to create...")
        if not reinit_connection_pool():
            raise Exception("Database connection pool is not available")

    conn = None
    last_exception = None

    for attempt in range(max_retries):
        try:
            conn = connectionPool.getconn()

            # Validate the connection before using it
            if not validate_connection(conn):
                logger.warning(f"Connection is dead, discarding and retrying (attempt {attempt + 1}/{max_retries})")
                connectionPool.putconn(conn, close=True)  # Close the bad connection

                # If this was the last attempt, try to reinitialize the pool
                if attempt == max_retries - 1:
                    logger.info("Reinitializing connection pool...")
                    if reinit_connection_pool():
                        conn = connectionPool.getconn()
                    else:
                        raise Exception("Failed to reinitialize connection pool")
                else:
                    continue

            # Connection is valid, use it
            yield conn
            connectionPool.putconn(conn)
            return

        except (OperationalError, psycopg2.InterfaceError) as e:
            last_exception = e
            logger.error(f"Connection error (attempt {attempt + 1}/{max_retries}): {e}")

            if conn:
                try:
                    connectionPool.putconn(conn, close=True)
                except:
                    pass

            # Try to reinitialize pool on last attempt
            if attempt == max_retries - 1:
                logger.info("Final attempt: reinitializing connection pool...")
                if not reinit_connection_pool():
                    raise Exception("Failed to restore database connection") from last_exception
        except Exception as e:
            last_exception = e
            logger.error(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")
            if conn:
                try:
                    connectionPool.putconn(conn)
                except:
                    pass
            raise

    if last_exception:
        raise last_exception


def load_printers():
    """
    Load all printers from the database with automatic reconnection on failure.

    Returns:
        list: List of printer records as dictionaries.
    """
    max_attempts = 3
    last_error = None

    for attempt in range(max_attempts):
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
            last_error = e
            logger.error(f"Error loading printers (attempt {attempt + 1}/{max_attempts}): {e}")
            if attempt < max_attempts - 1:
                logger.info("Retrying after connection error...")
                continue

    logger.error(f"Failed to load printers after {max_attempts} attempts")
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
    Health check endpoint to verify application status with reconnection support.

    Returns:
        dict: Health status information.
    """
    status = 'healthy'
    db_status = 'connected'

    max_attempts = 2

    for attempt in range(max_attempts):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT 1')
                    break  # Success
        except Exception as e:
            logger.error(f"Health check failed (attempt {attempt + 1}/{max_attempts}): {e}")
            status = 'unhealthy'
            db_status = f'error: {str(e)}'
            if attempt < max_attempts - 1:
                continue

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
