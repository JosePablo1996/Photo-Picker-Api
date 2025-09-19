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

# Configuración de base de datos mejorada
def get_db_config():
    # Para Render con ClearDB MySQL
    if os.environ.get('RENDER'):
        database_url = os.environ.get('CLEARDB_DATABASE_URL', '')
        if database_url:
            try:
                url = urllib.parse.urlparse(database_url)
                return {
                    'host': url.hostname,
                    'database': url.path[1:],
                    'user': url.username,
                    'password': url.password,
                    'port': url.port or 3306
                }
            except:
                pass
    
    # Para Docker con MySQL
    if os.environ.get('DOCKER_ENV'):
        return {
            'host': os.getenv('DB_HOST', 'mysql'),
            'database': os.getenv('DB_NAME', 'photo_picker_db'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', 'password'),
            'port': int(os.getenv('DB_PORT', 3306))
        }
    
    # Para desarrollo local
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'photo_picker_db'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'port': int(os.getenv('DB_PORT', 3377))
    }

DB_CONFIG = get_db_config()

# Directorio para uploads (compatible con Docker y Render)
UPLOAD_DIR = os.getenv('UPLOAD_DIR', '/app/uploads' if os.environ.get('DOCKER_ENV') else 'uploads')
Path(UPLOAD_DIR).mkdir(exist_ok=True)

# Función de conexión a BD con reintentos
def get_db_connection(max_retries=3, delay=2):
    import time
    for attempt in range(max_retries):
        try:
            connection = mysql.connector.connect(**DB_CONFIG)
            print(f"✅ Database connection successful (attempt {attempt + 1})")
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS images (
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
            print("✅ Table created successfully or already exists")
            
            # Verificar si la tabla tiene datos
            cursor.execute("SELECT COUNT(*) as count FROM images")
            result = cursor.fetchone()
            print(f"📊 Total images in database: {result[0]}")
            
        except Error as e:
            print(f"❌ Error creating table: {e}")
        finally:
            connection.close()
    else:
        print("⚠️  Could not create table - no database connection")

# Intentar crear tabla al iniciar (con reintentos)
import time
time.sleep(2)  # Esperar para que la BD esté lista en Docker
create_table()

@app.get("/")
async def root():
    return {
        "message": "Photo Picker API is running!",
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "environment": "docker" if os.environ.get('DOCKER_ENV') else "render" if os.environ.get('RENDER') else "development"
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
        if os.environ.get('RENDER'):
            base_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:8000')
        elif os.environ.get('DOCKER_ENV'):
            base_url = os.environ.get('DOCKER_HOST', 'http://localhost:8000')
        else:
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
            if os.environ.get('RENDER'):
                base_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:8000')
            elif os.environ.get('DOCKER_ENV'):
                base_url = os.environ.get('DOCKER_HOST', 'http://localhost:8000')
            else:
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
        "environment": "docker" if os.environ.get('DOCKER_ENV') else "render" if os.environ.get('RENDER') else "development"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)