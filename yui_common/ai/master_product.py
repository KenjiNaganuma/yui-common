# models/master_product.py

from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class AIVectorProduct(Base):
    __tablename__ = "master_product"
    __table_args__ = {"schema": "kdp"}

    product_id = Column(String, primary_key=True)
    product_name = Column(String)
    product_type = Column(String)
    provider_text = Column(String)
    age_min = Column(Integer)
    age_max = Column(Integer)
    interest_trate = Column(float)
    feature_summary = Column(Text)
    recommend_keywords = Column(Text)
    condition_summary = Column(Text)
    recommend_reason = Column(Text)
    is_internal = Column(Boolean)
    created_at = Column(DateTime)

