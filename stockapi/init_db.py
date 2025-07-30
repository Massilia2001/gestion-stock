import asyncio
from stockapi.database import engine, Base

from stockapi import models  # <-- Cet import est indispensable

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created!")

if __name__ == "__main__":
    asyncio.run(init_db())

