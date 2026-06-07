import os
import re
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import matplotlib.pyplot as plt
from fpdf import FPDF
from datetime import datetime, timedelta

# --- CONFIGURATION & CREDENTIALS ---
SLACK_BOT_TOKEN = "xoxb-your-slack-bot-token"
SLACK_CHANNEL_ID = "C1234567890" # ID of the channel where recruiters post
GOOGLE_SHEETS_CREDENTIALS_FILE = "google_credentials.json"
GOOGLE_SHEET_NAME = "Daily Recruiting Updates"

client = WebClient(token=SLACK_BOT_TOKEN)

# --- 1 & 3. FETCH AND EXTRACT DATA FROM SLACK ---
def fetch_daily_slack_messages():
    """Fetches messages from the specified Slack channel for the last 24 hours."""
    try:
        yesterday = datetime.now() - timedelta(days=1)
        result = client.conversations_history(
            channel=SLACK_CHANNEL_ID,
            oldest=yesterday.timestamp()
        )
        return result["messages"]
    except SlackApiError as e:
        print(f"Error fetching conversations: {e}")
        return []

def parse_recruiter_updates(messages):
    """
    Parses messages using Regex. 
    Assumes a template like:
    Candidate: Jane Doe
    Manager: John Smith
    Stage: Onsite
    Status: Stuck - needs feedback
    Priority: High
    """
    extracted_data = []
    
    # Define regex patterns based on your template
    patterns = {
        "Candidate": r"Candidate:\s*(.*)",
        "Manager": r"Manager:\s*(.*)",
        "Stage": r"Stage:\s*(.*)",
        "Status": r"Status:\s*(.*)",
        "Priority": r"Priority:\s*(.*)"
    }

    for msg in messages:
        text = msg.get("text", "")
        entry = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                entry[key] = match.group(1)
        
        # Only add if it actually matched the template
        if entry:
            extracted_data.append(entry)
            
    return extracted_data

# --- 4. CLEAN AND TRANSFORM DATA ---
def clean_data(data_list):
    """Loads data into Pandas, removes extra spaces, and formats text."""
    df = pd.DataFrame(data_list)
    if df.empty:
        return df
        
    # Remove leading/trailing spaces and capitalize consistently (Title Case)
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip().str.title()
        
    return df

# --- 2. PUSH TO GOOGLE SHEETS ---
def update_google_sheet(df):
    """Appends the cleaned data to Google Sheets under machine-identified headers."""
    if df.empty:
        print("No data to update.")
        return

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    
    # Append the dataframe to the sheet
    sheet.append_rows(df.values.tolist())
    print("Google Sheet updated successfully.")

# --- 5 & 6. ANALYZE AND VISUALIZE DATA ---
def analyze_and_visualize(df):
    """Analyzes trends (e.g., stuck candidates, stages) and creates visualizations."""
    if df.empty:
        return
        
    # Visualization 1: Candidates by Stage
    plt.figure(figsize=(8, 5))
    stage_counts = df['Stage'].value_counts()
    stage_counts.plot(kind='bar', color='skyblue', edgecolor='black')
    plt.title('Candidates Pipeline by Stage', fontsize=14)
    plt.xlabel('Interview Stage')
    plt.ylabel('Number of Candidates')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('pipeline_chart.png')
    plt.close()
    
    # Visualization 2: High Priority Roles Breakdown
    plt.figure(figsize=(6, 6))
    priority_counts = df['Priority'].value_counts()
    plt.pie(priority_counts, labels=priority_counts.index, autopct='%1.1f%%', startangle=140)
    plt.title('Priority Distribution')
    plt.savefig('priority_chart.png')
    plt.close()

# --- 7. GENERATE FINAL REPORT ---
def generate_pdf_report(df):
    """Compiles the analysis and visualizations into a daily PDF report."""
    if df.empty:
        return None

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=15)
    
    # Title
    date_str = datetime.now().strftime("%Y-%m-%d")
    pdf.cell(200, 10, txt=f"Daily Recruiting Sync Report - {date_str}", ln=True, align='C')
    
    # Stuck Candidates Insight
    pdf.set_font("Arial", size=12)
    pdf.ln(10)
    pdf.cell(200, 10, txt="Insight: Stuck Candidates", ln=True)
    
    stuck_df = df[df['Status'].str.contains("Stuck", case=False, na=False)]
    if not stuck_df.empty:
        for _, row in stuck_df.iterrows():
            pdf.cell(200, 10, txt=f"- {row['Candidate']} (Manager: {row['Manager']})", ln=True)
    else:
        pdf.cell(200, 10, txt="- No stuck candidates today! Great job.", ln=True)
        
    # Insert Visualizations
    pdf.ln(10)
    pdf.image('pipeline_chart.png', x=10, y=None, w=100)
    pdf.image('priority_chart.png', x=110, y=pdf.get_y() - 75, w=80)
    
    report_filename = f"Recruiting_Report_{date_str}.pdf"
    pdf.output(report_filename)
    return report_filename

def send_report_to_slack(report_filename):
    """Uploads the final report back to the team sync Slack channel."""
    try:
        client.files_upload_v2(
            channel=SLACK_CHANNEL_ID,
            file=report_filename,
            title="Morning Sync Report",
            initial_comment="Good morning team! Here is the data breakdown from yesterday's updates. 📊"
        )
        print("Report shared to Slack!")
    except SlackApiError as e:
        print(f"Error uploading file: {e}")

# --- MASTER EXECUTION FUNCTION ---
def main():
    print("Fetching daily updates...")
    raw_messages = fetch_daily_slack_messages()
    
    print("Extracting data based on template...")
    extracted_data = parse_recruiter_updates(raw_messages)
    
    print("Cleaning and standardizing data...")
    df = clean_data(extracted_data)
    
    if not df.empty:
        update_google_sheet(df)
        analyze_and_visualize(df)
        report_file = generate_pdf_report(df)
        if report_file:
            send_report_to_slack(report_file)
    else:
        print("No recruiting updates found for today.")

if __name__ == "__main__":
    main()
