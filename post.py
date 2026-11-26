"""Автопостинг Ctrl + ₸ в Threads.
Каждый час GitHub запускает этот скрипт. Он берёт из posts.json самый ранний пост,
у которого дата и время (Алматы) уже наступили и который ещё не опубликован, и публикует его.
За один запуск — не больше одного поста. Пост, опоздавший больше чем на 36 часов, пропускается.
Перед публикацией проверяется, что ключ принадлежит аккаунту EXPECT_USERNAME (ctrl.tenge),
чтобы случайно не опубликовать в чужой аккаунт.
DRY=1 — тест: проверяет ключ и показывает, что опубликовал бы, но ничего не публикует.
"""
import base64, datetime, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from zoneinfo import ZoneInfo
import th_token

API = "https://graph.threads.net/v1.0"
TZ = ZoneInfo("Asia/Almaty")
EXPECT = os.environ.get("EXPECT_USERNAME", "ctrl.tenge").lower()
DRY = os.environ.get("DRY", "") == "1"
REPO = os.environ.get("GITHUB_REPOSITORY", "")
GH_HDR = {"Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}", "Accept": "application/vnd.github+json"}
TOKEN = th_token.get()

def http(method, url, data=None, headers=None):
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = f"Ошибка {method} {url.split('?')[0]} {e.code}: {e.read().decode()}"
            if e.code >= 500 and attempt < 3:
                print(msg, "— повтор через 30 с"); time.sleep(30); continue
            sys.exit(msg)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 3:
                print("Сеть:", e, "— повтор через 30 с"); time.sleep(30); continue
            sys.exit(f"Сеть: {e}")

def threads(method, path, **params):
    params["access_token"] = TOKEN
    q = urllib.parse.urlencode(params)
    if method == "GET":
        return http("GET", f"{API}/{path}?{q}")
    return http("POST", f"{API}/{path}", data=q.encode())

def put_file(path, raw, message):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    payload = {"message": message, "content": base64.b64encode(raw).decode()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url + "?ref=main", headers=GH_HDR), timeout=30) as r:
            payload["sha"] = json.load(r)["sha"]
    except urllib.error.HTTPError:
        pass
    http("PUT", url, data=json.dumps(payload).encode(), headers=GH_HDR)

def save_state(state, msg):
    put_file("state.json", json.dumps(state, ensure_ascii=False, indent=1).encode(), msg)

me = threads("GET", "me", fields="id,username")
print("Аккаунт по ключу:", me.get("username"))
if (me.get("username") or "").lower() != EXPECT:
    sys.exit(f"СТОП: ключ от аккаунта {me.get('username')}, а ожидается {EXPECT}. Ничего не публикую.")

now = datetime.datetime.now(TZ)
state = json.load(open("state.json", encoding="utf-8")) if os.path.exists("state.json") else {}
state.setdefault("posted", {}); state.setdefault("skipped", {})
posts = json.load(open("posts.json", encoding="utf-8"))

week = now.strftime("%G-W%V")
if not DRY and state.get("refresh_week") != week:            # раз в неделю продлеваем ключ (живёт 60 дней)
    try:
        TOKEN = th_token.refresh(put_file)
        state["refresh_week"] = week
        save_state(state, f"th_refresh {week}")
    except BaseException as e:
        print("Ключ Threads продлить не удалось:", e)

due = []
for p in posts:
    if p["id"] in state["posted"] or p["id"] in state["skipped"]:
        continue
    at = datetime.datetime.fromisoformat(f"{p['date']}T{p['time']}").replace(tzinfo=TZ)
    if at <= now:
        due.append((at, p))
due.sort(key=lambda x: x[0])

fresh = []
for at, p in due:
    if now - at > datetime.timedelta(hours=36):
        print(f"Пропуск (опоздал больше чем на 36 ч): {p['id']}")
        if not DRY:
            state["skipped"][p["id"]] = now.isoformat(timespec="minutes")
    else:
        fresh.append((at, p))

if not fresh:
    print("Сейчас публиковать нечего.")
    nxt = [p for p in posts if p["id"] not in state["posted"] and p["id"] not in state["skipped"]]
    print("Осталось в очереди:", len(nxt))
    if not DRY and state["skipped"]:
        save_state(state, "skipped")
    sys.exit(0)

at, p = fresh[0]
text = p["text"].strip()
if len(text) > 500:
    sys.exit(f"СТОП: пост {p['id']} длиннее 500 знаков ({len(text)}).")
REPO = os.environ.get("GITHUB_REPOSITORY", "amocrm-proxy/ctrltenge-threads")
def media_url(path):
    return f"https://raw.githubusercontent.com/{REPO}/main/{urllib.parse.quote(path)}"
def reachable(url):                       # Threads берёт файлы только по публичной ссылке
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as r:
            return r.status == 200
    except Exception:
        return False
def kind(path):
    return "VIDEO" if path.lower().endswith((".mp4", ".mov")) else "IMAGE"
def wait_ready(cid, label):               # видео Threads обрабатывает не сразу
    for _ in range(40):
        st = threads("GET", cid, fields="status,error_message")
        if st.get("status") == "FINISHED":
            return
        if st.get("status") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"{label}: {st}")
        time.sleep(10)
    raise RuntimeError(f"{label}: не дождались обработки")

media = [m for m in p.get("media", [])]
urls = [media_url(m) for m in media]
if urls and not all(reachable(u) for u in urls):
    print("ВНИМАНИЕ: медиа недоступны по публичной ссылке (репозиторий закрыт?) — публикую только текст.")
    media, urls = [], []
print(f"Публикую {p['id']} ({p['date']} {p['time']}):\n{text}\nМедиа: {urls or 'нет'}\n")
if DRY:
    print("DRY: тест, не публикую."); sys.exit(0)

if not media:
    c = threads("POST", "me/threads", media_type="TEXT", text=text)
    time.sleep(5)
elif len(media) == 1:
    k = kind(media[0])
    c = threads("POST", "me/threads", media_type=k, text=text, **({"video_url": urls[0]} if k == "VIDEO" else {"image_url": urls[0]}))
    wait_ready(c["id"], media[0])
else:
    kids = []
    for m, u in zip(media[:20], urls[:20]):
        k = kind(m)
        ch = threads("POST", "me/threads", media_type=k, is_carousel_item="true", **({"video_url": u} if k == "VIDEO" else {"image_url": u}))
        wait_ready(ch["id"], m); kids.append(ch["id"])
    c = threads("POST", "me/threads", media_type="CAROUSEL", children=",".join(kids), text=text)
    wait_ready(c["id"], "carousel")
r = threads("POST", "me/threads_publish", creation_id=c["id"])
state["posted"][p["id"]] = {"at": now.isoformat(timespec="minutes"), "media_id": r.get("id")}
save_state(state, f"posted {p['id']}")
print("Опубликовано, id:", r.get("id"))
left = [x for x in posts if x["id"] not in state["posted"] and x["id"] not in state["skipped"]]
print("Осталось в очереди:", len(left))
if len(left) <= 3:
    print("ВНИМАНИЕ: в очереди осталось мало постов — пора добавить новую пачку.")
