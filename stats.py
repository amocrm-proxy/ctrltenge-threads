# Статистика постов Threads (только чтение): просмотры и реакции по каждому опубликованному посту
import json, urllib.parse, urllib.request
import th_token
TOKEN = th_token.get()
def get(path, **p):
    p["access_token"] = TOKEN
    with urllib.request.urlopen(f"https://graph.threads.net/v1.0/{path}?" + urllib.parse.urlencode(p), timeout=30) as r:
        return json.load(r)
st = json.load(open("state.json"))["posted"]
rows = []
for pid, v in st.items():
    m = {"views": 0, "likes": 0, "replies": 0, "reposts": 0, "quotes": 0, "shares": 0}
    try:
        d = get(f"{v['media_id']}/insights", metric="views,likes,replies,reposts,quotes,shares")
        for x in d.get("data", []):
            m[x["name"]] = x.get("values", [{}])[0].get("value", x.get("total_value", {}).get("value", 0))
    except Exception as e:
        m["err"] = str(e)[:80]
    rows.append((v["at"], pid, m))
for at, pid, m in sorted(rows):
    print("ROW", at, pid, json.dumps(m, ensure_ascii=False))
try:
    me = get("me", fields="id,username"); uid = me["id"]
    f = get(f"{uid}/threads_insights", metric="followers_count")
    print("FOLLOWERS", json.dumps(f.get("data", []), ensure_ascii=False)[:300])
except Exception as e:
    print("FOLLOWERS_ERR", str(e)[:120])
