# Проверка: примет ли Threads видео из media/. Создаёт контейнер БЕЗ публикации и ждёт обработки.
import json, sys, time, urllib.parse, urllib.request
import th_token
TOKEN = th_token.get()
def call(method, path, **p):
    p["access_token"] = TOKEN; q = urllib.parse.urlencode(p)
    req = urllib.request.Request(f"https://graph.threads.net/v1.0/{path}" + (f"?{q}" if method == "GET" else ""), data=None if method == "GET" else q.encode(), method=method)
    with urllib.request.urlopen(req, timeout=60) as r: return json.load(r)
f = sys.argv[1] if len(sys.argv) > 1 else "media/salon.mp4"
url = "https://raw.githubusercontent.com/amocrm-proxy/ctrltenge-threads/main/" + f
c = call("POST", "me/threads", media_type="VIDEO", video_url=url, text="test")
for _ in range(30):
    st = call("GET", c["id"], fields="status,error_message"); print("STATUS", st)
    if st.get("status") in ("FINISHED", "ERROR", "EXPIRED"): break
    time.sleep(10)
