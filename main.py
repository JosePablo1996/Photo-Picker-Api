from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, Boolean, Text, TIMESTAMP, ARRAY
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.sql import func
from urllib.parse import quote_plus
import os
from datetime import datetime
import uuid
from dotenv import load_dotenv

# Cargar variables de entorno solo en desarrollo local
load_dotenv()

# Configuración desde variables de entorno
DB_HOST = os.getenv("DB_HOST", "20.84.99.214")
DB_PORT = os.getenv("DB_PORT", "443")  # Puerto 443 para PostgreSQL
DB_NAME = os.getenv("DB_NAME", "PhotoPickerAPI")
DB_USER = os.getenv("DB_USER", "photopicker_user")  # Usuario correcto
DB_PASSWORD = os.getenv("DB_PASSWORD", "uPxBHn]Ag9H~N4'K")

# Validar que todas las variables críticas estén presentes
required_vars = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
missing_vars = [var for var in required_vars if not os.getenv(var) and not globals().get(var)]

if missing_vars:
    print(f"Advertencia: Variables de entorno faltantes: {missing_vars}")
    print("Usando valores por defecto...")

# Codificar la contraseña para la URL
ENCODED_PASSWORD = quote_plus(DB_PASSWORD)

# Cadena de conexión a PostgreSQL con puerto 443
DATABASE_URL = f"postgresql://{DB_USER}:{ENCODED_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Configuración de SQLAlchemy
try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={'sslmode': 'require'})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base = declarative_base()
    print(f"✅ Conectado a la base de datos: {DB_NAME} en {DB_HOST}:{DB_PORT}")
except Exception as e:
    print(f"❌ Error conectando a la base de datos: {e}")
    raise

# Modelo de la base de datos para imágenes
class Image(Base):
    __tablename__ = "images"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=False)
    width = Column(Integer)
    height = Column(Integer)
    upload_date = Column(TIMESTAMP(timezone=True), server_default=func.now())
    last_modified = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    file_path = Column(String(500), nullable=False)
    thumbnail_path = Column(String(500))
    description = Column(Text)
    tags = Column(ARRAY(String))
    is_public = Column(Boolean, default=False)
    user_id = Column(String(100))
    device_info = Column(Text)
    app_version = Column(String(50))

# Crear las tablas en la base de datos
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas de la base de datos creadas/verificadas correctamente")
except Exception as e:
    print(f"❌ Error creando tablas: {e}")

# Esquemas Pydantic
class ImageSchema(BaseModel):
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    width: int = None
    height: int = None
    file_path: str
    thumbnail_path: str = None
    description: str = None
    tags: list = []
    is_public: bool = False
    user_id: str = None
    device_info: str = None
    app_version: str = None

    class Config:
        orm_mode = True

