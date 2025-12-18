import os
import json
import time
import typing_extensions
from typing import List
import pandas as pd
import google.generativeai as genai
from google.api_core import retry
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
FOLDER_PATH = r"F:\Project X\Gemini_pdf\sTest"
OUTPUT_FILE = "Extracted_MAERSK_INC.xlsx"


genai.configure(api_key=API_KEY)

# --- 1. IMPROVED SCHEMA (Allows for NULL values) ---
# We use typing.Optional because if the data isn't there (like in your first PDF),
# we want the AI to return null, NOT fake data.
class ExtractionSchema(typing_extensions.TypedDict):
    invoice_date: typing_extensions.Optional[str]
    invoice_number: typing_extensions.Optional[str]
    bl_number: typing_extensions.Optional[str]
    port_of_loading: typing_extensions.Optional[str]
    cy_cfs_destination: typing_extensions.Optional[str]
    container_numbers: typing_extensions.Optional[List[str]]
    gross_weights: typing_extensions.Optional[List[float]]
    total_amount: typing_extensions.Optional[float]

# --- 2. CONFIGURING THE MODEL ---
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    generation_config={
        "response_mime_type": "application/json",
        "response_schema": ExtractionSchema,
        "temperature": 0.0,  # 0.0 is crucial for strict, non-creative extraction
    }
)

# --- 3. THE "PERFECT PRECISION" PROMPT ---
# This prompt includes instructions on formatting and what to do with missing data.
SYSTEM_PROMPT = """
You are an expert data extraction agent specialized in Logistics and Shipping documents. Your goal is to extract the specific highlighted fields from the DB Schenker invoice with 100% precision.

### FIELDS TO EXTRACT:
1. **invoice_date**: Look for "Invoice Date:". Format: DD-MMM-YYYY (e.g., 11-Oct-2021).
2. **invoice_number**: Look for "Invoice No.:". (e.g., 202057121).
3. **bl_number**: Look for "HB/L No.:". (e.g., USMSP0000004006).
4. **port_of_loading**: Look for "Port of Loading (Look specifically "Port of Loading" not the other port):". Extract the city/location name (e.g., Oakland).
5. **cy_cfs_destination**: Look for "CY/CFS Destination(it relies between "port of Discharge" and "final destination" look specifically and if it is empty then keep it empty)". Extract the FULL value including the code and location (e.g., "IDJKT / Jakarta, Java, JK").
6. **container_numbers**: Look under "Marks and Numbers". Extract ALL container numbers as a list. Each container is an 11-character alphanumeric code (4 letters + 7 digits). Return as an array (e.g., ["BMOU1441213", "MSKU9876543"]). If only one container, still return as array.
7. **gross_weights**: Look for "Gross Weight" for EACH container. Return as an array in the SAME ORDER as container_numbers. Each value should be numeric only (e.g., [7678.280, 5432.100]). If only one container, still return as array.
8. **total_amount**: Look for "Total Amount" at the bottom right or "Total Invoice / Credit Amount". Return ONLY the numeric value. (e.g., 1341.00).

### RULES FOR ACCURACY:
- **NO HALLUCINATIONS**: If a field is not clearly present or highlighted, return null.
- **FORMATTING**: 
    - Remove all spaces from Container Numbers.
    - For weights and amounts, remove currency symbols (USD) or unit labels (KGS). 
    - Use a period (.) as the decimal separator.
- **DEDUPLICATION**: If the Invoice Number appears in multiple places (e.g., top header and mid-section), ensure they match and return one instance.

### EXPECTED OUTPUT FORMAT:
Return a JSON object:
{
  "invoice_date": "11-Oct-2021",
  "invoice_number": "202057121",
  "bl_number": "USMSP0000004006",
  "port_of_loading": "Oakland",
  "cy_cfs_destination": " ",
  "container_numbers": ["BMOU1441213"],
  "gross_weights": [7678.280],
  "total_amount": 1341.00
}
"""

