import sqlite3
import requests
import json

# Your 100/mo free SerpApi Key
SERPAPI_KEY = "YOUR_SERPAPI_KEY"
DB_PATH = '/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db'

def generate_warm_followup(cin):
    """Fetches live ad data for a single warm lead and generates a reply email."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Get the company name from the database
    cursor.execute("SELECT CompanyName FROM vw_qualified_leads WHERE CIN = ?", (cin,))
    result = cursor.fetchone()
    
    if not result:
        return print("CIN not found in database.")
    
    company_name = result[0]
    print(f"🔥 Warm Lead Triggered: {company_name}")
    print("Fetching live Google Ads from Transparency Center...")
    
    # 2. Hit the API (Uses 1 Credit)
    params = {
      "engine": "google_ads_transparency_center",
      "text": company_name,
      "api_key": SERPAPI_KEY
    }
    
    response = requests.get("https://serpapi.com/search", params=params)
    data = response.json()
    
    ads = data.get('ads', [])
    
    if not ads:
        print("❌ No active ads found in the Transparency Center right now.")
        # Update CRM status
        cursor.execute("UPDATE company_enrichment SET Pipeline_Status = 'Replied_No_Visible_Ads' WHERE CIN = ?", (cin,))
        conn.commit()
        return
        
    print(f"✅ Found {len(ads)} active ads!")
    
    # 3. Extract the most interesting ad details for the email
    first_ad = ads[0]
    ad_format = first_ad.get('format', 'display')
    ad_copy = first_ad.get('text', 'your current creatives')[:60] # Grab first 60 chars
    
    # 4. Save the raw Ad Data to your database so you have it forever
    cursor.execute("""
        UPDATE company_enrichment 
        SET Pipeline_Status = 'Replied_Ads_Extracted', 
            Live_Ad_Data = ? 
        WHERE CIN = ?
    """, (json.dumps(ads), cin))
    conn.commit()
    conn.close()
    
    # 5. Generate the Killer Reply Template
    company_title = company_name.title().replace(" Private Limited", "").replace(" Ltd", "")
    
    print("\n" + "="*50)
    print("🎯 COPY & PASTE THIS REPLY:")
    print("="*50)
    print(f"Hi [Name],\n")
    print(f"Thanks for getting back to me. I'm attaching the sample PMax Black Box Audit below.\n")
    print(f"Before you read it, I actually just pulled up the live {ad_format} ads {company_title} is running today (specifically the one starting with '{ad_copy}...').\n")
    print(f"Based on the structure of that specific campaign, it is highly likely your account is currently suffering from what the audit calls 'Attribution Drift'.\n")
    print(f"Take a look at page 2 of the attached PDF—it explains exactly how to patch that specific leak. Let me know if you want me to run this on your live account.\n")
    print(f"Best,\n[Your Name]")
    print("="*50)

# --- How you use it in real life ---
# You get an email from a lead. You find their CIN in your spreadsheet:
# generate_warm_followup('U73100MH2023PTC123456')