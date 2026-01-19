# models/vector_kojin.py

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class AIVectorKojin(Base):
    __tablename__ = "vector_kojin"
    __table_args__ = (
        Index("ix_kojin_analysis", "kojin_id", "analysis_type"),  # 複合インデックス
        {"schema": "ai"},
    )

    id = Column(Integer, primary_key=True)
    kojin_id = Column(Integer)
    analysis_type = Column(String)
    summary_json = Column(JSON)

