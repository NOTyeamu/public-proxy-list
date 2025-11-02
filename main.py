import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

# Источники списков прокси
SOURCES = [
    "https://www.sslproxies.org/",
    "https://free-proxy-list.net/",
    "https://www.us-proxy.org/",
]

def fetch_proxies():
    proxies = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in SOURCES:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table", id="proxylisttable")
            if not table:
                continue
            for row in table.tbody.find_all("tr"):
                cols = row.find_all("td")
                ip = cols[0].text.strip()
                port = cols[1].text.strip()
                country = cols[3].text.strip()
                https = cols[6].text.strip().lower()
                if https == "yes":
                    proxies.append({"ip": ip, "port": port, "country": country})
        except Exception as e:
            print(f"Ошибка при загрузке {url}: {e}")
    # удаляем дубликаты
    unique = {(p["ip"], p["port"]): p for p in proxies}
    return list(unique.values())

def save_json(proxies):
    with open("proxies.json", "w", encoding="utf-8") as f:
        json.dump(proxies, f, ensure_ascii=False, indent=2)

def save_html(proxies):
    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    rows = "\n".join(
        f"<tr><td>{p['ip']}</td><td>{p['port']}</td><td>{p['country']}</td></tr>"
        for p in proxies
    )
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Список HTTPS-прокси</title>
<style>
body {{
  background-color: #0e1117;
  color: #e0e0e0;
  font-family: "Segoe UI", Roboto, Arial, sans-serif;
  text-align: center;
}}
table {{
  margin: auto;
  border-collapse: collapse;
  width: 90%;
}}
th, td {{
  border: 1px solid #333;
  padding: 8px 10px;
  text-align: center;
}}
th {{
  background-color: #20232a;
}}
tr:nth-child(even) {{
  background-color: #16181d;
}}
</style>
</head>
<body>
<h1>Свежие HTTPS-прокси</h1>
<p>Обновлено: {updated}</p>
<table>
<tr><th>IP</th><th>Port</th><th>Country</th></tr>
{rows}
</table>
<p style="color:#888;">Автоматическое обновление каждые 30 минут через GitHub Actions.</p>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

def main():
    print("Загружаю список прокси...")
    proxies = fetch_proxies()
    print(f"Найдено {len(proxies)} HTTPS прокси")
    save_json(proxies)
    save_html(proxies)
    print("Файлы обновлены: proxies.json и index.html")

if __name__ == "__main__":
    main()
