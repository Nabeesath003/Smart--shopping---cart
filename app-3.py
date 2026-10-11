import html
import math
import re
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="SmartCart | Smart Shopping Assistant",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

CATALOGUE_FILE = Path(__file__).with_name("smartcart_catalogue.csv")
PAGE_SIZE = 20
COLUMNS = 4
AVAILABLE = ("in stock", "low stock")

# ---------- Fallback demo catalogue (used only if smartcart_catalogue.csv is missing) ----------
DEFAULT_PRODUCTS = [
    {"product_id":"MILK001","product_name":"Taaza Toned Milk","brand":"Amul","category":"Dairy and Eggs","pack_size":"1 L","price":68.00,"stock_status":"In stock","aisle":"B1"},
    {"product_id":"MILK002","product_name":"Toned Milk","brand":"Milma","category":"Dairy and Eggs","pack_size":"1 L","price":56.00,"stock_status":"In stock","aisle":"B1"},
    {"product_id":"BISC001","product_name":"Marie Gold Biscuits","brand":"Britannia","category":"Snacks and Packaged Foods","pack_size":"250 g","price":38.00,"stock_status":"In stock","aisle":"E2"},
    {"product_id":"BISC002","product_name":"Marie Biscuits","brand":"Parle","category":"Snacks and Packaged Foods","pack_size":"250 g","price":32.00,"stock_status":"In stock","aisle":"E2"},
    {"product_id":"RICE001","product_name":"Raw Rice","brand":"Store Brand","category":"Rice, Flour and Pulses","pack_size":"5 kg","price":310.00,"stock_status":"In stock","aisle":"C1"},
]

REQUIRED_COLUMNS = [
    "product_id", "product_name", "brand", "category",
    "pack_size", "price", "stock_status", "aisle",
]


def prepare_catalogue(df):
    df = df.copy()
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    for col in ["product_id", "product_name", "brand", "category", "pack_size", "stock_status", "aisle"]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["stock_status"] = df["stock_status"].replace("", "In stock")
    df["aisle"] = df["aisle"].replace("", "-")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["price"])
    df = df[(df["price"] >= 0) & (df["product_id"] != "") & (df["product_name"] != "")]
    df = df.drop_duplicates(subset=["product_id"], keep="first")
    df["unit_price"] = df.apply(
        lambda r: f"₹{r['price']:.2f} / {r['pack_size']}" if r["pack_size"] else f"₹{r['price']:.2f} / pack",
        axis=1,
    )
    return df.reset_index(drop=True)


def load_default_catalogue():
    if CATALOGUE_FILE.exists():
        try:
            df = prepare_catalogue(pd.read_csv(CATALOGUE_FILE))
            if not df.empty:
                return df
        except Exception:
            pass
    return prepare_catalogue(pd.DataFrame(DEFAULT_PRODUCTS))


def rupees(amount):
    return f"₹{amount:,.2f}"


def price_label(amount):
    amount = float(amount)
    return f"₹{amount:,.0f}" if amount == int(amount) else f"₹{amount:,.2f}"


# ---------- State ----------
if "catalogue" not in st.session_state:
    st.session_state.catalogue = load_default_catalogue()
if "cart" not in st.session_state:
    st.session_state.cart = {}
if "budget" not in st.session_state:
    st.session_state.budget = 2000.0
if "page" not in st.session_state:
    st.session_state.page = 1


def product_by_id(pid):
    cat = st.session_state.catalogue
    rows = cat[cat["product_id"] == pid]
    return None if rows.empty else rows.iloc[0]


def cart_total():
    total = 0.0
    for pid, qty in st.session_state.cart.items():
        p = product_by_id(pid)
        if p is not None:
            total += float(p["price"]) * int(qty)
    return total


STOP_WORDS = {"and", "the", "with", "pack", "fresh", "powder", "small", "large", "whole", "regular"}


def name_words(text):
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in STOP_WORDS}


