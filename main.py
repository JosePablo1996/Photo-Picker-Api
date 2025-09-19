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

app = FastAPI(title="Photo Picker API", version="1.0.0")

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de base de datos para Render (usando variables de entorno)
def get_db_config():
    # Para Render: usa ClearDB MySQL
    if os.environ.get('RENDER'):
        database_url = os.environ.get('CLEARDB_DATABASE_URL', '')
        if database_url:
            url = urllib.parse.urlparse(database_url)
            return {
                'host': url.hostname,
                'database': url.path[1:],
                'user': url.username,
                'password': url.password,
                'port': url.port or 3306
            }
    
    # Para desarrollo local (tu XAMPP)
    return {
        'host': 'localhost',
        'database': 'photo_picker_db',
        'user': 'root',
        'password': '',
        'port': 3377
    }

DB_CONFIG = get_db_config()

# Directorio para uploads (en Render usa /tmp/ para persistencia)
UPLOAD_DIR = os.environ.get('UPLOAD_DIR', 'uploads')
Path(UPLOAD_DIR).mkdir(exist_ok=True)

def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

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
            print("✅ Table created successfully")
        except Error as e:
            print(f"❌ Error creating table: {e}")
        finally:
            connection.close()

create_table()

@app.get("/")
async def root():
    return {
        "message": "Photo Picker API is running on Render!",
        "status": "success",
        "timestamp": datetime.now().isoformat()
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

        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        file_size = os.path.getsize(filepath)

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

        # URL para Render
        base_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:8000')
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

            base_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:8000')
            result = [{
                "id": img['image_id'],
                "url": f"{base_url}/images/{img['filename']}",
                "description": img['description'] or "",
                "uploadDate": img['upload_date'].isoformat() if img['upload_date'] else "",
                "fileSize": img['file_size'],
                "mimeType": img['mime_type']
            } for img in images]

            return {"success": True, "images": result}
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
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database": db_status,
        "environment": "production" if os.environ.get('RENDER') else "development"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)