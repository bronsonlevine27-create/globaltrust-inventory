import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
from google.oauth2.service_account import Credentials
from datetime import date
import json

st.set_page_config(page_title="Global Trust | Swag Inventory", page_icon="🎁", layout="wide")

st.markdown("""
    <style>
    .main-header { color: #1B3A6B; font-size: 2rem; font-weight: bold; }
    .sub-header  { color: #4A7AB5; font-size: 1.1rem; margin-bottom: 1rem; }
    </style>
""", unsafe_allow_html=True)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_workbook():
    creds_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open("GlobalTrust_Swag")

wb = get_workbook()
inventory_sheet = wb.worksheet("Inventory")
log_sheet = wb.worksheet("GiveLog")

@st.cache_data(ttl=30)
def load_inventory():
    records = inventory_sheet.get_all_records()
    df = pd.DataFrame(records)
    if not df.empty:
        df["Quantity In Stock"]   = pd.to_numeric(df["Quantity In Stock"],   errors="coerce").fillna(0).astype(int)
        df["Low Stock Threshold"] = pd.to_numeric(df["Low Stock Threshold"], errors="coerce").fillna(5).astype(int)
        df["Unit Cost ($)"]       = pd.to_numeric(df["Unit Cost ($)"],       errors="coerce").fillna(0.0)
    return df

@st.cache_data(ttl=30)
def load_log():
    records = log_sheet.get_all_records()
    return pd.DataFrame(records) if records else pd.DataFrame(columns=[
        "Date", "Client Name", "Item", "Size/Variant", "Quantity Given", "Given By", "Notes"
    ])

def refresh():
    load_inventory.clear()
    load_log.clear()
    st.rerun()

col1, col2 = st.columns([4, 1])
with col1:
    st.markdown('<div class="main-header">🎁 Global Trust Asset Management</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Client Gift & Swag Inventory Manager</div>', unsafe_allow_html=True)
with col2:
    st.write("")
    if st.button("🔄 Refresh", use_container_width=True):
        refresh()

df_inv = load_inventory()
df_log = load_log()

if not df_inv.empty:
    total_items = df_inv["Quantity In Stock"].sum()
    low_stock   = df_inv[df_inv["Quantity In Stock"] <= df_inv["Low Stock Threshold"]]
    total_value = (df_inv["Quantity In Stock"] * df_inv["Unit Cost ($)"]).sum()
    total_given = pd.to_numeric(df_log["Quantity Given"], errors="coerce").sum() if not df_log.empty else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Items In Stock",  f"{int(total_items):,}")
    m2.metric("⚠️ Low Stock Alerts",   len(low_stock))
    m3.metric("Inventory Value",       f"${total_value:,.2f}")
    m4.metric("Total Items Given Out", f"{int(total_given):,}")

st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs(["📦 Inventory", "🎁 Give to Client", "📬 Restock", "📊 Analytics"])

