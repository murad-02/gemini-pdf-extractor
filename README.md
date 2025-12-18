# Gemini PDF Extractor - Maersk Invoice Automation

A premium, AI-powered web dashboard for automatically extracting structured data from Maersk shipping invoices and logistics documents using Google's Gemini 2.5 Flash model.

## 🚀 Features

- **Intelligent Extraction**: Uses Google Gemini 2.5 Flash to identify and extract key fields like Invoice #, Date, BL Number, Port of Loading, and Container details with high precision.
- **Modern UI**: A beautiful, responsive glassmorphism interface with drag-and-drop file upload.
- **Live Configuration**: Customize the extraction prompt directly from the web interface without touching code.
- **Privacy Focused**: Your Gemini API Key is stored only in your browser (client-side) or current session—never saved to a database.
- **Excel Export**: Download all extracted data into a formatted Excel file (`.xlsx`) with a single click.
- **Batch Ready**: designed to handle complex PDF structures including multi-container invoices.

## 🛠️ Tech Stack

- **Backend**: Python, Flask
- **AI Engine**: Google Gemini API (gemini-2.5-flash)
- **Data Processing**: Pandas, OpenPyXL
- **Frontend**: HTML5, CSS3 (Custom Glassmorphism Design)

## 📋 Prerequisites

- Python 3.8 or higher
- A Google Cloud API Key with access to Gemini API

## 📦 Installation

1. **Clone or Download** this repository.

2. **Install Dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Application**:

   ```bash
   python app.py
   ```

4. **Access the Dashboard**:
   Open your browser and navigate to `http://localhost:5000`

## 💡 How to Use

1. **Configure API Key**:

   - Go to the **Settings** tab in the sidebar.
   - Enter your Google Gemini API Key. This enables the connection to the AI model.

2. **Upload PDF**:

   - Go to the **Upload** tab.
   - Drag and drop your Maersk PDF invoice or click to browse.
   - Click **Extract Data**.

3. **View & Export**:
   - Results will appear instantly in the **Results** tab.
   - Click **Download Excel** to save the data to your local machine.

## 📂 Project Structure

```
Gemini_pdf/
├── app.py                      # Main Flask application and API logic
├── MAERSK_INC_info_extraction.py # Original standalone CLI script
├── requirements.txt            # Python dependencies
├── .gitignore                 # Git ignore rules
├── templates/
│   └── index.html             # Main dashboard frontend
└── static/
    └── css/
        └── style.css          # Premium styling
```

## ⚙️ Customization

You can modify the default system prompt that instructs the AI on _what_ to extract by editing the **Extraction Prompt** in the Settings tab. This allows you to adapt the tool for different invoice formats without rewriting code.

## 📝 License

Proprietary - built for internal use.
