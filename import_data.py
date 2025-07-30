# import_data.py

import pandas as pd
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from stockapi.models import Product, Sale  # adapte si besoin
import asyncio

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
engine = create_async_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def import_products():
    df = pd.DataFrame([
        {"name": "Produit A", "capacity": 100, "lead_time": 5, "current_stock": 30},
        {"name": "Produit B", "capacity": 200, "lead_time": 7, "current_stock": 150},
    ])
    async with SessionLocal() as session:
        for _, row in df.iterrows():
            prod = Product(**row)
            session.add(prod)
        await session.commit()

async def import_sales():
    df = pd.DataFrame([
        {"ds": "2024-07-01", "y": 12, "product_id": 1},
        {"ds": "2024-07-02", "y": 15, "product_id": 1},
        {"ds": "2024-07-01", "y": 8, "product_id": 2},
        {"ds": "2024-07-02", "y": 13, "product_id": 2},
    ])
    async with SessionLocal() as session:
        for _, row in df.iterrows():
            sale = Sale(**row)
            session.add(sale)
        await session.commit()

async def main():
    await import_products()
    await import_sales()

if __name__ == "__main__":
    asyncio.run(main())
