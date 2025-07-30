from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, File, UploadFile, Query, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from prophet import Prophet
import pandas as pd
from datetime import datetime
from stockapi.database import get_db
from stockapi.models import Sale, Product
import matplotlib.pyplot as plt
import os
from fastapi.staticfiles import StaticFiles
from stockapi.utils import calcul_recommande
from fastapi.responses import StreamingResponse
import io

app = FastAPI()
app.mount("/static", StaticFiles(directory="stockapi/static"), name="static")
router = APIRouter()
templates = Jinja2Templates(directory="stockapi/templates")
def save_forecast_plot(historical_dates, historical_sales, forecast_df, product_name, product_id):
    print(">>> Je génère un graphique dans save_forecast_plot !")
    plt.figure(figsize=(8,4))
    plt.plot(historical_dates, historical_sales, label='Ventes historiques')
    plt.plot(forecast_df['ds'], forecast_df['yhat'], label='Prévision 7 jours', linestyle='--', marker='o')
    plt.title(f"Prévision pour {product_name}")
    plt.xlabel('Date')
    plt.ylabel('Ventes')
    plt.legend()
    plt.tight_layout()
    static_dir = "stockapi/static"
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    img_path = f"{static_dir}/forecast_{product_id}.png"
    plt.savefig(img_path)
    plt.close()
    print(f">>> Graphe enregistré ici : {img_path}")
    return img_path

# ---- Cette fonction doit être au même niveau que les autres (pas à l'intérieur de save_forecast_plot !) ----
async def compute_recommendation(product, sales_rows):
    """
    Calcule la quantité à commander sur la période du lead time.
    Utilise Prophet si ventes, sinon renvoie 0.
    """
    if not sales_rows:
        return {
            "demand_forecast_next_period": 0,
            "recommended_order_qty": 0
        }

    df = pd.DataFrame(sales_rows, columns=["ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"])
    model = Prophet()
    model.fit(df)
    lead_time = product.lead_time or 7
    future = model.make_future_dataframe(periods=lead_time)
    forecast = model.predict(future)
    forecast_lead_time = forecast.tail(lead_time)
    demand_lead_time = forecast_lead_time["yhat"].sum()

    current_stock = getattr(product, "current_stock", 0)
    capacity = product.capacity or 0

    max_possible = max(0, capacity - current_stock) if capacity else demand_lead_time - current_stock
    recommended_qty = int(min(max_possible, max(0, demand_lead_time - current_stock)))
    return {
        "demand_forecast_next_period": round(demand_lead_time, 1),
        "recommended_order_qty": recommended_qty
    }


# ----------- Forecast helper -----------
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
    forecast["ds"] = forecast["ds"].dt.strftime("%Y-%m-%d")
    return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(periods).to_dict(orient="records")

# ----------- API ROUTES -----------

@router.get("/predict", summary="Prévision globale (tous produits confondus)")
async def predict_sales(periods: int = 30, db: AsyncSession = Depends(get_db)):
    forecast = await generate_forecast(periods, db)
    if not forecast:
        raise HTTPException(status_code=404, detail="No sales data found")
    return {"forecast": forecast}

@router.get("/predict-view", response_class=HTMLResponse)
async def view_forecast(request: Request, periods: int = 30, db: AsyncSession = Depends(get_db)):
    forecast = await generate_forecast(periods, db)
    return templates.TemplateResponse(
        "predict.html",
        {"request": request, "forecast": forecast, "periods": periods}
    )

@router.get("/upload", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@router.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    await db.execute(text("DELETE FROM sales"))
    await db.commit()
    df = pd.read_csv(file.file)
    for _, row in df.iterrows():
        sale = Sale(
            ds=datetime.strptime(row["ds"], "%Y-%m-%d").date(),
            y=float(row["y"]),
            product_id=int(row["product_id"])
        )
        db.add(sale)
    await db.commit()
    return {"message": "CSV uploaded and data saved!"}

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@router.get("/visualisation", response_class=HTMLResponse)
async def view_sales(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Sale))
    sales = result.scalars().all()
    data = [
        {"ds": s.ds.strftime("%Y-%m-%d"), "y": s.y}
        for s in sales
    ]
    return templates.TemplateResponse(
        "visualisation.html",
        {"request": request, "sales": data}
    )

@router.post("/products")
async def create_product(name: str, db: AsyncSession = Depends(get_db)):
    # 1. Vérifier si le produit existe déjà
    query = select(Product).where(Product.name == name)
    result = await db.execute(query)
    existing_product = result.scalar_one_or_none()
    if existing_product:
        raise HTTPException(
            status_code=400, 
            detail=f"Le produit '{name}' existe déjà."
        )
    
    # 2. Sinon, on insère
    product = Product(name=name)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return {"id": product.id, "name": product.name}

@router.get("/products")
async def list_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
    products = result.scalars().all()
    return [{"id": p.id, "name": p.name} for p in products]

