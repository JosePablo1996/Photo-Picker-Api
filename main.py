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

# Cargar variables de entorno
load_dotenv()

# Configuración desde variables de entorno
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Validar que todas las variables estén presentes
if not all([DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD]):
    raise ValueError("Faltan variables de entorno para la conexión a la base de datos")

# Codificar la contraseña para la URL
ENCODED_PASSWORD = quote_plus(DB_PASSWORD)

# Cadena de conexión a PostgreSQL
DATABASE_URL = f"postgresql://{DB_USER}:{ENCODED_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Configuración de SQLAlchemy
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

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
Base.metadata.create_all(bind=engine)

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
app = FastAPI(title="Photo Picker API", version="1.0.0")

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
        "host": DB_HOST
    }

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Endpoint para verificar que la API y la base de datos están funcionando"""
    try:
        # Intentar una consulta simple para verificar la conexión a la base de datos
        db.execute("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión a la base de datos: {str(e)}")

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

@app.post("/images/")
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
    # Generar un nombre único para el archivo
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    # Guardar el archivo
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # Procesar tags
    tag_list = []
    if tags:
        tag_list = [tag.strip() for tag in tags.split(",")]
    
    # Crear registro en la base de datos
    db_image = Image(
        filename=unique_filename,
        original_filename=file.filename,
        file_size=len(contents),
        mime_type=file.content_type,
        file_path=file_path,
        description=description,
        tags=tag_list,
        is_public=is_public,
        user_id=user_id,
        device_info=device_info,
        app_version=app_version
    )
    
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    
    return {
        "message": "Imagen subida exitosamente",
        "image": ImageResponseSchema.from_orm(db_image)
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
    if os.path.exists(image.file_path):
        os.remove(image.file_path)
    
    # Eliminar la miniatura si existe
    if image.thumbnail_path and os.path.exists(image.thumbnail_path):
        os.remove(image.thumbnail_path)
    
    # Eliminar el registro de la base de datos
    db.delete(image)
    db.commit()
    
    return {"message": "Imagen eliminada exitosamente"}

# Ejecutar la aplicación
if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    print(f"Iniciando servidor en {host}:{port}")
    print(f"Base de datos: {DB_NAME} en {DB_HOST}:{DB_PORT}")
    
    uvicorn.run(app, host=host, port=port)