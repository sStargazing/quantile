import requests

url = "https://api.frankfurter.dev/v2/rates?base=AUD&from=2024-10-01"
response = requests.get(url)
aud_base = response.json()

print(aud_base[1])