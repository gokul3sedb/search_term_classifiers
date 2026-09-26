import csv, io, os, unicodedata
import streamlit as st
st.set_page_config(page_title="POI Search-Term Classifier", layout="wide")
def norm(x):
    s=unicodedata.normalize("NFKD",str(x).lower())
    return "".join(c for c in s if not unicodedata.combining(c))
def terms(x): return [norm(v.strip()) for v in x.split(",") if v.strip()]
def hit(s, xs): return next((x for x in xs if x and x in s), None)
def exact(term,c):
    s=norm(term); aliases=[norm(c["attraction"]),*c["aliases"]]
    a=hit(s,aliases); rel=hit(s,c["related"]); seller=hit(s,c["resellers"]); info=hit(s,c["info"]); buy=hit(s,c["purchase"])
    if rel: return "Clear exclude",f"Related attraction or combination: {rel}"
    if seller: return "Clear exclude",f"Other booking provider: {seller}"
    if "official" in s or "direct operator" in s: return "Clear exclude","Explicit official/direct-operator intent"
    if info and not buy: return "Clear exclude",f"Informational intent: {info}"
    if a and buy: return "Clear keep",f"Main attraction plus purchase signal: {buy}"
    return "Needs semantic triage","No exact rule decided this term"
def questions(c):
    products=", ".join(c["products"]) or "entry tickets and experiences"
    return {"experience":{"type":"choice","instructions":f"Which experience does this search term seek? The campaign sells {c['attraction']}; products include {products}.","criteria":{"main_only":f"{c['attraction']} only","combo":f"{c['attraction']} with another attraction, cruise, tour, or pass","other":"Another attraction or experience","unclear":"Cannot determine"}},"intent":{"type":"choice","instructions":"What is the user's intent?","criteria":{"purchase":"Tickets, prices, booking, availability, discounts, or a paid experience","information":"Hours, duration, directions, facts, reviews, photos, or general information","support":"Existing booking, cancellation, refund, login, or customer service","unclear":"Cannot determine"}}}
@st.cache_resource(show_spinner="Loading Laya semantic judge...")
def get_laya_router():
    from laya import Router
    return Router()

st.title("Point-of-Interest Search-Term Classifier")
st.caption("Exact rules handle literal facts. Enable Laya only when the cloud instance has enough memory for the model checkpoint.")
with st.sidebar:
    st.header("Campaign settings")
    attraction=st.text_input("Main attraction","London Eye")
    aliases=st.text_area("Attraction aliases","london eye, eye of london, londoneye")
    products=st.text_area("Landing-page products","entry tickets, fast-track tickets, 30-minute ride, champagne experience")
    related=st.text_area("Related attractions / combinations","Madame Tussauds, SEA LIFE, Thames cruise, London Dungeon, Shrek's Adventure, Big Bus")
    resellers=st.text_area("Reseller names","GetYourGuide, Viator, Klook, Tiqets, Golden Tours, Groupon, Booking.com")
    info=st.text_area("Informational phrases","opening times, hours, duration, directions, reviews, facts, photos, address, where is")
    purchase=st.text_area("Purchase phrases","ticket, tickets, book, booking, reservation, price, cost, discount, availability, fast track, experience")
    use_laya=st.checkbox("Run Laya semantic judge on unresolved terms",False)
c={"attraction":attraction,"aliases":terms(aliases),"products":terms(products),"related":terms(related),"resellers":terms(resellers),"info":terms(info),"purchase":terms(purchase)}
up=st.file_uploader("Upload a search-term CSV",type=["csv"])
if up:
    text=up.getvalue().decode("utf-8-sig",errors="replace"); reader=csv.DictReader(io.StringIO(text)); rows=list(reader)
    if not rows: st.error("CSV is empty"); st.stop()
    before=len(rows); rows=[r for r in rows if norm(r.get(next((k for k in reader.fieldnames if norm(k) in {"search term","term","keyword"}),reader.fieldnames[0]),"")).strip() not in {"grand total","total"}]
    removed_summary=before-len(rows)
    if removed_summary: st.info(f"Removed {removed_summary:,} summary row(s) before classification.")
    key=next((k for k in reader.fieldnames if norm(k) in {"search term","term","keyword"}),reader.fieldnames[0])
    agent=None
    if use_laya:
        try: agent=get_laya_router()
        except Exception as e: st.error(f"Laya load failed: {e}")
    results={}; unique=list(dict.fromkeys(r.get(key,"") for r in rows)); bar=st.progress(0.0)
    for i,t in enumerate(unique):
        route,reason=exact(t,c); rec="Review"
        if route=="Clear keep": rec="Keep candidate"
        elif route=="Clear exclude": rec="Exclude candidate"
        elif agent:
            a=agent.predict(t,questions(c))["answers"]; exp=a["experience"]["choice"]; intent=a["intent"]["choice"]; route="Laya semantic triage"; reason=f"Laya experience={exp}; intent={intent}"
            rec="Review — proposed exclude" if exp in ("combo","other") or intent in ("information","support") else "Review — proposed keep" if exp=="main_only" and intent=="purchase" else "Review"
        results[t]=(route,rec,reason); bar.progress((i+1)/len(unique))
    out=[]
    for r in rows:
        route,rec,reason=results[r.get(key,"")]; x=dict(r); x.update({"Final route":route,"Recommendation":rec,"Reason":reason,"Your decision":""}); out.append(x)
    st.success(f"Classified {len(rows):,} rows and {len(unique):,} unique terms.")
    st.dataframe(out,use_container_width=True,height=520)
    buf=io.StringIO(); w=csv.DictWriter(buf,fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    st.download_button("Download classifications",buf.getvalue().encode(),"poi-search-term-classifications.csv","text/csv")
else: st.info("Upload a search-term CSV to begin.")
