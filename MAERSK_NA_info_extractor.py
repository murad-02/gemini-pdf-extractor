import os
import json
import time
import typing_extensions
import pandas as pd
import google.generativeai as genai
from google.api_core import retry
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
FOLDER_PATH = "Test"       # Folder containing your 700 PDFs
OUTPUT_FILE = "MAERSK_NA.xlsx"


genai.configure(api_key=API_KEY)

# --- 1. IMPROVED SCHEMA (Allows for NULL values) ---
# We use typing.Optional because if the data isn't there (like in your first PDF),
# we want the AI to return null, NOT fake data.
class ExtractionSchema(typing_extensions.TypedDict):
    invoice_number: typing_extensions.Optional[str]
    invoice_date: typing_extensions.Optional[str]
    place_of_receipt: typing_extensions.Optional[str]
    place_of_delivery: typing_extensions.Optional[str]
    bl_number: typing_extensions.Optional[str]
    container_number: typing_extensions.Optional[str]
    pcd: typing_extensions.Optional[str]
    total_payable_amount: typing_extensions.Optional[float]

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
You are an expert data extraction agent specialized in Logistics and Shipping documents (Invoices, Bill of Ladings, Demurrage notes).
Your goal is to extract specific fields with 100% precision.

### FIELDS TO EXTRACT:
1. **invoice_number**: Look for "Nº da Fatura", "Invoice Number", "Invoice No". Generally it will be in top right area of the page.
2. **invoice_date**: Look for "Data da Fatura", "Invoice Date", "Invoice Date". Generally it will be in top right area of the page. Convert the date to mm/dd/yyyy format.
3. **place_of_receipt**: Look for "Place of Receipt". Generally it will be under "vesseal/voyage Direction" window. 
4. **place_of_delivery**: Look for "Place of Delivery". Generally it will be under "vesseal/voyage Direction" window. 
5. **bl_number**: Bill of Lading (BL) Number used to track the shipment. Look for "Bill of Lading" 
6. **container_number**: 
   - Look for standard ISO container numbers: 4 letters followed by 7 digits (e.g., MSKU1234567, SUDU9876543).
   - Look under headers like "Container No", "Contenedor"
   - **CRITICAL**: If the document lists a header for Container but the field below it is empty, return null. DO NOT guess a phone number or reference number as a container.
7. **pcd**: 
   - Look for "PCD" (Price Calculation Date) 
   - Convert the date to mm/dd/yyyy format.
8. **total_payable_amount**: 
   - Look for the final total payable amount. Keywords: "Total Payable Amount"
   - Return ONLY the numeric value (e.g., 650.00). Do not include currency symbols ($ or USD).

### RULES FOR ACCURACY:
- **NO HALLUCINATIONS**: If a field is not clearly present in the document, return null. Do not infer or guess.
- **FORMATTING**: Remove all spaces from Container Numbers (e.g., "MSKU 123 456 7" -> "MSKU1234567").
- **PRIORITY**: If multiple numbers appear, prioritize the one explicitly labeled with the keywords above.

### EXAMPLES:

**Input Text:**
"Hamburg Sud. Invoice No: 698064567. Invoice Date: 22-Oct-2023.
Place of Receipt: Santos. Place of Delivery: Rotterdam.
Bill of Lading: SUDU22PHL039856A. 
Container No: MSKU2804235.
PCD: 25-Oct-2023.
Total Payable Amount: 650.00 USD."

**Correct Output:**
{"invoice_number": "698064567", "invoice_date": "10/22/2023", "place_of_receipt": "Santos", "place_of_delivery": "Rotterdam", "bl_number": "SUDU22PHL039856A", "container_number": "MSKU2804235", "pcd": "10/25/2023", "total_payable_amount": 650.00}

**Input Text:**
"Factura 200517. Data da Fatura: 15/05/2023. Ref: ME-24088. Contenedorles: [EMPTY]. Total Payable Amount: 12.289,10 EUR. Place of Receipt: StartPort. PCD: 16/05/2023"

**Correct Output:**
{"invoice_number": "200517", "invoice_date": "05/15/2023", "place_of_receipt": "StartPort", "place_of_delivery": null, "bl_number": null, "container_number": null, "pcd": "05/16/2023", "total_payable_amount": 12289.10}
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
    processed_files = {r['filename'] for r in results if 'filename' in r}
    
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
    cols = ['filename', 'invoice_number', 'invoice_date', 'place_of_receipt', 'place_of_delivery', 'bl_number', 'container_number', 'pcd', 'total_payable_amount']

    for index, filename in enumerate(files_to_process):
        file_path = os.path.join(FOLDER_PATH, filename)
        current_progress = len(processed_files) + index + 1
        print(f"Processing {current_progress}/{total_files}: {filename}...", end="\r")
        
        data = extract_from_pdf(file_path)
        
        if data:
            data['filename'] = filename
            results.append(data)
            
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