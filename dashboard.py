import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000"  # ou l'URL de ton FastAPI

st.title("Dashboard de gestion et prévision des stocks")

# --- Section Produits ---
st.header("Liste des produits")
prods = requests.get(f"{API_URL}/products").json()
prod_df = pd.DataFrame(prods)
st.table(prod_df)

# --- Sélection d’un produit ---
prod_ids = prod_df["id"].tolist()
prod_names = prod_df["name"].tolist()
prod_choice = st.selectbox("Choisir un produit pour la prévision :", prod_names)

if prod_choice:
    prod_id = prod_df[prod_df["name"] == prod_choice]["id"].values[0]
    
    # --- Prévision par produit ---
    st.subheader(f"Prévision de la demande (ID: {prod_id})")
    forecast = requests.get(f"{API_URL}/predict-by-product", params={"product_id": prod_id}).json()
    if "forecast" in forecast:
        df_forecast = pd.DataFrame(forecast["forecast"])
        st.line_chart(df_forecast.set_index("ds")["yhat"])
        st.write(df_forecast)
    else:
        st.warning(forecast.get("error", "Erreur de prévision."))

    # --- Recommandation de commande ---
    st.subheader("Quantité à commander (recommandation)")
    reco = requests.get(f"{API_URL}/recommendation", params={"product_id": prod_id}).json()
    st.write(reco)

# --- Visualiser toutes les recommandations ---
st.header("Toutes les recommandations (CSV exportable)")
if st.button("Télécharger CSV des recommandations"):
    csv = requests.get(f"{API_URL}/export-recommendations-csv").text
    st.download_button("Télécharger CSV", data=csv, file_name="recommandations.csv", mime="text/csv")

