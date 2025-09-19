from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import os
from datetime import datetime
import uuid
from typing import List, Optional
import mysql.connector
from mysql.connector import Error
import shutil
from pathlib import Path
import urllib.parse
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = FastAPI(title="Photo Picker API", version="1.0.0")

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de base de datos mejorada para MySQL Workbench
def get_db_config():
    # Para desarrollo local con MySQL Workbench
    return {
        'host': os.getenv('DB_HOST', '127.0.0.1'),
        'database': os.getenv('DB_NAME', 'photo_picker_db'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'port': int(os.getenv('DB_PORT', 3377)),
        'charset': 'utf8mb4',
        'collation': 'utf8mb4_unicode_ci',
        'autocommit': True
    }

DB_CONFIG = get_db_config()

# Directorio para uploads
UPLOAD_DIR = os.getenv('UPLOAD_DIR', 'uploads')
Path(UPLOAD_DIR).mkdir(exist_ok=True)

# Función de conexión a BD con reintentos y verificación mejorada
def get_db_connection(max_retries=3, delay=2):
    import time
    for attempt in range(max_retries):
        try:
            connection = mysql.connector.connect(**DB_CONFIG)
            print(f"✅ Database connection successful (attempt {attempt + 1})")
            
            # Verificar que la base de datos existe
            cursor = connection.cursor()
            cursor.execute("SHOW DATABASES LIKE %s", (DB_CONFIG['database'],))
            result = cursor.fetchone()
            
            if not result:
                print(f"❌ Database '{DB_CONFIG['database']}' does not exist")
                connection.close()
                return None
                
            print(f"✅ Database '{DB_CONFIG['database']}' exists")
            return connection
        except Error as e:
            print(f"❌ Database connection failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                print("❌ Max retries reached, could not connect to database")
                return None

# Crear tabla con verificación mejorada
def create_table():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            
            # Seleccionar la base de datos
            cursor.execute(f"USE {DB_CONFIG['database']}")
            
            # Verificar si la tabla ya existe
            cursor.execute("SHOW TABLES LIKE 'images'")
            table_exists = cursor.fetchone()
            
            if table_exists:
                print("✅ Table 'images' already exists")
                
                # Verificar la estructura de la tabla
                cursor.execute("DESCRIBE images")
                columns = cursor.fetchall()
                print("📋 Table structure:")
                for column in columns:
                    print(f"  - {column[0]}: {column[1]}")
            else:
                # Crear la tabla si no existe
                cursor.execute("""
                    CREATE TABLE images (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        image_id VARCHAR(36) NOT NULL UNIQUE,
                        filename VARCHAR(255) NOT NULL,
                        filepath VARCHAR(500) NOT NULL,
                        description TEXT,
                        upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                        file_size BIGINT,
                        mime_type VARCHAR(100),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """)
                connection.commit()
                print("✅ Table 'images' created successfully")
            
            # Verificar si la tabla tiene datos
            cursor.execute("SELECT COUNT(*) as count FROM images")
            result = cursor.fetchone()
            print(f"📊 Total images in database: {result[0]}")
            
        except Error as e:
            print(f"❌ Error creating/verifying table: {e}")
        finally:
            connection.close()
    else:
        print("⚠️  Could not create table - no database connection")

# Verificar conexión al iniciar
print("🔍 Attempting to connect to database...")
print(f"📋 Connection parameters: {DB_CONFIG}")

# Intentar crear tabla al iniciar (con reintentos)
import time
time.sleep(2)  # Esperar para que la BD esté lista
create_table()

@app.get("/")
async def root():
    return {
        "message": "Photo Picker API is running!",
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "database_config": {
            "host": DB_CONFIG['host'],
            "database": DB_CONFIG['database'],
            "port": DB_CONFIG['port'],
            "user": DB_CONFIG['user']
        },
        "environment": "development"
    }

@app.post("/upload")
async def upload_image(
    image: UploadFile = File(...),
    description: Optional[str] = Form("")
):
    try:
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")

        image_id = str(uuid.uuid4())
        file_extension = os.path.splitext(image.filename)[1] or ".jpg"
        filename = f"{image_id}{file_extension}"
        filepath = os.path.join(UPLOAD_DIR, filename)

        # Guardar archivo
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        file_size = os.path.getsize(filepath)

        # Insertar en BD
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("""
                    INSERT INTO images (image_id, filename, filepath, description, file_size, mime_type)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (image_id, filename, filepath, description, file_size, image.content_type))
                connection.commit()
            except Error as e:
                os.remove(filepath)
                raise HTTPException(status_code=500, detail=f"Database error: {e}")
            finally:
                connection.close()
        else:
            raise HTTPException(status_code=500, detail="Database connection failed")

        # Generar URL
        base_url = 'http://localhost:8000'
        image_url = f"{base_url}/images/{filename}"

        return JSONResponse({
            "success": True,
            "message": "Image uploaded successfully",
            "imageId": image_id,
            "imageUrl": image_url,
            "filename": filename
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/images")
async def get_all_images():
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT image_id, filename, description, upload_date, file_size, mime_type
                FROM images ORDER BY upload_date DESC
            """)
            images = cursor.fetchall()
            connection.close()

            # Determinar base URL
            base_url = 'http://localhost:8000'

            result = [{
                "id": img['image_id'],
                "url": f"{base_url}/images/{img['filename']}",
                "description": img['description'] or "",
                "uploadDate": img['upload_date'].isoformat() if img['upload_date'] else "",
                "fileSize": img['file_size'],
                "mimeType": img['mime_type']
            } for img in images]

            return {"success": True, "images": result}
        else:
            return {"success": False, "images": [], "error": "Database connection failed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/images/{filename}")
async def get_image(filename: str):
    filepath = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(filepath):
        return FileResponse(filepath)
    raise HTTPException(status_code=404, detail="Image not found")

@app.get("/health")
async def health_check():
    connection = get_db_connection()
    db_status = "connected" if connection else "disconnected"
    if connection:
        connection.close()
    
    upload_dir_exists = os.path.exists(UPLOAD_DIR)
    upload_dir_writable = os.access(UPLOAD_DIR, os.W_OK)
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database": db_status,
        "upload_directory": {
            "exists": upload_dir_exists,
            "writable": upload_dir_writable,
            "path": UPLOAD_DIR
        },
        "database_config": {
            "host": DB_CONFIG['host'],
            "database": DB_CONFIG['database'],
            "port": DB_CONFIG['port'],
            "user": DB_CONFIG['user']
        }
    }

@app.get("/db-info")
async def db_info():
    """Endpoint para obtener información detallada de la base de datos"""
    connection = get_db_connection()
    if not connection:
        return {"success": False, "error": "No database connection"}
    
    try:
        cursor = connection.cursor(dictionary=True)
        
        # Información de la base de datos
        cursor.execute("SELECT DATABASE() as db_name")
        db_name = cursor.fetchone()
        
        # Información de las tablas
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        # Información de la tabla images
        cursor.execute("DESCRIBE images")
        columns = cursor.fetchall()
        
        # Contar registros
        cursor.execute("SELECT COUNT(*) as count FROM images")
        count = cursor.fetchone()
        
        return {
            "success": True,
            "database": db_name['db_name'],
            "tables": [table for table in tables],
            "images_table_columns": columns,
            "total_images": count['count']
        }
        
    except Error as e:
        return {"success": False, "error": str(e)}
    finally:
        connection.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)