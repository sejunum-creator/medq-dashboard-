import os, json, re, datetime, urllib.request, urllib.error

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
QID_DB = "a42e0f38b08882ac9934811dfe9d9912"
MEDQ_DB = "3152de0a0f0a80249ed8e5289d18757d"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def notion_query(database_id):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    rows = []
    payload = {"page_size": 100}
    while True:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        rows.extend(result["results"])
        if not result.get("has_more"):
            break
        payload["start_cursor"] = result["next_cursor"]
    return rows


def prop_text(prop):
    if not prop:
        return ""
    t = prop["type"]
    if t == "title":
        return "".join(rt.get("plain_text", "") for rt in prop["title"])
    if t == "rich_text":
        return "".join(rt.get("plain_text", "") for rt in prop["rich_text"])
    if t == "select":
        return prop["select"]["name"] if prop["select"] else ""
    if t == "multi_select":
        return ", ".join(s["name"] for s in prop["multi_select"])
    if t == "number":
        return str(prop["number"]) if prop["number"] is not None else ""
    if t == "formula":
        f = prop["formula"]
        ft = f.get("type", "")
        if ft == "string":
            return f.get("string") or ""
        if ft == "number":
            return str(f.get("number", ""))
        return ""
    if t == "rollup":
        r = prop["rollup"]
        if r.get("type") == "array":
            parts = []
            for item in r.get("array", []):
                parts.append(prop_text(item))
            return ", ".join(filter(None, parts))
        return ""
    if t == "status":
        return prop["status"]["name"] if prop["status"] else ""
    return ""


def build():
    print("Fetching QID Index...")
    qid_raw = notion_query(QID_DB)
    print(f"  {len(qid_raw)} rows")

    print("Fetching MedQ Database...")
    medq_raw = notion_query(MEDQ_DB)
    print(f"  {len(medq_raw)} rows")

    qid_rows = []
    for page in qid_raw:
        p = page["properties"]
        qid_rows.append({
            "src": prop_text(p.get("원본 출처", {})).strip(),
            "cat": prop_text(p.get("구분", {})).strip(),
            "l1": prop_text(p.get("L1 대분류", {})).strip(),
            "l1m": prop_text(p.get("L1 중분류", {})).strip(),
            "l1s": prop_text(p.get("L1 소분류", {})).strip(),
            "qid": prop_text(p.get("QID", {})).strip(),
        })

    medq_by_source = {}
    for page in medq_raw:
        p = page["properties"]
        src = prop_text(p.get("L5 소스", {})).strip()
        if src:
            entry = {
                "id": prop_text(p.get("문제번호(ID)", {})).strip(),
                "status": prop_text(p.get("작업 상태", {})).strip(),
            }
            medq_by_source.setdefault(src, []).append(entry)

    data = []
    done_count = 0
    for r in qid_rows:
        src = r["src"]
        m = re.match(r"(\d{4})", src)
        year = m.group(1) if m else ""

        entries = medq_by_source.get(src, [])
        has_extract_only = entries and all(e["status"] == "추출" for e in entries)
        has_non_extract = entries and any(e["status"] != "추출" for e in entries)

        if has_extract_only:
            status = ""
            medq_id = ""
        elif has_non_extract:
            status = "완료"
            medq_id = next(e["id"] for e in entries if e["status"] != "추출")
            done_count += 1
        elif r["qid"]:
            status = "완료"
            medq_id = r["qid"]
            done_count += 1
        else:
            status = ""
            medq_id = ""

        data.append([src, year, r["cat"], r["l1"], r["l1m"], r["l1s"], r["qid"], medq_id, status])

    print(f"Total: {len(data)}, Done: {done_count}, Pending: {len(data) - done_count}")

    years = sorted(set(r[1] for r in data if r[1]), reverse=True)
    l1s_seen = []
    for r in data:
        if r[3] and r[3] not in l1s_seen:
            l1s_seen.append(r[3])

    today = datetime.date.today().isoformat()

    with open("template.html", "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("__DATA_PLACEHOLDER__", json.dumps(data, ensure_ascii=False))
    html = html.replace("__YEARS_PLACEHOLDER__", json.dumps(years, ensure_ascii=False))
    html = html.replace("__L1S_PLACEHOLDER__", json.dumps(l1s_seen, ensure_ascii=False))
    html = html.replace("__DATE_PLACEHOLDER__", today)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Built index.html ({len(html)} bytes) - {today}")


if __name__ == "__main__":
    build()
