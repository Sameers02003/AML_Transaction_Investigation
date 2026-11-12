from sqlalchemy import create_engine # type: ignore
from sqlalchemy.orm import sessionmaker, DeclarativeBase # type: ignore
from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()