def cheaper_alternatives(p, qty=1):
    cat = st.session_state.catalogue
    pool = cat[
        (cat["category"] == p["category"])
        & (cat["price"] < p["price"])
        & (cat["stock_status"].str.lower().isin(AVAILABLE))
    ]
    words = name_words(p["product_name"])
    pool = pool[pool["product_name"].apply(lambda n: bool(name_words(n) & words))]
    room = st.session_state.budget - cart_total()
    pool = pool[pool["price"] * qty <= room]
    return pool.sort_values("price").head(3)


def add_item(pid, qty=1):
    p = product_by_id(pid)
    if p is None:
        return False
    proposed = cart_total() + float(p["price"]) * qty
    budget = st.session_state.budget
    if proposed <= budget + 1e-9:
        st.session_state.cart[pid] = min(st.session_state.cart.get(pid, 0) + qty, 99)
        return True
    alts = cheaper_alternatives(p, qty)
    st.session_state.notice = {
        "msg": f"Adding {p['product_name']} would make your bill {rupees(proposed)}, "
               f"which is {rupees(proposed - budget)} over your budget.",
        "alts": [
            f"{a['brand']} · {a['product_name']} ({a['pack_size']}): {rupees(float(a['price']))}, "
            f"saves {rupees(float(p['price']) - float(a['price']))} per item"
            for _, a in alts.iterrows()
        ],
    }
    return False


def change_qty(pid, delta):
    qty = st.session_state.cart.get(pid, 0) + delta
    if qty <= 0:
        st.session_state.cart.pop(pid, None)
    else:
        st.session_state.cart[pid] = min(qty, 99)


def add_by_code():
    code = st.session_state.get("code_input", "").strip().upper()
    st.session_state.code_input = ""
    if not code:
        return
    cat = st.session_state.catalogue
    match = cat[cat["product_id"].str.upper() == code]
    if match.empty:
        st.session_state.code_msg = ("err", f"No product has the code {code}.")
        return
    p = match.iloc[0]
    if str(p["stock_status"]).lower() not in AVAILABLE:
        st.session_state.code_msg = ("err", f"{p['product_name']} is not available right now.")
        return
    if add_item(p["product_id"], 1):
        st.session_state.code_msg = ("ok", f"Added {p['product_name']} ({p['pack_size']}).")


def reset_page():
    st.session_state.page = 1


