# proxy_manager_with_country.py
import subprocess
import sys
import time
import json
import re
import os
from datetime import datetime

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

try:
    import requests
except ImportError:
    print("Устанавливаю requests...")
    install("requests")
    import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Устанавливаю beautifulsoup4...")
    install("beautifulsoup4")
    from bs4 import BeautifulSoup

# ----------------------------
# Настройки
# ----------------------------
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SOURCES = [
    "https://www.sslproxies.org/",
    "https://free-proxy-list.net/",
    "https://www.us-proxy.org/",
    "https://api.proxyscrape.com/?request=displayproxies&proxytype=https&timeout=5000&country=all&anonymity=all&ssl=yes",
]
DEAD_SOURCES_FILE = "dead_sources.json"
GOOD_PROXIES_FILE = "good_proxies.json"
BAD_PROXIES_FILE = "bad_proxies.json"
SOURCE_FAILS_FILE = "source_fail_counts.json"
SOURCE_FAIL_THRESHOLD = 3
IPPORT_RE = re.compile(r"(?:(?:\d{1,3}\.){3}\d{1,3}):\d{2,5}")

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def now_iso():
    return datetime.utcnow().isoformat() + "Z"

dead_sources = load_json(DEAD_SOURCES_FILE, {})
source_fail_counts = load_json(SOURCE_FAILS_FILE, {})

def mark_source_dead(url):
    dead_sources[url] = {"marked_dead_at": now_iso()}
    if url in source_fail_counts:
        del source_fail_counts[url]
    save_json(DEAD_SOURCES_FILE, dead_sources)
    save_json(SOURCE_FAILS_FILE, source_fail_counts)
    print(f"  -> Источник {url} помечен как МЁРТВЫЙ.")

def increment_source_fail(url):
    n = source_fail_counts.get(url, 0) + 1
    source_fail_counts[url] = n
    save_json(SOURCE_FAILS_FILE, source_fail_counts)
    print(f"  Источник {url} провалился ({n}/{SOURCE_FAIL_THRESHOLD}).")
    if n >= SOURCE_FAIL_THRESHOLD:
        mark_source_dead(url)

def reset_source_fail(url):
    if url in source_fail_counts:
        del source_fail_counts[url]
        save_json(SOURCE_FAILS_FILE, source_fail_counts)

def fetch_text(url, timeout=12):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  Ошибка загрузки {url}: {e}")
        return ""

def parse_table(html, url):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    results = []
    if not table:
        return results
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")
    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 2:
            ip = cols[0].text.strip()
            port = cols[1].text.strip()
            country = cols[3].text.strip() if len(cols) > 3 else "unknown"
            https_flag = cols[6].text.strip().lower() if len(cols) > 6 else ""
            if re.match(r"^(?:\d{1,3}\.){3}\d{1,3}$", ip) and port.isdigit():
                results.append({"ip": ip, "port": port, "country": country, "https": https_flag, "source": url})
    return results

def parse_ipport_plain(text, url):
    found = set(m.group(0) for m in IPPORT_RE.finditer(text))
    results = []
    for fp in found:
        ip, port = fp.split(":")
        results.append({"ip": ip, "port": port, "country": "unknown", "https": "", "source": url})
    return results

def gather_proxies(sources):
    all_proxies = []
    seen = set()
    for url in sources:
        if url in dead_sources:
            print(f"Пропускаю мёртвый источник: {url}")
            continue
        print(f"Запрашиваю {url} ...")
        text = fetch_text(url)
        if not text:
            increment_source_fail(url)
            continue
        parsed = parse_table(text, url)
        if parsed:
            print(f"  Нашёл {len(parsed)} прокси в таблице.")
            reset_source_fail(url)
        else:
            parsed = parse_ipport_plain(text, url)
            print(f"  Поиск по regex: найдено {len(parsed)} уникальных IP:PORT.")
            if parsed:
                reset_source_fail(url)
            else:
                increment_source_fail(url)
                continue
        for p in parsed:
            key = f"{p['ip']}:{p['port']}"
            if key not in seen:
                seen.add(key)
                all_proxies.append(p)
        time.sleep(0.3)
    print(f"Всего уникальных прокси собрано: {len(all_proxies)}")
    return all_proxies

