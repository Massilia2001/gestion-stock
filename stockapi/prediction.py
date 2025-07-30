from prophet import Prophet
import pandas as pd
from sqlalchemy import select
from .models import Sale
from .database import AsyncSessionLocal

async def predict_next_days(n_days: int = 7):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Sale))
        sales = result.scalars().all()

    df = pd.DataFrame([{"ds": s.ds, "y": s.y} for s in sales])
    if df.empty:
        return []

    model = Prophet()
    model.fit(df)

    future = model.make_future_dataframe(periods=n_days)
    forecast = model.predict(future)

    return forecast.tail(n_days)[["ds", "yhat", "yhat_lower", "yhat_upper"]].to_dict(orient="records")
