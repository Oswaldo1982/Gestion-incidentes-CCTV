#!/usr/bin/env python
"""
Script ejecutable para poblar la base de datos de demostración CCTV.
Ejecución: python seeder_demo.py
"""
import os
import sys

# Asegurar que el directorio raíz esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.seeder_demo import seed_demo_data

def main():
    print(f"[*] Modo actual: {'DEMO / SANDBOX (VOLÁTIL)' if settings.DEMO_MODE else 'PRODUCCIÓN / ESTÁNDAR'}")
    print(f"[*] Base de datos destino: {settings.effective_database_url}")
    
    # Crear tablas si no existen
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        seed_demo_data(db)
        print("[+] Proceso de sembrado finalizado correctamente.")
    except Exception as e:
        print(f"[!] Error al poblar datos: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
