from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.db.session import Base

class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    type = Column(String, nullable=False)  # goal, preference, constraint, life_event, philosophy, etc.
    text = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=False)  # 768-dim Vertex AI text-embedding-004
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
