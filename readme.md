# Receipt Processing System

A full-stack application for uploading, processing, and managing receipts with OCR capabilities.

## Features
- PDF receipt upload and validation
- OCR text extraction using Tesseract
- Merchant recognition and categorization
- Year-based file organization
- REST API backend with SQLite database
- React frontend


## Installation

### Backend Setup
1. Navigate to the backend folder:
   ```bash
   cd receipt_management
   ```

1. Create and activate a virtual environment:

    **Windows:**

    ```bash
    python -m venv venv
    venv\Scripts\activate
    ```

    **Mac/Linux:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

    **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

    **Install Tesseract OCR:**
    Windows: Download from UB Mannheim
    Mac: brew install tesseract
    Linux: sudo apt install tesseract-ocr

### Run the backend:

    ```bash
    python app.py
    ```

### Frontend Setup
    Navigate to the frontend folder:

    ```bash
    cd ../receipt-frontend
    ```
### Install dependencies:

    ```bash
    npm install
    ```

### Run the frontend:

    ```bash
    npm start
    ```

### Usage

    Access the frontend at http://localhost:3000

    Upload PDF receipts through the web interface

    View processed receipts in the dashboard

### API Endpoints

    POST /upload - Upload a receipt file

    POST /validate/<file_id> - Validate a PDF

    POST /process/<file_id> - Process a receipt

    GET /receipts - List all receipts

    GET /receipts/<id> - Get receipt details

    GET /merchants - List known merchants