def extract_from_pdf(file_path):
    try:
        with open(file_path, "rb") as f:
            pdf_data = f.read()

        # We combine the System Prompt with the actual document data
        response = model.generate_content(
            [
                SYSTEM_PROMPT,
                {"mime_type": "application/pdf", "data": pdf_data}
            ],
            request_options={"retry": retry.Retry(predicate=retry.if_transient_error)}
        )
        return json.loads(response.text)

    except Exception as e:
        print(f"Error processing {os.path.basename(file_path)}: {e}")
        return None

# --- MAIN EXECUTION LOOP ---
def main():
    results = []
    
    # 1. LOAD EXISTING DATA (RESUME CAPABILITY)
    if os.path.exists(OUTPUT_FILE):
        print(f"Loading existing data from {OUTPUT_FILE}...")
        try:
            df_existing = pd.read_excel(OUTPUT_FILE)
            # Normalize column names to match what we expect
            if 'filename' in df_existing.columns:
                results = df_existing.to_dict('records')
        except Exception as e:
            print(f"Could not load existing file: {e}. Starting fresh.")
    
    # Get set of already processed files for O(1) lookups
    # Get set of already processed files for O(1) lookups
    processed_files = {r['file_name'] for r in results if 'file_name' in r}
    
    # Get list of all PDF files
    all_files = [f for f in os.listdir(FOLDER_PATH) if f.lower().endswith('.pdf')]
    
    # Filter out already processed files
    files_to_process = [f for f in all_files if f not in processed_files]
    
    total_files = len(all_files)
    remaining_files = len(files_to_process)
    
    print(f"Found {total_files} PDF files.")
    print(f"Already processed: {len(processed_files)}")
    print(f"Remaining to process: {remaining_files}")
    
    # Define columns order
    cols = ['file_name', 'invoice_date', 'invoice_number', 'bl_number', 'port_of_loading', 'cy_cfs_destination', 'container_number', 'gross_weight', 'total_amount']

    for index, filename in enumerate(files_to_process):
        file_path = os.path.join(FOLDER_PATH, filename)
        current_progress = len(processed_files) + index + 1
        print(f"Processing {current_progress}/{total_files}: {filename}...", end="\r")
        
        data = extract_from_pdf(file_path)
        
        if data:
            # Handle multiple container numbers - create one row per container
            container_numbers = data.get('container_numbers') or [None]
            gross_weights = data.get('gross_weights') or []
            
            if not isinstance(container_numbers, list):
                container_numbers = [container_numbers]
            if not isinstance(gross_weights, list):
                gross_weights = [gross_weights]
            if len(container_numbers) == 0:
                container_numbers = [None]
            
            # Pad gross_weights to match container_numbers length
            while len(gross_weights) < len(container_numbers):
                gross_weights.append(None)
            
            for i, container in enumerate(container_numbers):
                row = {
                    'file_name': filename,
                    'invoice_date': data.get('invoice_date'),
                    'invoice_number': data.get('invoice_number'),
                    'bl_number': data.get('bl_number'),
                    'port_of_loading': data.get('port_of_loading'),
                    'cy_cfs_destination': data.get('cy_cfs_destination'),
                    'container_number': container,
                    'gross_weight': gross_weights[i] if i < len(gross_weights) else None,
                    'total_amount': data.get('total_amount')
                }
                results.append(row)
            
            # --- INCREMENTAL SAVE ---
            try:
                df = pd.DataFrame(results)
                # Ensure columns exist even if all are null
                for col in cols:
                    if col not in df.columns:
                        df[col] = None
                df = df[cols]
                df.to_excel(OUTPUT_FILE, index=False)
            except Exception as e:
                print(f"\nError saving to Excel: {e}")
        
        time.sleep(1) # Respect rate limits

    print(f"\n\nSuccess! All Data saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()