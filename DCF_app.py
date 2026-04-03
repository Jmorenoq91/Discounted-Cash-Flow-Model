import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

# 1. UPDATED CSS: Using Streamlit's internal variables for 100% compatibility
st.markdown("""
<style>
    .kpi-card {
        /* Streamlit's native secondary background variable */
        background-color: var(--secondary-background-color); 
        border-radius: 10px;
        padding: 20px;
        border-left: 5px solid #0096FF;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin-bottom: 20px;
    }

    .kpi-label {
        font-size: 12px;
        font-weight: 600;
        /* Streamlit's native text color variable */
        color: var(--text-color);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }

    .kpi-value {
        font-size: 32px;
        font-weight: 800;
        color: var(--text-color);
    }
</style>
""", unsafe_allow_html=True)

# 2. THE RENDERER: You MUST use this function to see the changes
def styled_kpi(label, value):
    st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
    """, unsafe_allow_html=True)


# Set page to wide mode to accommodate the large DCF table
st.set_page_config(layout="wide", page_title="Two-Stage DCF Model")

# ==========================================
# --- SIDEBAR & INPUTS (TABBED & STYLED) ---
# ==========================================

st.sidebar.title("📈 Model Inputs")

# Global Metric Placeholder (updated at the end of WACC calculation)
wacc_metric = st.sidebar.empty()

# Define and Reverse Tabs
tab_ops, tab_wacc = st.sidebar.tabs(["Operating Inputs", "WACC Calculation"])

# --- TAB 1: OPERATING INPUTS ---
with tab_ops:
    # Row: Revenue Input needed to start projection
    rev_ltm = st.number_input("LTM Revenue", value=1000, step=10)

    # Row 1: Terminal Year (Slider 2 to 20)    
    terminal_year = st.slider("Terminal Year", 2, 20, 10)
    st.caption(f"Projection will run for {terminal_year} years.")

    # Row 2: Revenue Growth (inputs)
    col1, col2 = st.columns(2)
    with col1:
        next_rev_growth = st.number_input("Year 1 Rev Growth (%)", value=10.0, step=0.1) / 100
    with col2:
        term_rev_growth = st.number_input("Terminal Rev Growth (%)", value=3.0, step=0.1) / 100

    # Row 3: EBITDA Margins (inputs)
    col3, col4 = st.columns(2)
    with col3:
        next_ebitda_margin = st.number_input("Year 1 EBITDA Margin (%)", value=35.0, step=0.1) / 100
    with col4:
        term_ebitda_margin = st.number_input("Terminal EBITDA Margin (%)", value=40.0, step=0.1) / 100

    st.divider()

    # Rows 4, 5, 6: Sliders as % of Revenue
    da_pct = st.slider("D&A as % of Revenue", 0.0, 15.0, 3.0, 0.1) / 100
    capex_pct = st.slider("CAPEX as % of Revenue", 0.0, 15.0, 5.0, 0.1) / 100
    nwc_pct = st.slider("WK Investment as % of Revenue", -5.0, 10.0, 2.0, 0.1) / 100

    st.divider()

    # Row 7: Debt, Cash, Shares (Number Inputs)
    st.write("**Bridge to Equity Value**")
    col5, col6 = st.columns(2)
    with col5:
        current_debt = st.number_input("Total Debt ($)", value=2500, step=10)
    with col6:
        current_cash = st.number_input("Cash & Equiv. ($)", value=50, step=10)
    
    shares_outstanding = st.number_input("Shares Outstanding", value=100, step=1)

# --- TAB 2: WACC CALCULATION ---
with tab_wacc:
    st.subheader("Cost of Equity")
    rf = st.number_input("Risk-Free Rate (%)", value=4.0, step=0.1) / 100
    beta = st.number_input("Beta", value=1.0, step=0.05)
    erp = st.number_input("Equity Risk Premium (%)", value=5.0, step=0.1) / 100
    
    ke = rf + (beta * erp) # CAPM
    st.info(f"Cost of Equity ($K_e$): **{ke:.2%}**")
    
    st.divider()
    
    st.subheader("Cost of Debt")
    pre_tax_kd = st.number_input("Pre-tax Cost of Debt (%)", value=6.0, step=0.1) / 100
    # REQUESTED: Change default tax rate to 30%
    tax_rate = st.number_input("Tax Rate (%)", value=30.0, step=1.0) / 100
    
    post_tax_kd = pre_tax_kd * (1 - tax_rate)
    st.info(f"After-tax Cost of Debt: **{post_tax_kd:.2%}**")
    
    st.divider()
    
    st.subheader("Capital Structure")
    # REQUESTED: Change default equity/capital to 50%
    equity_weight = st.slider("Target Equity Weight (%)", 0, 100, 50) / 100
    debt_weight = 1.0 - equity_weight
    st.info(f"Implied Debt Share ($W_d$): **{debt_weight:.2%}**")

    # Final WACC Calculation
    wacc = (equity_weight * ke) + (debt_weight * post_tax_kd)
    # Update global metric in sidebar
    wacc_metric.metric(label="Calculated WACC (Discount Rate)", value=f"{wacc:.2%}")

# =========================================
# --- MODEL LOGIC & CALCULATIONS ---
# =========================================

# 1. Define Projection Years
years = list(range(1, terminal_year + 1))
num_years = len(years)

# 2. Linear Convergence Logic (The "Step")
# Growth and Margin converge LINEARLY from Year 1 values to Terminal values by Year N.
# Step calculation: (Terminal Value - Year 1 Value) / (N - 1)
def calculate_linear_steps(start_val, end_val, steps):
    if steps <= 1: return [end_val]
    # np.linspace handles the linear interpolation perfectly
    return np.linspace(start_val, end_val, steps)

# Apply linear convergence
rev_growth_forecast = calculate_linear_steps(next_rev_growth, term_rev_growth, num_years)
ebitda_margin_forecast = calculate_linear_steps(next_ebitda_margin, term_ebitda_margin, num_years)

# 3. Build the DCF Projection DataFrame
dcf_data = []
prev_rev = rev_ltm

for i, year in enumerate(years):
    # Income Statement Items
    current_growth = rev_growth_forecast[i]
    current_rev = prev_rev * (1 + current_growth)
    
    current_margin = ebitda_margin_forecast[i]
    ebitda = current_rev * current_margin
    
    da = current_rev * da_pct
    ebit = ebitda - da
    taxes = ebit * tax_rate
    nopat = ebit - taxes
    
    # Cash Flow Items
    wk_invest = current_rev * nwc_pct
    capex = current_rev * capex_pct
    fcff = nopat + da - wk_invest - capex
    
    # Discounting
    discount_factor = (1 + wacc) ** year
    pv_fcff = fcff / discount_factor
    
    # Store data
    dcf_data.append({
        "Year": year,
        "Revenue": current_rev,
        "Rev Growth %": current_growth,
        "EBITDA": ebitda,
        "EBITDA Margin %": current_margin,
        "D&A": da,
        "EBIT": ebit,
        "Taxes": taxes,
        "NOPAT": nopat,
        "D&A (Add back)": da,
        "WK Investment": wk_invest,
        "CAPEX": capex,
        "FCFF": fcff,
        "Discount Factor": discount_factor,
        "PV of FCFF": pv_fcff
    })
    prev_rev = current_rev

df_projection = pd.DataFrame(dcf_data).set_index("Year")

# 4. Terminal Value Calculation (Gordon Growth Method)
# Using Year N FCFF as base for terminal growth
last_fcff = df_projection.loc[terminal_year, "FCFF"]
terminal_value = (last_fcff * (1 + term_rev_growth)) / (wacc - term_rev_growth)

# PV of Terminal Value (discounted back from Year N)
pv_terminal_value = terminal_value / ((1 + wacc) ** terminal_year)

# 5. Entity & Equity Value (Photo 2 Logic)
pv_stage1 = df_projection["PV of FCFF"].sum()
net_present_value = pv_stage1 + pv_terminal_value # Enterprise Value

fair_equity_value = net_present_value - current_debt + current_cash

# Handle division by zero if shares set to 0
if shares_outstanding > 0:
    fair_price = fair_equity_value / shares_outstanding
else:
    fair_price = 0

# 6. Specialized KPI Calculation: Implied Terminal EV/EBITDA
# Definition: (PV of TV) / (Last Period EBITDA)
last_ebitda = df_projection.loc[terminal_year, "EBITDA"]
if last_ebitda > 0:
    implied_terminal_ev_ebitda = terminal_value / last_ebitda
else:
    implied_terminal_ev_ebitda = 0

# =========================================
# --- MAIN PAGE OUTPUT (TABBED) ---
# =========================================
st.title("Two-Stage Discounted Cash Flow Model")

k1, k2, k3 = st.columns(3)
    
with k1:
    styled_kpi("Fair Equity Value", f"${fair_equity_value:,.2f}")
with k2:
    styled_kpi("Fair Value Per Share", f"${fair_price:,.2f}")
with k3:
    styled_kpi("Implied Terminal EV/EBITDA", f"{implied_terminal_ev_ebitda:.2f}x")
    
# Define Output Tabs
out_tab1, out_tab2, out_tab3 = st.tabs(["📊 Valuation Output", "📋 Supplementary Data", "🧮 Sensitivity Analysis"])

# --- OUTPUT TAB 1: VALUATION & PHOTOS ---
with out_tab1:

    # Row 2: RE-ADDED BAR CHART (Visualizing the Waterfall)
    st.subheader("Variable Projection Chart")
    st.caption("Visualize the trend of your Income Statement and Cash Flow variables.")
    
    # Prepare display data for the chart with correct signs
    df_chart = df_projection.copy()
    df_chart["Costs and Expenses excl D&A"] = -(df_chart["Revenue"] * (1 - df_chart["EBITDA Margin %"]))
    df_chart["D&A"] = -df_chart["D&A"]
    df_chart["Taxes"] = -df_chart["Taxes"]
    df_chart["WK Investment"] = -df_chart["WK Investment"]
    df_chart["CAPEX"] = -df_chart["CAPEX"]

    # Select variables for the chart
    available_vars = ["Revenue", "Costs and Expenses excl D&A", "EBITDA", "EBIT", "NOPAT", "FCFF"]
    selected_vars = st.multiselect("Select variables to plot:", options=available_vars, default=["Revenue", "EBITDA", "FCFF"])

    if selected_vars:
        fig = go.Figure()
        for var in selected_vars:
            fig.add_trace(go.Bar(x=df_chart.index, y=df_chart[var], name=var))
        fig.update_layout(barmode='group', xaxis_title="Year", yaxis_title="Value ($)", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Row 3: Free Cash Flow Projection (Table)
    st.subheader("1. Free Cash Flow Projection")
    
    # Item 1: Drop Revenue Growth and EBITDA Margin from this view
    items_to_show = [
        "Revenue", 
        "Costs and Expenses excl D&A",
        "EBITDA", 
        "D&A", 
        "EBIT", 
        "Taxes", 
        "NOPAT", 
        "D&A (Add back)", 
        "WK Investment", 
        "CAPEX", 
        "FCFF"
    ]
    
    df_photo1_final = df_chart[items_to_show].T

    # Accounting Format Function (Parentheses for negative)
    def accounting_format(val):
        if isinstance(val, (int, float)):
            if val < 0:
                return f"({abs(val):,.2f})"
            return f"{val:,.2f}"
        return val

    st.dataframe(df_photo1_final.style.format(accounting_format), use_container_width=True)

    st.divider()

    # Row 4: Valuation Summary & Bridge
    st.subheader("2. DCF Valuation Summary & Bridge")
    col_p2_1, col_p2_2 = st.columns([1, 2])
    with col_p2_1:
        p2_data = {
            "Metric": ["PV (Stage 1 Forecast)", "PV (Terminal Value Stage)", "**Enterprise Value (NPV)**", 
                       "Less: Total Debt", "Plus: Cash & Equiv.", "**Fair Equity Value**", 
                       "Shares Outstanding", "**Fair Share Price**"],
            "Value": [pv_stage1, pv_terminal_value, net_present_value, -current_debt, current_cash, 
                      fair_equity_value, shares_outstanding, fair_price]
        }
        for idx, row in pd.DataFrame(p2_data).iterrows():
            c1, c2 = st.columns([2, 1])
            c1.markdown(row["Metric"])
            val = row["Value"]
            fmt = f"({abs(val):,.2f})" if isinstance(val, (int, float)) and val < 0 else f"{val:,.2f}"
            if "**" in row["Metric"]: c2.markdown(f"**{fmt}**")
            else: c2.markdown(fmt)


with out_tab2:
    st.subheader("Supplementary Growth & Margin Analysis")

    # --- ROW 2: Growth Rates Table ---
    # Calculating Year-over-Year growth for various metrics
    # Note: Period 1 (Index 0) will be NaN for most except Revenue Growth
    df_growth = df_projection[["Revenue", "EBITDA", "EBIT", "FCFF"]].pct_change()
    
    # Adding Costs and Expenses excl D&A Growth
    costs_excl_da = df_projection["Revenue"] * (1 - df_projection["EBITDA Margin %"])
    df_growth["Costs & Exp excl D&A Growth"] = costs_excl_da.pct_change()
    
    # Cleaning up names and setting Year 1 Revenue Growth (which is an input, not a calculation)
    df_growth.columns = [f"{c} Growth" for c in df_growth.columns]
    df_growth.iloc[0, 0] = next_rev_growth # Set Y1 Rev Growth manually
    
    # Transpose and display table
    st.write("**Growth Rates Table (%)**")
    st.dataframe(df_growth.T.style.format("{:.2%}", na_rep="-"))

    # --- ROW 1: Growth Chart (Line chart feeding from table above) ---
    st.write("**Growth Trends**")
    fig_growth = go.Figure()
    for col in df_growth.columns:
        fig_growth.add_trace(go.Scatter(x=df_growth.index, y=df_growth[col], name=col, mode='lines+markers'))
    fig_growth.update_layout(yaxis_tickformat='.1%', hovermode="x unified")
    st.plotly_chart(fig_growth, use_container_width=True)

    st.divider()

    # --- ROW 4: Margins & Ratios Table ---
    df_margins = pd.DataFrame(index=df_projection.index)
    df_margins["EBITDA Margin"] = df_projection["EBITDA Margin %"]
    df_margins["EBIT Margin"] = df_projection["EBIT"] / df_projection["Revenue"]
    df_margins["FCFF Margin"] = df_projection["FCFF"] / df_projection["Revenue"]
    df_margins["FCFF / EBITDA"] = df_projection["FCFF"] / df_projection["EBITDA"]

    st.write("**Margins & Conversion Ratios**")
    st.dataframe(df_margins.T.style.format("{:.2%}", subset=pd.IndexSlice[["EBITDA Margin", "EBIT Margin", "FCFF Margin"], :])
                                  .format("{:.2f}x", subset=pd.IndexSlice[["FCFF / EBITDA"], :]))

    # --- ROW 3: Margins Chart (Line chart feeding from table above) ---
    st.write("**Margin & Ratio Trends**")
    fig_margins = go.Figure()
    for col in df_margins.columns:
        # Use secondary Y-axis logic if needed, but here simple lines work
        fig_margins.add_trace(go.Scatter(x=df_margins.index, y=df_margins[col], name=col, mode='lines+markers'))
    fig_margins.update_layout(hovermode="x unified")
    st.plotly_chart(fig_margins, use_container_width=True)

    
# --- OUTPUT TAB 3: SENSITIVITY ANALYSIS ---
with out_tab3:
    st.subheader("Sensitivity Analysis: Fair Share Price")
    st.caption("Investment Banking Style Matrix: Impact of Terminal Assumptions on Valuation.")

    # 1. Define standard IB-style sensitivity ranges around the base case
    # Range for Terminal Growth Rate (Columns)
    g_range = np.arange(term_rev_growth - 0.01, term_rev_growth + 0.015, 0.005) 
    # Range for Terminal EBITDA Margin (Rows)
    m_range = np.arange(term_ebitda_margin - 0.05, term_ebitda_margin + 0.075, 0.025)

    sensitivity_results = []

    for margin_sens in m_range:
        row = []
        for growth_sens in g_range:
            # 1. Rerun linear convergence
            sens_rev_growth = calculate_linear_steps(next_rev_growth, growth_sens, num_years)
            sens_ebitda_margin = calculate_linear_steps(next_ebitda_margin, margin_sens, num_years)
            
            sens_prev_rev = rev_ltm
            sens_fcff_projection = []
            
            for i in range(num_years):
                curr_rev = sens_prev_rev * (1 + sens_rev_growth[i])
                curr_margin = sens_ebitda_margin[i]
                
                # FCFF Ratio Logic
                fcff_ratio = (curr_margin * (1-tax_rate)) + (da_pct * tax_rate) - nwc_pct - capex_pct
                curr_fcff = curr_rev * fcff_ratio
                
                # Discount
                sens_fcff_projection.append(curr_fcff / ((1 + wacc)**(i+1)))
                sens_prev_rev = curr_rev

            # 2. Terminal Value Logic
            sens_last_rev = curr_rev
            sens_last_margin = sens_ebitda_margin[-1]
            
            # Re-derive final FCFF for TV
            sens_last_ebitda = sens_last_rev * sens_last_margin
            sens_last_da = sens_last_rev * da_pct
            sens_last_ebit = sens_last_ebitda - sens_last_da
            sens_last_taxes = sens_last_ebit * tax_rate
            sens_last_nopat = sens_last_ebit - sens_last_taxes
            sens_last_fcff_raw = sens_last_nopat + sens_last_da - (sens_last_rev * nwc_pct) - (sens_last_rev * capex_pct)

            # TV calculation
            sens_tv = (sens_last_fcff_raw * (1 + growth_sens)) / (wacc - growth_sens)
            sens_pv_tv = sens_tv / ((1 + wacc) ** terminal_year)

            # 3. Bridge to Final Price
            sens_ev = sum(sens_fcff_projection) + sens_pv_tv
            sens_equity = sens_ev - current_debt + current_cash
            sens_price = sens_equity / shares_outstanding if shares_outstanding > 0 else 0
            row.append(sens_price)
            
        sensitivity_results.append(row)

    # Convert results matrix to DataFrame
    df_sens = pd.DataFrame(
        sensitivity_results,
        columns=[f"{g:.1%}" for g in g_range],
        index=[f"{m:.1%}" for m in m_range]
    )
    df_sens.index.name = "Terminal EBITDA Margin"

    # --- HEATMAP FIX ---
    # Using 'RdYlGn' (Red-Yellow-Green). 
    # High values (bottom-right) get intense Green.
    # Low values (top-left) get intense Red.
    styled_sens = df_sens.style.background_gradient(cmap='RdYlGn', axis=None).format("{:.2f}")
    
    st.write("**Impact on Fair Share Price ($)**")
    # Using st.write on the styled object preserves the background colors perfectly
    st.write(styled_sens)


def convert_df_to_excel(df_projection, df_growth, df_margins, df_sens, inputs_dict):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # 1. Inputs Sheet
        pd.DataFrame.from_dict(inputs_dict, orient='index', columns=['Value']).to_excel(writer, sheet_name='Inputs')
        
        # 2. Projections Sheet
        df_projection.T.to_excel(writer, sheet_name='Projections')
        
        # 3. Supplementary Data Sheet
        df_growth.T.to_excel(writer, sheet_name='Growth Analysis')
        df_margins.T.to_excel(writer, sheet_name='Margins & Ratios', startrow=len(df_growth.columns) + 4)
        
        # 4. Sensitivity Analysis Sheet
        df_sens.to_excel(writer, sheet_name='Sensitivity Analysis')
        
    return output.getvalue()

def generate_pdf_report(df_projection, df_sens, fair_price):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="DCF Valuation Report", ln=True, align='C')
    
    pdf.set_font("Arial", size=12)
    pdf.ln(10)
    pdf.cell(200, 10, txt=f"Fair Share Price: ${fair_price:,.2f}", ln=True)
    
    # Simple table export for PDF (Projections Summary)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Financial Projections Summary (First 5 Years):", ln=True)
    pdf.set_font("Arial", size=10)
    
    # Add headers
    cols = ["Year"] + list(df_projection.columns[:4])
    for col in cols:
        pdf.cell(35, 10, col, border=1)
    pdf.ln()
    
    # Add rows for first 5 years
    for i in range(1, 6):
        pdf.cell(35, 10, str(i), border=1)
        pdf.cell(35, 10, f"{df_projection.loc[i, 'Revenue']:,.0f}", border=1)
        pdf.cell(35, 10, f"{df_projection.loc[i, 'EBITDA']:,.0f}", border=1)
        pdf.cell(35, 10, f"{df_projection.loc[i, 'EBIT']:,.0f}", border=1)
        pdf.cell(35, 10, f"{df_projection.loc[i, 'FCFF']:,.0f}", border=1)
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1')

# --- EXPORT SECTION ---
st.sidebar.divider()
st.sidebar.subheader("📥 Export Results")

# Create Input Summary for Excel
inputs_summary = {
    "LTM Revenue": rev_ltm,
    "Terminal Year": terminal_year,
    "WACC": wacc,
    "Tax Rate": tax_rate,
    "Terminal Growth": term_rev_growth,
    "Target Equity Weight": equity_weight,
    "Fair Equity Value": fair_equity_value,
    "Fair Share Price": fair_price
}

# Excel Download
excel_data = convert_df_to_excel(df_projection, df_growth, df_margins, df_sens, inputs_summary)
st.sidebar.download_button(
    label="Download Excel Report",
    data=excel_data,
    file_name="DCF_Valuation_Model.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# PDF Download (requires fpdf library)
try:
    pdf_data = generate_pdf_report(df_projection, df_sens, fair_price)
    st.sidebar.download_button(
        label="Download PDF Summary",
        data=pdf_data,
        file_name="Valuation_Summary.pdf",
        mime="application/pdf"
    )
except ImportError:
    st.sidebar.warning("Install 'fpdf' to enable PDF downloads.")    