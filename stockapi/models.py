from sqlalchemy import Column, Integer, Date, Float, String, ForeignKey
from sqlalchemy.orm import relationship
from stockapi.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    capacity = Column(Integer, nullable=True)    # Capacité max de stockage (optionnel)
    lead_time = Column(Integer, nullable=True)   # Délai de livraison (jours, optionnel)
    current_stock = Column(Integer, nullable=False, default=0)
   
    sales = relationship("Sale", back_populates="product")

class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    ds = Column(Date, index=True)   # Date de la vente
    y = Column(Float)               # Valeur à prédire (ventes)
    product_id = Column(Integer, ForeignKey('products.id'))
    product = relationship("Product", back_populates="sales")
