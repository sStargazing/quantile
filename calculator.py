top_currencies = {"JPY": {"name": "Japanese Yen", "countries": ["Japan"]},
                  "USD": {"name": "United States Dollar", "countries": ["USA"]},
                  "EUR": {"name": "Euro", "countries": ["France", "Germany", "Spain"]},
                  "GBP": {"name": "Pound Sterling", "countries": ["UK"]},
                  "CNY": {"name": "Chinese Yuan", "countries": ["China"]},
                  "CHF": {"name": "Swiss Franc", "countries": ["Switzerland"]}
}

for index, (key, value) in enumerate(top_currencies.items()):
    print(f"{index}. {value["name"]} ({key})")

input("Hello")