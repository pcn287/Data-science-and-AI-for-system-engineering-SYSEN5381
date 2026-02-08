import requests

url = "https://httpbin.org/post"
payload = {"name": "test"}

response = requests.post(url, json=payload)

print(response.status_code)
print(response.json())