with tab1:
    st.subheader("Current Stock Levels")
    if df_inv.empty:
        st.info("No inventory data found.")
    else:
        low = df_inv[df_inv["Quantity In Stock"] <= df_inv["Low Stock Threshold"]]
        if not low.empty:
            for _, row in low.iterrows():
                label = f"{row['Item']}" + (f" ({row['Size/Variant']})" if row['Size/Variant'] not in ["N/A", ""] else "")
                st.warning(f"🔴 {label} — only {row['Quantity In Stock']} left (threshold: {row['Low Stock Threshold']})")

        cat_filter = st.multiselect("Filter by Category", df_inv["Category"].unique(), default=list(df_inv["Category"].unique()))
        filtered = df_inv[df_inv["Category"].isin(cat_filter)]
        st.dataframe(filtered, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Export CSV", filtered.to_csv(index=False), "globaltrust_inventory.csv", "text/csv")

with tab2:
    st.subheader("Record Items Given to a Client")
    if df_inv.empty:
        st.info("No inventory loaded.")
    else:
        with st.form("give_form"):
            c1, c2 = st.columns(2)
            with c1:
                client_name = st.text_input("Client Name")
                given_by    = st.text_input("Given By (Advisor/Staff Name)")
                give_date   = st.date_input("Date", value=date.today())
            with c2:
                item_options  = df_inv.apply(
                    lambda r: f"{r['Item']}" + (f" ({r['Size/Variant']})" if r['Size/Variant'] not in ["N/A", ""] else ""),
                    axis=1
                ).tolist()
                selected_item = st.selectbox("Item", item_options)
                qty_give      = st.number_input("Quantity", min_value=1, step=1, value=1)
            notes     = st.text_input("Notes (optional)")
            submitted = st.form_submit_button("✅ Record & Deduct from Stock")

        if submitted:
            if not client_name or not given_by:
                st.error("Client name and advisor name are required.")
            else:
                idx         = item_options.index(selected_item)
                row_num     = idx + 2
                current_qty = int(df_inv.iloc[idx]["Quantity In Stock"])
                if qty_give > current_qty:
                    st.error(f"❌ Only {current_qty} in stock. Can't give out {qty_give}.")
                else:
                    new_qty   = current_qty - qty_give
                    inventory_sheet.update_cell(row_num, 4, new_qty)
                    item_row  = df_inv.iloc[idx]
                    log_sheet.append_row([
                        str(give_date), client_name, item_row["Item"],
                        item_row["Size/Variant"], qty_give, given_by, notes
                    ])
                    st.success(f"✅ Gave {qty_give}x {selected_item} to {client_name}. Stock is now {new_qty}.")
                    refresh()

with tab3:
    st.subheader("Restock an Item")
    if df_inv.empty:
        st.info("No inventory loaded.")
    else:
        with st.form("restock_form"):
            item_options_r   = df_inv.apply(
                lambda r: f"{r['Item']}" + (f" ({r['Size/Variant']})" if r['Size/Variant'] not in ["N/A", ""] else ""),
                axis=1
            ).tolist()
            selected_restock = st.selectbox("Item to Restock", item_options_r)
            qty_add          = st.number_input("Quantity to Add", min_value=1, step=1, value=10)
            submitted_r      = st.form_submit_button("📦 Add to Stock")

        if submitted_r:
            idx_r     = item_options_r.index(selected_restock)
            row_num_r = idx_r + 2
            current_r = int(df_inv.iloc[idx_r]["Quantity In Stock"])
            new_r     = current_r + qty_add
            inventory_sheet.update_cell(row_num_r, 4, new_r)
            st.success(f"✅ Restocked {selected_restock}: {current_r} → {new_r}")
            refresh()

with tab4:
    st.subheader("Analytics")
    if df_inv.empty:
        st.info("No data yet.")
    else:
        a1, a2 = st.columns(2)
        with a1:
            stock_summary = df_inv.groupby("Item")["Quantity In Stock"].sum().reset_index()
            fig1 = px.bar(stock_summary, x="Item", y="Quantity In Stock",
                          title="Stock by Item", color="Item",
                          color_discrete_sequence=px.colors.sequential.Blues_r)
            st.plotly_chart(fig1, use_container_width=True)
        with a2:
            df_inv["Total Value"] = df_inv["Quantity In Stock"] * df_inv["Unit Cost ($)"]
            val_by_cat = df_inv.groupby("Category")["Total Value"].sum().reset_index()
            fig2 = px.pie(val_by_cat, names="Category", values="Total Value",
                          title="Inventory Value by Category",
                          color_discrete_sequence=["#1B3A6B","#4A7AB5","#A8C4E0","#D0E4F7"])
            st.plotly_chart(fig2, use_container_width=True)

        if not df_log.empty:
            df_log["Quantity Given"] = pd.to_numeric(df_log["Quantity Given"], errors="coerce").fillna(0)
            given_summary = df_log.groupby("Item")["Quantity Given"].sum().reset_index()
            fig3 = px.bar(given_summary, x="Item", y="Quantity Given",
                          title="Total Items Given Out", color="Item",
                          color_discrete_sequence=px.colors.sequential.Blues_r)
            st.plotly_chart(fig3, use_container_width=True)

            st.subheader("📬 Give Log")
            st.dataframe(df_log.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)
            st.download_button("⬇️ Export Give Log", df_log.to_csv(index=False), "globaltrust_givelog.csv", "text/csv")
