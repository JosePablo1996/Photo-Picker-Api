# Opción 1: Para entornos de producción con múltiples workers
web: uvicorn main:app --host=0.0.0.0 --port=$PORT --workers=2 --timeout-keep-alive=30

# Opción 2: Para desarrollo o debugging
web: uvicorn main:app --host=0.0.0.0 --port=$PORT --reload

# Opción 3: Con nivel de log configurado
web: uvicorn main:app --host=0.0.0.0 --port=$PORT --workers=2 --log-level=info