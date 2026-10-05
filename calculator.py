import requests

top_currencies = {"JPY": {"name": "Japanese Yen", "countries": ["Japan"]},
                  "USD": {"name": "United States Dollar", "countries": ["USA"]},
                  "EUR": {"name": "Euro", "countries": ["France", "Germany", "Spain"]},
                  "GBP": {"name": "Pound Sterling", "countries": ["UK"]},
                  "CNY": {"name": "Chinese Yuan", "countries": ["China"]},
                  "CHF": {"name": "Swiss Franc", "countries": ["Switzerland"]}
}

top_currencies_codes = list(top_currencies)

for index, (key, value) in enumerate(top_currencies.items()):
    print(f"{index + 1}. {value["name"]} ({key})")

while True: 
    try:
        choice = int(input(f"Choose a Currency (1-{len(top_currencies_codes)}): "))
    except ValueError: 
        print(f"Please enter a valid integer between 1-{len(top_currencies_codes)}.")
        continue

    if 1 <= choice <= len(top_currencies_codes):
        break
    print("That number isn't on the list.")

chosen_currency_code = top_currencies_codes[choice - 1]

while True:
    try:
        amount = float(input("Enter amount in AUD: "))
    except ValueError:
        print("Please enter a valid amount.")
    if 0 <= amount:
        break

url = f"https://api.frankfurter.dev/v2/rate/aud/{chosen_currency_code}"
response = requests.get(url)
data = response.json()
rate = data["rate"]
date = data["date"]

print(f"{amount} AUD = {rate * amount} {chosen_currency_code} (rate {rate}, as of {date})")