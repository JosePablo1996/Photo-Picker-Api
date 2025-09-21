# Procfile optimizado para Render.com
web: uvicorn main:app --host=0.0.0.0 --port=$PORT --timeout-keep-alive=300 --log-level=info

# Opción alternativa para desarrollo (no usar en producción)
# web: uvicorn main:app --host=0.0.0.0 --port=$PORT --reload --log-level=debug