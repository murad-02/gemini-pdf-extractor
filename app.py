import os
import json
import time
import typing_extensions
from typing import List
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import google.generativeai as genai
from google.api_core import retry
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['OUTPUT_FILE'] = 'web_extraction_results.xlsx'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

# Schema definition
class ExtractionSchema(typing_extensions.TypedDict):
    invoice_date: typing_extensions.Optional[str]
    invoice_number: typing_extensions.Optional[str]
    bl_number: typing_extensions.Optional[str]
    port_of_loading: typing_extensions.Optional[str]
    cy_cfs_destination: typing_extensions.Optional[str]
    container_numbers: typing_extensions.Optional[List[str]]
    gross_weights: typing_extensions.Optional[List[float]]
    total_amount: typing_extensions.Optional[float]

# Default prompt
DEFAULT_PROMPT = """
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

# In-memory storage
extraction_results = []

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_from_pdf(pdf_content, api_key, prompt):
    try:
        genai.configure(api_key=api_key)
        
        # Switched to 2.5-flash as requested
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash", 
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": ExtractionSchema,
                "temperature": 0.0,
            }
        )
        
        print(f"Sending request to Gemini...")
        response = model.generate_content(
            [prompt, {"mime_type": "application/pdf", "data": pdf_content}],
            request_options={"retry": retry.Retry(predicate=retry.if_transient_error)}
        )
        
        print(f"Received response: {response.text[:100]}...") # Log first 100 chars
        return json.loads(response.text)
    except Exception as e:
        print(f"Extraction Error: {str(e)}")
        raise Exception(f"Gemini API Error: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html', default_prompt=DEFAULT_PROMPT)

@app.route('/extract', methods=['POST'])
def extract():
    global extraction_results
    
    try:
        api_key = request.form.get('api_key')
        prompt = request.form.get('prompt', DEFAULT_PROMPT)
        
        if not api_key:
            return jsonify({'error': 'API key is required'}), 400
        
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file'}), 400
        
        # Read file directly into memory
        pdf_content = file.read()
        filename = secure_filename(file.filename)
        
        # Extract
        data = extract_from_pdf(pdf_content, api_key, prompt)
        
        # Normalize Data Lists
        container_numbers = data.get('container_numbers')
        # If None or not list, convert to list
        if container_numbers is None:
            container_numbers = [None]
        elif not isinstance(container_numbers, list):
            container_numbers = [container_numbers]
        # If empty list, ensure at least one None to create a row
        if len(container_numbers) == 0:
            container_numbers = [None]
            
        gross_weights = data.get('gross_weights') or []
        if not isinstance(gross_weights, list):
            gross_weights = [gross_weights]
            
        # Pad weights
        while len(gross_weights) < len(container_numbers):
            gross_weights.append(None)
        
        new_rows = []
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
            new_rows.append(row)
            extraction_results.append(row)
            
        # Save to Excel
        if extraction_results:
            df = pd.DataFrame(extraction_results)
            # Ensure cols order for better Excel
            cols = ['file_name', 'invoice_date', 'invoice_number', 'bl_number', 
                    'port_of_loading', 'cy_cfs_destination', 'container_number', 
                    'gross_weight', 'total_amount']
            # Add missing cols
            for c in cols:
                if c not in df.columns:
                    df[c] = None
            df = df[cols]
            df.to_excel(app.config['OUTPUT_FILE'], index=False)
        
        return jsonify({
            'success': True, 
            'data': new_rows,
            'total_records': len(extraction_results)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download')
def download():
    if os.path.exists(app.config['OUTPUT_FILE']):
        return send_file(app.config['OUTPUT_FILE'], as_attachment=True)
    return jsonify({'error': 'No results to download'}), 404

@app.route('/clear_results', methods=['POST'])
def clear_results():
    global extraction_results
    extraction_results = []
    if os.path.exists(app.config['OUTPUT_FILE']):
        os.remove(app.config['OUTPUT_FILE'])
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
