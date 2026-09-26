import csv, io, json, os, unicodedata
import streamlit as st
from gradio_client import Client

st.set_page_config(page_title="POI Search-Term Classifier", layout="wide")

def norm(v):
    s = unicodedata.normalize("NFKD", str(v).lower())
    return "".join(c for c in s if not unicodedata.combining(c))

def terms(v): return [norm(x.strip()) for x in v.split(",") if x.strip()]
def hit(s, xs): return next((x for x in xs if x and x in s), None)

def exact(term, c):
    s = norm(term); attraction = hit(s, [norm(c["attraction"]), *c["aliases"]])
    related = hit(s, c["related"]); reseller = hit(s, c["resellers"]); info = hit(s, c["info"]); buy = hit(s, c["purchase"])
    if related: return "Clear exclude", f"Related attraction or combination: {related}"
    if reseller: return "Clear exclude", f"Other booking provider: {reseller}"
    if "official" in s or "direct operator" in s: return "Clear exclude", "Official/direct-operator intent"
    if info and not buy: return "Clear exclude", f"Informational intent: {info}"
    if attraction and buy: return "Clear keep", f"Main attraction plus purchase signal: {buy}"
    return "Needs semantic triage", "No exact rule decided this term"

def questions(c):
    products = ", ".join(c["products"]) or "entry tickets and experiences"
    return {"experience": {"type": "choice", "instructions": f"Which experience does this search term seek? The campaign sells {c['attraction']}; products include {products}.", "criteria": {"main_only": f"{c['attraction']} only", "combo": f"{c['attraction']} with another attraction, cruise, tour, or pass", "other": "Another attraction or experience", "unclear": "Cannot determine"}}, "intent": {"type": "choice", "instructions": "What is the user's intent?", "criteria": {"purchase": "Tickets, prices, booking, availability, discounts, or a paid experience", "information": "Hours, duration, directions, facts, reviews, photos, or general information", "support": "Existing booking, cancellation, refund, login, or customer service", "unclear": "Cannot determine"}}}

@st.cache_resource
def laya_client(url): return Client(url.rstrip("/"))

def laya_batch(url, batch, q):
    raw = laya_client(url).predict(json.dumps(batch, ensure_ascii=False), json.dumps(q, ensure_ascii=False), api_name="/predict_batch")
    data = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(data, dict) and "error" in data: raise RuntimeError(data["error"])
    return data

st.title("Point-of-Interest Search-Term Classifier")
st.caption("Exact rules decide obvious terms. Laya reviews unresolved terms in batches through Hugging Face.")
with st.sidebar:
    st.header("Campaign settings")
    attraction = st.text_input("Main attraction", "London Eye")
    aliases = st.text_area("Attraction aliases", "london eye, eye of london, londoneye")
    products = st.text_area("Landing-page products", "entry tickets, fast-track tickets, 30-minute ride, champagne experience")
    related = st.text_area("Related attractions / combinations", "Madame Tussauds, SEA LIFE, Thames cruise, London Dungeon, Shrek's Adventure, Big Bus")
    resellers = st.text_area("Reseller names", "GetYourGuide, Viator, Klook, Tiqets, Golden Tours, Groupon, Booking.com")
    info = st.text_area("Informational phrases", "opening times, hours, duration, directions, reviews, facts, photos, address, where is")
    purchase = st.text_area("Purchase phrases", "ticket, tickets, book, booking, reservation, price, cost, discount, availability, fast track, experience")
    laya_url = st.text_input("Laya service URL", os.environ.get("LAYA_API_URL", "https://gokul0303-poi-laya-judge.hf.space"))
    use_laya = st.checkbox("Send unresolved terms to Laya", True)
c = {"attraction": attraction, "aliases": terms(aliases), "products": terms(products), "related": terms(related), "resellers": terms(resellers), "info": terms(info), "purchase": terms(purchase)}
up = st.file_uploader("Upload a search-term CSV", type=["csv"])
if up:
    reader = csv.DictReader(io.StringIO(up.getvalue().decode("utf-8-sig", errors="replace"))); rows = list(reader)
    if not rows: st.error("CSV is empty"); st.stop()
    key = next((k for k in reader.fieldnames if norm(k) in {"search term", "term", "keyword"}), reader.fieldnames[0])
    rows = [r for r in rows if norm(r.get(key, "")).strip() not in {"grand total", "total"}]
    unique = list(dict.fromkeys(r.get(key, "") for r in rows)); results = {}; bar = st.progress(0.0)
    unresolved = []
    for term in unique:
        route, reason = exact(term, c); rec = "Review"
        if route == "Clear keep": rec = "Keep candidate"
        elif route == "Clear exclude": rec = "Exclude candidate"
        else: unresolved.append(term)
        results[term] = (route, rec, reason)
    if use_laya and unresolved:
        q = questions(c)
        for start in range(0, len(unresolved), 32):
            batch = unresolved[start:start + 32]
            try:
                answers = laya_batch(laya_url, batch, q)
                for term, item in zip(batch, answers):
                    a = item.get("answers", item); exp = a["experience"]["choice"]; intent = a["intent"]["choice"]
                    rec = "Review — proposed exclude" if exp in ("combo", "other") or intent in ("information", "support") else "Review — proposed keep" if exp == "main_only" and intent == "purchase" else "Review"
                    results[term] = ("Laya semantic triage", rec, f"Laya experience={exp}; intent={intent}")
            except Exception as e:
                for term in batch: results[term] = ("Needs semantic triage", "Review", f"Laya unavailable: {e}")
            bar.progress(min(1.0, (start + len(batch)) / max(1, len(unique))))
    else: bar.progress(1.0)
    out = []
    for r in rows:
        route, rec, reason = results[r.get(key, "")]; x = dict(r); x.update({"Final route": route, "Recommendation": rec, "Reason": reason, "Your decision": ""}); out.append(x)
    st.success(f"Classified {len(rows):,} rows and {len(unique):,} unique terms.")
    st.dataframe(out, use_container_width=True, height=520)
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    st.download_button("Download classifications", buf.getvalue().encode(), "poi-search-term-classifications.csv", "text/csv")
else: st.info("Upload a search-term CSV to begin.")