# ---------- Styling ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@500&display=swap');
.stApp { font-family: 'DM Sans', system-ui, sans-serif; }
h1, h2, h3, .brand { font-family: 'Bricolage Grotesque', 'Trebuchet MS', sans-serif !important; letter-spacing: -.02em; }
.head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: .5rem; }
.brand { font-weight: 800; font-size: 2rem; color: #17221b; }
.sub { color: #5d6b61; font-size: .9rem; }
div[data-testid="stMetric"] { background: #ffffff; border: 1px solid #dde3da; border-radius: 10px; padding: 10px 14px; }
.tile { height: 58px; border-radius: 6px; display: flex; align-items: flex-end; justify-content: space-between;
        padding: 6px 8px; margin-bottom: 8px;
        background: hsl(var(--h) 38% 88%); color: hsl(var(--h) 45% 28%); }
.tile b { font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.5rem; line-height: 1; }
.tile span, .pcode { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: .7rem; }
.pname { font-weight: 700; font-size: .95rem; line-height: 1.25; min-height: 2.4em; color: #17221b; overflow-wrap: anywhere; }
.pmeta { color: #5d6b61; font-size: .8rem; }
.pcode { color: #5d6b61; margin-bottom: 6px; }
.price { background: #ffd84a; color: #2a2200; font-family: 'Bricolage Grotesque', sans-serif; font-weight: 800;
         font-size: 1.1rem; padding: 2px 9px; border-radius: 4px; display: inline-block; }
.low { color: #b25b00; font-size: .78rem; font-weight: 700; margin-left: 6px; }
.out { color: #c0392b; font-size: .78rem; font-weight: 700; margin-left: 6px; }
.qty { text-align: center; font-weight: 700; padding-top: .35rem; }
.aisle { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: .78rem; letter-spacing: .06em;
         text-transform: uppercase; color: #5d6b61; border-bottom: 1px solid #dde3da; padding-bottom: 4px; margin: 14px 0 6px; }
</style>
""", unsafe_allow_html=True)

# ---------- Sidebar ----------
with st.sidebar:
    st.header("Shopping setup")
    st.number_input("Set your budget (₹)", min_value=1.0, max_value=1000000.0, step=100.0, key="budget")
    st.caption("Sample catalogue for demonstration. Prices are illustrative, not live store prices.")
    st.divider()
    st.subheader("Catalogue tools")
    uploaded = st.file_uploader("Upload your product CSV", type=["csv"])
    if uploaded is not None:
        sig = (uploaded.name, uploaded.size)
        if st.session_state.get("loaded_sig") != sig:
            try:
                incoming = prepare_catalogue(pd.read_csv(uploaded))
                if incoming.empty:
                    st.error("No valid product rows found. Check your CSV columns and prices.")
                else:
                    st.session_state.catalogue = incoming
                    st.session_state.loaded_sig = sig
                    reset_page()
                    st.success(f"Loaded {len(incoming)} products.")
            except Exception as exc:
                st.error(f"Could not read CSV: {exc}")
    if st.button("Restore full catalogue", use_container_width=True):
        st.session_state.catalogue = load_default_catalogue()
        st.session_state.cart = {}
        st.session_state.pop("loaded_sig", None)
        reset_page()
        st.rerun()

catalogue = st.session_state.catalogue
valid_ids = set(catalogue["product_id"].tolist())
st.session_state.cart = {pid: q for pid, q in st.session_state.cart.items() if pid in valid_ids}

# ---------- Header and budget ----------
budget = float(st.session_state.budget)
total = cart_total()
remaining = budget - total
percent = min(total / budget, 1.0) if budget else 0.0
item_count = sum(st.session_state.cart.values())

st.markdown(
    f'<div class="head"><span class="brand">SmartCart</span>'
    f'<span class="sub">Budget-aware smart shopping · {len(catalogue)} products · '
    f'{catalogue["category"].nunique()} categories</span></div>',
    unsafe_allow_html=True,
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Shopping budget", rupees(budget))
m2.metric("Live bill", rupees(total))
m3.metric("Remaining" if remaining >= 0 else "Over budget by", rupees(abs(remaining)))
m4.metric("Items in cart", item_count)
st.progress(percent, text=f"{percent * 100:.0f}% of your budget used")

if total > budget:
    st.error(f"Your cart is {rupees(total - budget)} over budget. Remove items or choose suitable alternatives.")
elif item_count and remaining <= budget * 0.10:
    st.warning("You're close to your budget limit. Check the total before adding more.")

tab_shop, tab_cart, tab_catalogue, tab_how = st.tabs(
    ["Shop", f"My cart ({item_count})", "Product catalogue", "How it works"]
)

# ---------- Shop ----------
with tab_shop:
    notice = st.session_state.pop("notice", None)
    if notice:
        st.warning(notice["msg"])
        if notice["alts"]:
            st.markdown("**Cheaper alternatives in the same category:**")
            for line in notice["alts"]:
                st.write("• " + line)
        else:
            st.info("No cheaper in-stock option fits your remaining budget. Lower the quantity or remove an item.")

    s1, s2, s3 = st.columns([3, 2, 2])
    search = s1.text_input(
        "Search by product, brand, aisle or code", placeholder="onion, pen, Amul, VEG-001",
        key="search", on_change=reset_page,
    )
    sort_by = s2.selectbox(
        "Sort by", ["Aisle order", "Name A to Z", "Price low to high", "Price high to low"], key="sort_by",
    )
    s3.text_input(
        "Add by product code", placeholder="VEG-001", key="code_input", on_change=add_by_code,
    )
    code_msg = st.session_state.pop("code_msg", None)
    if code_msg:
        (st.success if code_msg[0] == "ok" else st.error)(code_msg[1])

    categories = ["All"] + sorted(catalogue["category"].unique().tolist())
    if hasattr(st, "pills"):
        chosen = st.pills("Category", categories, default="All", key="cat", label_visibility="collapsed", on_change=reset_page)
        chosen = chosen or "All"
    else:
        chosen = st.selectbox("Category", categories, key="cat_select", on_change=reset_page)

    shown = catalogue.copy()
    if search.strip():
        q = search.strip().lower()
        hay = (shown["product_name"] + " " + shown["brand"] + " " + shown["category"] + " "
               + shown["product_id"] + " " + shown["aisle"]).str.lower()
        shown = shown[hay.str.contains(q, regex=False)]
    if chosen != "All":
        shown = shown[shown["category"] == chosen]

    if sort_by == "Name A to Z":
        shown = shown.sort_values("product_name")
    elif sort_by == "Price low to high":
        shown = shown.sort_values(["price", "product_name"])
    elif sort_by == "Price high to low":
        shown = shown.sort_values(["price", "product_name"], ascending=[False, True])
    else:
        shown = shown.sort_values(["aisle", "product_id"])

    st.caption(f"{len(shown)} of {len(catalogue)} products")
    if shown.empty:
        st.info("No products match. Try a different word or choose All categories.")
    else:
        pages = max(1, math.ceil(len(shown) / PAGE_SIZE))
        st.session_state.page = max(1, min(int(st.session_state.page), pages))
        if pages > 1:
            st.number_input("Page", min_value=1, max_value=pages, step=1, key="page")
        start = (st.session_state.page - 1) * PAGE_SIZE
        chunk = shown.iloc[start:start + PAGE_SIZE]

        hues = {c: (i * 47) % 360 for i, c in enumerate(sorted(catalogue["category"].unique()))}
        cart = st.session_state.cart
        for row_start in range(0, len(chunk), COLUMNS):
            cols = st.columns(COLUMNS)
            for col, (_, p) in zip(cols, chunk.iloc[row_start:row_start + COLUMNS].iterrows()):
                pid = p["product_id"]
                status = str(p["stock_status"])
                available = status.lower() in AVAILABLE
                flag = ""
                if status.lower() == "low stock":
                    flag = '<span class="low">Low stock</span>'
                elif not available:
                    flag = f'<span class="out">{html.escape(status)}</span>'
                with col.container(border=True):
                    st.markdown(
                        f'<div class="tile" style="--h:{hues.get(p["category"], 140)}">'
                        f'<b>{html.escape(p["product_name"][:1].upper())}</b><span>{html.escape(p["aisle"])}</span></div>'
                        f'<div class="pname">{html.escape(p["product_name"])}</div>'
                        f'<div class="pmeta">{html.escape(p["brand"])} · {html.escape(p["pack_size"])}</div>'
                        f'<div class="pcode">{html.escape(pid)}</div>'
                        f'<span class="price">{price_label(p["price"])}</span>{flag}',
                        unsafe_allow_html=True,
                    )
                    qty = cart.get(pid, 0)
                    if qty == 0:
                        st.button("Add", key=f"add_{pid}", on_click=add_item, args=(pid, 1),
                                  disabled=not available, use_container_width=True)
                    else:
                        a, b, c = st.columns(3)
                        a.button("−", key=f"dec_{pid}", on_click=change_qty, args=(pid, -1), use_container_width=True)
                        b.markdown(f'<div class="qty">{qty}</div>', unsafe_allow_html=True)
                        c.button("+", key=f"inc_{pid}", on_click=add_item, args=(pid, 1), use_container_width=True)

# ---------- Cart ----------
with tab_cart:
    st.subheader("Your cart, in aisle order")
    if not st.session_state.cart:
        st.info("Your cart is empty. Add products from the Shop tab or enter a product code.")
    else:
        rows = []
        for pid, qty in st.session_state.cart.items():
            p = product_by_id(pid)
            if p is None:
                continue
            rows.append({
                "Aisle": p["aisle"], "Product ID": p["product_id"], "Product": p["product_name"],
                "Brand": p["brand"], "Category": p["category"], "Pack size": p["pack_size"],
                "Qty": int(qty), "Unit price": float(p["price"]), "Line total": float(p["price"]) * int(qty),
            })
        bill_df = pd.DataFrame(rows).sort_values(["Aisle", "Product"]).reset_index(drop=True)

        lines = ["Picking list (by aisle)"]
        for aisle, grp in bill_df.groupby("Aisle", sort=True):
            label = "Unsorted" if aisle == "-" else f"Aisle {aisle} · {grp['Category'].iloc[0]}"
            st.markdown(f'<div class="aisle">{html.escape(label)}</div>', unsafe_allow_html=True)
            lines.append("\n" + label)
            for _, r in grp.iterrows():
                pid = r["Product ID"]
                a, b, c = st.columns([5, 2, 3])
                a.markdown(f"**{r['Product']}**")
                a.caption(f"{r['Brand']} · {r['Pack size']} · {rupees(r['Unit price'])} each")
                b.markdown(f"**{rupees(r['Line total'])}**")
                with c:
                    x, y, z = st.columns(3)
                    x.button("−", key=f"cdec_{pid}", on_click=change_qty, args=(pid, -1), use_container_width=True)
                    y.markdown(f'<div class="qty">{r["Qty"]}</div>', unsafe_allow_html=True)
                    z.button("+", key=f"cinc_{pid}", on_click=add_item, args=(pid, 1), use_container_width=True)
                lines.append(f"- {r['Product']} ({r['Pack size']}) x {r['Qty']}  Rs {r['Line total']:,.2f}")
        lines.append(f"\nTotal: Rs {total:,.2f}")

        st.divider()
        c1, c2 = st.columns(2)
        c1.metric("Total bill", rupees(total))
        c2.metric("Budget remaining" if remaining >= 0 else "Over budget by", rupees(abs(remaining)))
        d1, d2, d3 = st.columns(3)
        d1.download_button("Download bill (CSV)", data=bill_df.to_csv(index=False).encode("utf-8"),
                           file_name="smartcart_bill.csv", mime="text/csv", use_container_width=True)
        d2.download_button("Download picking list", data="\n".join(lines), file_name="picking_list.txt",
                           use_container_width=True)
        if d3.button("Clear cart", use_container_width=True):
            st.session_state.cart = {}
            st.rerun()

# ---------- Catalogue ----------
with tab_catalogue:
    st.subheader("Product catalogue")
    display_cols = ["product_id", "product_name", "brand", "category", "aisle", "pack_size", "price", "unit_price", "stock_status"]
    st.dataframe(catalogue[display_cols], use_container_width=True, hide_index=True)
    st.download_button(
        "Download product catalogue (CSV)",
        data=catalogue[display_cols].drop(columns=["unit_price"]).to_csv(index=False).encode("utf-8"),
        file_name="smartcart_product_catalogue.csv",
        mime="text/csv",
    )
    st.markdown("**CSV columns:** `product_id`, `product_name`, `brand`, `category`, `pack_size`, `price`, `stock_status`, and optional `aisle`.")
    st.caption("For exact unit-price comparisons across different pack sizes, store a normalised pack quantity and unit in the database.")

# ---------- How it works ----------
with tab_how:
    st.subheader("Project overview")
    st.markdown("""
    **Problem:** Shoppers lose track of their total while choosing among many products, brands and pack sizes.

    **Solution:** SmartCart combines a full supermarket catalogue, budget monitoring, a live bill, stock visibility, lower-price alternatives and an aisle-ordered picking list.

    **Core workflow**
    1. Set a budget in the sidebar.
    2. Search, pick a category, or type a product code to find items.
    3. Add items with the Add and plus buttons.
    4. The live bill and remaining budget update straight away.
    5. If an item would exceed the budget, the app suggests cheaper in-stock options from the same category.
    6. Open My cart to see items grouped by aisle, then download the bill or picking list.

    **Future scope:** barcode/RFID scanning, supermarket inventory integration, expiry-date alerts and demand prediction.

    **Limitations of this demo:** prices and stock levels are sample data, and it is not connected to a live supermarket or physical cart hardware. Cheaper alternatives are matched by similar product names, so check pack size and suitability before switching.
    """)
    st.info("For a real deployment, use verified store prices and update stock from a supermarket database or API.")