@router.post("/products-view", response_class=HTMLResponse)
async def create_product_view(
    request: Request,
    name: str = Form(...),
    current_stock: int = Form(0),
    capacity: int = Form(0),
    lead_time: int = Form(0),
    db: AsyncSession = Depends(get_db)
):
    # Vérifier si le produit existe déjà
    result = await db.execute(select(Product).where(Product.name == name))
    existing = result.scalar_one_or_none()
    if existing:
        # Recharger la page avec le message d’erreur
        products = (await db.execute(select(Product))).scalars().all()
        return templates.TemplateResponse(
            "products_view.html",
            {
                "request": request,
                "products": products,
                "error": f"Le produit '{name}' existe déjà !"
            }
        )
    # Sinon, créer le produit
    product = Product(
        name=name,
        current_stock=current_stock,
        capacity=capacity,
        lead_time=lead_time
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return RedirectResponse(url="/products-view", status_code=303)

@router.get("/products-view", response_class=HTMLResponse)
async def products_view(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
    products = result.scalars().all()
    return templates.TemplateResponse(
        "products_view.html", 
        {"request": request, "products": products}
    )
# ----------- PREDICT + RECOMMENDATION PAR PRODUIT -----------
templates = Jinja2Templates(directory="stockapi/templates")

@router.get("/predict-by-product", summary="Prévision de la demande pour un produit")
async def predict_next_week(
    product_id: int = Query(..., description="ID du produit"),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Sale.ds, Sale.y).where(Sale.product_id == product_id).order_by(Sale.ds)
    )
    rows = result.fetchall()
    if not rows:
        return {"error": "No data found for this product."}
    df = pd.DataFrame(rows, columns=["ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"])
    model = Prophet()
    model.fit(df)
    future = model.make_future_dataframe(periods=7)
    forecast = model.predict(future)
    forecast_result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(7)
    forecast_result["ds"] = forecast_result["ds"].dt.strftime("%Y-%m-%d")
    return {
        "product_id": product_id,
        "forecast": forecast_result.to_dict(orient="records")
    }

@router.get("/recommendation", summary="Quantité optimale à commander")
async def recommend_order_quantity(
    product_id: int = Query(..., description="ID du produit"),
    db: AsyncSession = Depends(get_db)
):
    # Récupère ventes
    result = await db.execute(
        select(Sale.ds, Sale.y).where(Sale.product_id == product_id).order_by(Sale.ds)
    )
    rows = result.fetchall()

    # Récupère produit
    prod_result = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_result.scalars().first()
    if not product:
        return {"error": "Product not found."}

    reco = await compute_recommendation(product, rows)
    return {
        "product_id": product_id,
        "current_stock": getattr(product, "current_stock", 0),
        "capacity": product.capacity,
        "lead_time": product.lead_time,
        **reco
    }



@router.get("/recommendation-view", response_class=HTMLResponse)
async def recommendation_view(request: Request, product_id: int, db: AsyncSession = Depends(get_db)):
    # 1. Cherche les ventes pour ce produit
    result = await db.execute(select(Sale.ds, Sale.y).where(Sale.product_id == product_id).order_by(Sale.ds))
    rows = result.fetchall()
    if not rows:
        return templates.TemplateResponse("recommendation.html", {"request": request, "result": None, "product": {"name": "?"}, "plot_path": None})

    # 2. Infos produit (stock, capacité, lead_time)
    prod_result = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_result.scalars().first()
    if not product:
        return templates.TemplateResponse(
            "recommendation.html",
            {
                "request": request,
                "result": None,
                "product": {"name": "Produit non trouvé"},
                "plot_path": None
            }
        )

    # ... LE RESTE DE TA LOGIQUE COMME AVANT ...


    df = pd.DataFrame(rows, columns=["ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"])
    model = Prophet()
    model.fit(df)
    future = model.make_future_dataframe(periods=7)
    forecast = model.predict(future)
    forecast_next_week = forecast[["ds", "yhat"]].tail(7)
    demand_forecast = forecast_next_week["yhat"].sum()

    # 3. Génération du graphique (on utilise product.name si product existe)
    plot_path = save_forecast_plot(
        historical_dates=df["ds"],
        historical_sales=df["y"],
        forecast_df=forecast,
        product_name=product.name if product else "Produit",
        product_id=product_id
    )

    # 4. Calcul de la recommandation
    reco = {
        "product_id": product_id,
        "demand_forecast_next_7_days": round(demand_forecast, 1),
        "current_stock": getattr(product, "current_stock", 0) if product else 0,
        "capacity": product.capacity if product and product.capacity else 0,
        "lead_time": product.lead_time if product and product.lead_time else 0,
        "recommended_order_qty": int(max(0, demand_forecast - (getattr(product, "current_stock", 0) if product else 0)))
    }

    return templates.TemplateResponse(
        "recommendation.html",
        {
            "request": request,
            "result": reco,
            "product": product,
            "plot_path": f"/static/forecast_{product_id}.png"
        }
    )
@router.get("/recommandations")
async def get_recommandations(db: AsyncSession = Depends(get_db)):
    produits = (await db.execute(select(Product))).scalars().all()
    resultat = []
    for prod in produits:
        # Récupère l'historique des ventes pour chaque produit
        result = await db.execute(
            select(Sale.ds, Sale.y).where(Sale.product_id == prod.id).order_by(Sale.ds)
        )
        rows = result.fetchall()
        reco = await compute_recommendation(prod, rows)
        resultat.append({
            "produit": prod.name,
            "stock": prod.current_stock,
            "prévision_demandes": reco["demand_forecast_next_period"],
            "quantité_à_commander": reco["recommended_order_qty"]
        })
    return resultat


@router.get("/export-recommendations-csv")
async def export_recommendations_csv(db: AsyncSession = Depends(get_db)):
    data = await get_recommandations(db)
    df = pd.DataFrame(data)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    response = StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv"
    )
    response.headers["Content-Disposition"] = "attachment; filename=recommendations.csv"
    return response


app.include_router(router)