class ImageResponseSchema(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    width: int = None
    height: int = None
    upload_date: datetime
    last_modified: datetime
    file_path: str
    thumbnail_path: str = None
    description: str = None
    tags: list = []
    is_public: bool
    user_id: str = None
    device_info: str = None
    app_version: str = None

    class Config:
        orm_mode = True

# Instancia de la aplicación FastAPI
app = FastAPI(
    title="Photo Picker API", 
    version="1.0.0",
    description="API para subir y gestionar imágenes desde aplicaciones Android"
)

# Configuración de CORS
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directorios desde variables de entorno
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
THUMBNAIL_DIR = os.getenv("THUMBNAIL_DIR", "thumbnails")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

# Servir archivos estáticos
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/thumbnails", StaticFiles(directory=THUMBNAIL_DIR), name="thumbnails")

# Dependencia para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Rutas de la API
@app.get("/")
def read_root():
    return {
        "message": "Photo Picker API está funcionando correctamente",
        "database": DB_NAME,
        "host": DB_HOST,
        "port": DB_PORT,
        "status": "active"
    }

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Endpoint para verificar que la API y la base de datos están funcionando"""
    try:
        # Intentar una consulta simple para verificar la conexión a la base de datos
        db.execute("SELECT 1")
        
        # Verificar directorios
        upload_dir_exists = os.path.exists(UPLOAD_DIR)
        upload_dir_writable = os.access(UPLOAD_DIR, os.W_OK)
        
        return {
            "status": "healthy",
            "database": "connected",
            "database_name": DB_NAME,
            "database_host": DB_HOST,
            "database_port": DB_PORT,
            "upload_dir": {
                "exists": upload_dir_exists,
                "writable": upload_dir_writable,
                "path": UPLOAD_DIR
            },
            "timestamp": datetime.now().isoformat(),
            "environment": "production" if os.getenv("RENDER") else "development"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión a la base de datos: {str(e)}")

@app.get("/config")
def show_config():
    """Endpoint para mostrar la configuración actual (útil para debugging)"""
    return {
        "db_host": DB_HOST,
        "db_port": DB_PORT,
        "db_name": DB_NAME,
        "db_user": DB_USER,
        "upload_dir": UPLOAD_DIR,
        "thumbnail_dir": THUMBNAIL_DIR,
        "database_url": f"postgresql://{DB_USER}:******@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    }

@app.get("/test-upload")
async def test_upload_endpoint():
    """Endpoint para probar que el upload funciona"""
    return {
        "status": "upload_endpoint_available",
        "method": "POST",
        "endpoint": "/upload",
        "required_fields": ["file (image)"],
        "optional_fields": ["user_id", "description", "tags", "is_public", "device_info", "app_version"]
    }

@app.get("/images/")
def get_images(
    skip: int = 0, 
    limit: int = 100, 
    user_id: str = None, 
    is_public: bool = None,
    db: Session = Depends(get_db)
):
    query = db.query(Image)
    
    if user_id:
        query = query.filter(Image.user_id == user_id)
    
    if is_public is not None:
        query = query.filter(Image.is_public == is_public)
    
    images = query.offset(skip).limit(limit).all()
    
    return [
        ImageResponseSchema.from_orm(img) for img in images
    ]

@app.get("/images/{image_id}")
def get_image(image_id: int, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    return ImageResponseSchema.from_orm(image)

@app.post("/upload")  # ✅ Endpoint corregido a /upload
async def upload_image(
    file: UploadFile = File(...),
    user_id: str = Form(None),
    description: str = Form(None),
    tags: str = Form(None),
    is_public: bool = Form(False),
    device_info: str = Form(None),
    app_version: str = Form(None),
    db: Session = Depends(get_db)
):
    # Validar tipo de archivo
    allowed_mime_types = ["image/jpeg", "image/png", "image/gif", "image/webp", "image/jpg"]
    if file.content_type not in allowed_mime_types:
        raise HTTPException(status_code=400, detail="Tipo de archivo no permitido. Solo se permiten imágenes JPEG, PNG, GIF y WebP")
    
    # Generar un nombre único para el archivo
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    # Guardar el archivo
    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar archivo: {str(e)}")
    
    # Procesar tags
    tag_list = []
    if tags:
        tag_list = [tag.strip() for tag in tags.split(",")]
    
    # Crear registro en la base de datos con URL accesible
    db_image = Image(
        filename=unique_filename,
        original_filename=file.filename,
        file_size=len(contents),
        mime_type=file.content_type,
        file_path=f"/uploads/{unique_filename}",  # ✅ Ruta accesible via URL
        description=description,
        tags=tag_list,
        is_public=is_public,
        user_id=user_id,
        device_info=device_info,
        app_version=app_version
    )
    
    try:
        db.add(db_image)
        db.commit()
        db.refresh(db_image)
    except Exception as e:
        # Eliminar archivo si hay error en la BD
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Error en base de datos: {str(e)}")
    
    return {
        "message": "Imagen subida exitosamente",
        "image_id": db_image.id,
        "filename": unique_filename,
        "original_filename": file.filename,
        "file_url": f"https://photo-picker-api-1.onrender.com/uploads/{unique_filename}",
        "file_size": len(contents),
        "upload_date": db_image.upload_date.isoformat()
    }

@app.put("/images/{image_id}")
def update_image(
    image_id: int,
    description: str = Form(None),
    tags: str = Form(None),
    is_public: bool = Form(None),
    db: Session = Depends(get_db)
):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    
    if description is not None:
        image.description = description
    
    if tags is not None:
        image.tags = [tag.strip() for tag in tags.split(",")]
    
    if is_public is not None:
        image.is_public = is_public
    
    db.commit()
    db.refresh(image)
    
    return {
        "message": "Imagen actualizada exitosamente",
        "image": ImageResponseSchema.from_orm(image)
    }

@app.delete("/images/{image_id}")
def delete_image(image_id: int, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    
    # Eliminar el archivo físico
    physical_path = os.path.join(UPLOAD_DIR, image.filename)
    if os.path.exists(physical_path):
        os.remove(physical_path)
    
    # Eliminar la miniatura si existe
    if image.thumbnail_path:
        thumbnail_filename = os.path.basename(image.thumbnail_path)
        thumbnail_path = os.path.join(THUMBNAIL_DIR, thumbnail_filename)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
    
    # Eliminar el registro de la base de datos
    db.delete(image)
    db.commit()
    
    return {"message": "Imagen eliminada exitosamente"}

# Ejecutar la aplicación
if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    print("=" * 50)
    print("🚀 Iniciando Photo Picker API")
    print("=" * 50)
    print(f"📊 Base de datos: {DB_NAME}")
    print(f"🌐 Host: {DB_HOST}:{DB_PORT}")
    print(f"👤 Usuario: {DB_USER}")
    print(f"📁 Directorio uploads: {UPLOAD_DIR}")
    print(f"🔗 URL de conexión: postgresql://{DB_USER}:******@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print("=" * 50)
    
    uvicorn.run(app, host=host, port=port)