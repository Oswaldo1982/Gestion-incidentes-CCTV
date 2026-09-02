from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool
from app.config import settings

# Determinar URL efectiva de la base de datos (Producción o Sandbox Demo Volátil)
db_url = settings.effective_database_url

connect_args = {}
engine_kwargs = {}

if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    if ":memory:" in db_url or db_url == "sqlite://":
        # StaticPool mantiene la base de datos en memoria viva durante todo el ciclo de vida del proceso
        engine_kwargs["poolclass"] = StaticPool

engine_kwargs["connect_args"] = connect_args

engine = create_engine(
    db_url,
    **engine_kwargs
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
