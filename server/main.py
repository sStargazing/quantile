import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI()

FRANKFURTER_URL = "https://api.frankfurter.dev/v2/rate"

top_currencies = {"JPY": {"name": "Japanese Yen", "countries": ["Japan"]},
                  "USD": {"name": "United States Dollar", "countries": ["USA"]},
                  "EUR": {"name": "Euro", "countries": ["France", "Germany", "Spain"]},
                  "GBP": {"name": "Pound Sterling", "countries": ["UK"]},
                  "CNY": {"name": "Chinese Yuan", "countries": ["China"]},
                  "CHF": {"name": "Swiss Franc", "countries": ["Switzerland"]}
}

def get_rate(code):
    response = requests.get(f"{FRANKFURTER_URL}/aud/{code}")
    data = response.json()
    return data["rate"], data["date"]


# ------- ROUTES --------

@app.get("/") #serves the HTML page
def home():
    return FileResponse("static/index.html")

@app.get("/api/currencies")
def currencies():
    return top_currencies

@app.get("/api/convert")
def convert(to: str, amount: float):
    to = to.upper()
    if to not in top_currencies:
        raise HTTPException(status_code=404, detail=f"Unknown currency: {to}")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")
 
    try:
        rate, date = get_rate(to)
    except requests.RequestException:
        # if frankfurter api is slow or down
        raise HTTPException(status_code=502, detail="Couldn't fetch the exchange rate")
 
    return {
        "from": "AUD",
        "to": to,
        "amount": amount,
        "rate": rate,
        "result": round(amount * rate, 2),
        "date": date,
    }