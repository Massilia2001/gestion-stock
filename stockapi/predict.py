from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from prophet import Prophet
import pandas as pd

from stockapi.database import get_db
from stockapi.models import Sale

router = APIRouter()

async def generate_forecast(periods: int, db: AsyncSession):
    result = await db.execute(select(Sale))
    sales = result.scalars().all()

    if not sales:
        return []

    df = pd.DataFrame([{"ds": s.ds, "y": s.y} for s in sales])
    model = Prophet()
    model.fit(df)

    future = model.make_future_dataframe(periods=periods)
    forecast = model.predict(future)

    return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(periods).to_dict(orient="records")

@router.get("/predict")
async def predict_sales(periods: int = 30, db: AsyncSession = Depends(get_db)):
    forecast = await generate_forecast(periods, db)
    if not forecast:
        raise HTTPException(status_code=404, detail="No sales data found")
    return {"forecast": forecast}

