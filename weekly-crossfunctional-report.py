import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import matplotlib.pyplot as plt
from fpdf import FPDF
from datetime import datetime, timedelta

# --- CONFIGURATION ---
SLACK_BOT_TOKEN = "xoxb-your-slack-bot-token"
EXEC_CHANNEL_ID = "C0987654321" # e.g., #leadership-updates or #hiring-managers
GOOGLE_SHEETS_CREDENTIALS_FILE = "google_credentials.json"
GOOGLE_SHEET_NAME = "Daily Recruiting Updates"

client = WebClient(token=SLACK_BOT_TOKEN)

# --- 1. PULL LIVE DATA FROM GOOGLE SHEETS ---
def fetch_google_sheet_data():
    """Pulls the entire active pipeline from the Google Sheet database."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS_FILE, scope)
    gc = gspread.authorize(creds)
    
    sheet = gc.open(GOOGLE_SHEET_NAME).sheet1
    data = sheet.get_all_records()
    
    return pd.DataFrame(data)

# --- 2. AGGREGATE CROSS-DEPARTMENTAL METRICS ---
def generate_weekly_visualizations(df):
    """Creates macro-level visualizations for executives and hiring managers."""
    if df.empty:
        return
    
    # 1. Pipeline Volume by Hiring Manager (Department Proxy)
    plt.figure(figsize=(10, 6))
    manager_counts = df['Manager'].value_counts().head(10) # Top 10 most active managers
    manager_counts.sort_values().plot(kind='barh', color='#2ca02c', edgecolor='black')
    plt.title('Active Candidates by Hiring Manager (Top 10)', fontsize=14)
    plt.xlabel('Number of Candidates')
    plt.tight_layout()
    plt.savefig('manager_volume_chart.png')
    plt.close()

    # 2. Macro Pipeline Health (Funnel Drop-off)
    plt.figure(figsize=(8, 5))
    # Enforce logical funnel order
    stage_order = ['Sourcing', 'Phone Screen', 'Technical Assessment', 'Onsite', 'Executive Interview', 'Offer']
    stage_counts = df['Stage'].value_counts().reindex(stage_order).fillna(0)
    
    stage_counts.plot(kind='area', alpha=0.4, color='blue')
    stage_counts.plot(kind='line', marker='o', color='darkblue', linewidth=2)
    plt.title('Company-Wide Pipeline Funnel', fontsize=14)
    plt.ylabel('Candidates')
    plt.xticks(range(len(stage_counts)), stage_counts.index, rotation=45)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig('macro_funnel_chart.png')
    plt.close()

# --- 3. GENERATE EXECUTIVE PDF REPORT ---
def generate_weekly_pdf(df):
    """Compiles the high-level data into a polished PDF for leadership."""
    if df.empty:
        return None

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    # Header
    week_end = datetime.now().strftime("%B %d, %Y")
    pdf.cell(200, 10, txt=f"Weekly Cross-Departmental Hiring Report", ln=True, align='C')
    pdf.set_font("Arial", 'I', 12)
    pdf.cell(200, 10, txt=f"Week Ending: {week_end}", ln=True, align='C')
    pdf.ln(10)
    
    # Executive Summary Text
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="1. Executive Summary", ln=True)
    pdf.set_font("Arial", '', 11)
    
    total_candidates = len(df)
    offers_out = len(df[df['Stage'].str.contains('Offer', case=False, na=False)])
    high_priority = len(df[df['Priority'].str.contains('High', case=False, na=False)])
    
    pdf.cell(200, 8, txt=f"- Total Active Candidates in Pipeline: {total_candidates}", ln=True)
    pdf.cell(200, 8, txt=f"- Total Offers Currently Pending: {offers_out}", ln=True)
    pdf.cell(200, 8, txt=f"- High Priority Critical Fills Active: {high_priority}", ln=True)
    pdf.ln(5)

    # Cross-Functional Bottlenecks
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="2. Cross-Functional Bottlenecks (Action Required)", ln=True)
    pdf.set_font("Arial", '', 11)
    
    stuck_df = df[df['Status'].str.contains("Stuck", case=False, na=False)]
    if not stuck_df.empty:
        # Group stuck candidates by manager to show which departments are holding up the line
        stuck_by_manager = stuck_df['Manager'].value_counts()
        for manager, count in stuck_by_manager.items():
            pdf.cell(200, 8, txt=f"- {manager}'s Team: {count} candidates stuck awaiting action/feedback.", ln=True)
    else:
        pdf.cell(200, 8, txt="- No major bottlenecks reported this week.", ln=True)
        
    # Insert Visualizations
    pdf.add_page() # Put charts on a new page for clean formatting
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="3. Visual Pipeline Breakdown", ln=True)
    pdf.image('manager_volume_chart.png', x=10, y=30, w=180)
    pdf.image('macro_funnel_chart.png', x=10, y=140, w=180)
    
    report_filename = f"Weekly_Hiring_Report_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    pdf.output(report_filename)
    return report_filename

# --- 4. DISTRIBUTE TO LEADERSHIP SLACK ---
def send_weekly_report_to_slack(report_filename):
    """Uploads the report to a cross-functional Slack channel."""
    try:
        client.files_upload_v2(
            channel=EXEC_CHANNEL_ID,
            file=report_filename,
            title="Weekly Hiring Summary",
            initial_comment="Happy Friday Leadership Team! 📈 Here is the high-level summary of our hiring pipeline, active offers, and areas where we need department managers to unblock candidates."
        )
        print("Weekly report shared to leadership Slack!")
    except SlackApiError as e:
        print(f"Error uploading file: {e}")

# --- MASTER EXECUTION ---
def main():
    print("Pulling live pipeline data from Google Sheets...")
    df = fetch_google_sheet_data()
    
    if not df.empty:
        print("Generating executive visualizations...")
        generate_weekly_visualizations(df)
        
        print("Compiling Weekly PDF...")
        report_file = generate_weekly_pdf(df)
        
        if report_file:
            print("Distributing to stakeholders...")
            send_weekly_report_to_slack(report_file)
    else:
        print("No data available to generate weekly report.")

if __name__ == "__main__":
    main()
