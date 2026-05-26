import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
from google.oauth2.service_account import Credentials
from datetime import date

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="Global Trust Inventory",
    page_icon="🎁",
    layout="wide"
)

st.markdown("""
<style>
.main-header {
    color: #1B3A6B;
    font-size: 2rem;
    font-weight: bold;
}
.sub-header {
    color: #4A7AB5;
    font-size: 1.1rem;
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

# =========================
# GOOGLE CONFIG
# =========================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SHEET_NAME = "GlobalTrust_Inventory"

REQUIRED_COLUMNS = [
    "Item",
    "Category",
    "Size/Variant",
    "Quantity In Stock",
    "Low Stock Threshold",
    "Unit Cost ($)"
]

# =========================
# GOOGLE CONNECTION
# =========================
@st.cache_resource
def get_workbook():
    creds_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=SCOPES
    )

    client = gspread.authorize(creds)

    return client.open(SHEET_NAME)


wb = get_workbook()

inventory_sheet = wb.worksheet("Inventory")
log_sheet = wb.worksheet("GiveLog")

# =========================
# LOAD INVENTORY (SAFE)
# =========================
@st.cache_data(ttl=30)
def load_inventory():
    records = inventory_sheet.get_all_records()
    df = pd.DataFrame(records)

    if df.empty:
        return df

    # clean column names
    df.columns = df.columns.str.strip()

    # check missing columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]

    if missing:
        st.error("❌ Your Google Sheet is missing required columns:")
        st.write(missing)
        st.stop()

    # safe conversions
    df["Quantity In Stock"] = pd.to_numeric(df["Quantity In Stock"], errors="coerce").fillna(0).astype(int)
    df["Low Stock Threshold"] = pd.to_numeric(df["Low Stock Threshold"], errors="coerce").fillna(5).astype(int)
    df["Unit Cost ($)"] = pd.to_numeric(df["Unit Cost ($)"], errors="coerce").fillna(0.0)

    return df


# =========================
# LOAD LOG
# =========================
@st.cache_data(ttl=30)
def load_log():
    records = log_sheet.get_all_records()

    if not records:
        return pd.DataFrame(columns=[
            "Date", "Client Name", "Item", "Size/Variant",
            "Quantity Given", "Given By", "Notes"
        ])

    return pd.DataFrame(records)


# =========================
# REFRESH
# =========================
def refresh():
    load_inventory.clear()
    load_log.clear()
    st.rerun()


# =========================
# HEADER
# =========================
col1, col2 = st.columns([4, 1])

with col1:
    st.markdown('<div class="main-header">🎁 Global Trust Inventory</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Swag & Client Gift Tracker</div>', unsafe_allow_html=True)

with col2:
    if st.button("🔄 Refresh"):
        refresh()


# =========================
# LOAD DATA
# =========================
df_inv = load_inventory()
df_log = load_log()


# =========================
# METRICS
# =========================
if not df_inv.empty:
    total_items = df_inv["Quantity In Stock"].sum()
    low_stock = df_inv[df_inv["Quantity In Stock"] <= df_inv["Low Stock Threshold"]]
    total_value = (df_inv["Quantity In Stock"] * df_inv["Unit Cost ($)"]).sum()
    total_given = pd.to_numeric(df_log["Quantity Given"], errors="coerce").sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Stock", f"{int(total_items):,}")
    c2.metric("Low Stock Items", len(low_stock))
    c3.metric("Inventory Value", f"${total_value:,.2f}")
    c4.metric("Items Given", f"{int(total_given):,}")

st.markdown("---")


# =========================
# TABS
# =========================
tab1, tab2, tab3, tab4 = st.tabs([
    "📦 Inventory",
    "🎁 Give",
    "📬 Restock",
    "📊 Analytics"
])


# =========================
# TAB 1 - INVENTORY
# =========================
with tab1:
    st.subheader("Inventory")

    if df_inv.empty:
        st.info("No inventory data found.")
    else:
        st.dataframe(df_inv, use_container_width=True)


# =========================
# TAB 2 - GIVE
# =========================
with tab2:
    st.subheader("Give Item")

    if df_inv.empty:
        st.info("No inventory loaded.")
    else:
        with st.form("give_form"):
            client = st.text_input("Client Name")
            staff = st.text_input("Given By")

            items = df_inv.apply(
                lambda r: f"{r['Item']} ({r['Size/Variant']})",
                axis=1
            ).tolist()

            item = st.selectbox("Item", items)
            qty = st.number_input("Quantity", min_value=1, value=1)

            notes = st.text_input("Notes")

            submit = st.form_submit_button("Submit")

        if submit:
            idx = items.index(item)
            current = df_inv.iloc[idx]["Quantity In Stock"]

            if qty > current:
                st.error("Not enough stock")
            else:
                new_qty = current - qty

                inventory_sheet.update_cell(idx + 2, 4, new_qty)

                row = df_inv.iloc[idx]

                log_sheet.append_row([
                    str(date.today()),
                    client,
                    row["Item"],
                    row["Size/Variant"],
                    qty,
                    staff,
                    notes
                ])

                st.success("Recorded successfully")
                refresh()


# =========================
# TAB 3 - RESTOCK
# =========================
with tab3:
    st.subheader("Restock")

    if df_inv.empty:
        st.info("No inventory.")
    else:
        items = df_inv.apply(
            lambda r: f"{r['Item']} ({r['Size/Variant']})",
            axis=1
        ).tolist()

        item = st.selectbox("Item", items)
        qty = st.number_input("Add Quantity", min_value=1, value=10)

        if st.button("Restock"):
            idx = items.index(item)

            current = df_inv.iloc[idx]["Quantity In Stock"]
            new_qty = current + qty

            inventory_sheet.update_cell(idx + 2, 4, new_qty)

            st.success("Restocked")
            refresh()


# =========================
# TAB 4 - ANALYTICS
# =========================
with tab4:
    st.subheader("Analytics")

    if df_inv.empty:
        st.info("No data.")
    else:
        fig = px.bar(df_inv, x="Item", y="Quantity In Stock", color="Category")
        st.plotly_chart(fig, use_container_width=True)