def test_proxy(proxy, timeout=6):
    proxy_url = f"http://{proxy['ip']}:{proxy['port']}"
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        r = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=timeout)
        if r.status_code == 200:
            return True, r.text
        else:
            return False, f"status {r.status_code}"
    except Exception as e:
        return False, str(e)

def load_saved_proxies():
    good = load_json(GOOD_PROXIES_FILE, [])
    bad = load_json(BAD_PROXIES_FILE, [])
    return good, bad

def save_saved_proxies(good, bad):
    save_json(GOOD_PROXIES_FILE, good)
    save_json(BAD_PROXIES_FILE, bad)

def main(max_to_test_new=30, retest_saved=True, retest_saved_limit=100):
    good_saved, bad_saved = load_saved_proxies()
    print(f"Загружено сохранённых рабочих прокси: {len(good_saved)}, нерабочих: {len(bad_saved)}")
    new_proxies = gather_proxies(SOURCES)
    combined = []
    seen = set()
    for p in good_saved + new_proxies:
        key = f"{p['ip']}:{p['port']}"
        if key not in seen:
            seen.add(key)
            combined.append(p)
    to_test = []
    if retest_saved:
        to_test.extend(good_saved)
    to_test.extend([p for p in combined if f"{p['ip']}:{p['port']}" not in {f'{x["ip"]}:{x["port"]}' for x in to_test}][:max_to_test_new])
    if retest_saved_limit:
        to_test = to_test[:retest_saved_limit]
    print(f"Буду тестировать {len(to_test)} прокси.")

    good = []
    bad = []
    for i, p in enumerate(to_test, 1):
        ipport = f"{p['ip']}:{p['port']} ({p.get('country','?')})"
        print(f"[{i}/{len(to_test)}] Тестирую {ipport} ...", end=" ")
        ok, info = test_proxy(p, timeout=6)
        if ok:
            print("OK")
            p2 = dict(p)
            p2['last_ok'] = now_iso()
            p2['test_info'] = info
            good.append(p2)
        else:
            print("FAIL")
            p2 = dict(p)
            p2['last_fail'] = now_iso()
            p2['fail_info'] = info
            bad.append(p2)
        time.sleep(0.3)

    good_final = []
    seen = set()
    for p in good:
        key = f"{p['ip']}:{p['port']}"
        if key not in seen:
            seen.add(key)
            good_final.append(p)
    if not retest_saved or len(good) < len(good_saved):
        for p in good_saved:
            key = f"{p['ip']}:{p['port']}"
            if key not in seen:
                seen.add(key)
                good_final.append(p)

    bad_final = []
    seen_bad = set()
    for p in bad + bad_saved:
        key = f"{p['ip']}:{p['port']}"
        if key not in seen_bad:
            seen_bad.add(key)
            bad_final.append(p)

    save_saved_proxies(good_final, bad_final)
    save_json(DEAD_SOURCES_FILE, dead_sources)
    save_json(SOURCE_FAILS_FILE, source_fail_counts)

    print(f"\nИтого рабочих прокси сохранено: {len(good_final)}")
    print(f"Итого нерабочих прокси сохранено: {len(bad_final)}")

    if good_final:
        print("\nПримеры рабочих прокси:")
        for p in good_final[:10]:
            print(f"  {p['ip']}:{p['port']}  страна={p.get('country','?')} источник={p.get('source','?')} last_ok={p.get('last_ok','?')}")
    else:
        print("Рабочих прокси не найдено.")

if __name__ == "__main__":
    main(max_to_test_new=30, retest_saved=True, retest_saved_limit=120)
