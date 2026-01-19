# models/vector_kojin.py

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class AIAdviceKojin(Base):
    __tablename__ = "ai_advice_kojin"
    __table_args__ = {"schema": "app"}

    id = Column(Integer, primary_key=True)
    kojin_id = Column(Integer, nullable=False)
    advice_type = Column(String)
    target_scope = Column(String)
    analysis_type = Column(String)
    data_source = Column(String)
    predicted_kyosai = Column(String)
    advice_text = Column(Text)
    created_at = Column(DateTime)
    staff_advice = Column(Text)
    suggested_message = Column(Text)
    kamorate = Column(Integer)