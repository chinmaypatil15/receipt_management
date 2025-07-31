import os
import re
from flask_cors import CORS
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime
import pytesseract
from pdf2image import convert_from_path
import PyPDF2

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
ALLOWED_EXTENSIONS = {'pdf'}
DATABASE = 'receipts.db'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def match_merchant(text):
    """Match text against known merchants database"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT search_pattern, display_name FROM known_merchant')
    merchants = cursor.fetchall()
    conn.close()
    
    text_lower = text.lower()
    for pattern, name in merchants:
        if pattern in text_lower:
            return name
    
    # If no match found, try to find the most merchant-like line
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    for line in lines:
        # Simple heuristic for merchant names
        if (len(line) > 4 and not line[0].isdigit() 
            and not any(word in line.lower() for word in ['tax', 'total', 'subtotal', 'date'])):
            return line.title()
    
    return None

# Initialize database
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Create receipt_file table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS receipt_file (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        is_valid BOOLEAN DEFAULT 0,
        invalid_reason TEXT,
        is_processed BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create receipt table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS receipt (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchased_at TIMESTAMP,
        merchant_name TEXT,
        total_amount REAL,
        file_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (file_path) REFERENCES receipt_file (file_path)
    )
    ''')

    # Add known_merchant table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS known_merchant (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        search_pattern TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        category TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Populate with some initial data
    cursor.execute('SELECT COUNT(*) FROM known_merchant')
    if cursor.fetchone()[0] == 0:
        default_merchants = [
            ('cheesecake factory', 'The Cheesecake Factory', 'Restaurant'),
            ('walmart', 'Walmart', 'Retail'),
            ('target', 'Target', 'Retail'),
            ('starbucks', 'Starbucks', 'Cafe'),
            ('whole foods', 'Whole Foods Market', 'Grocery'),
            ('amazon', 'Amazon', 'Online'),
            ('cvs', 'CVS Pharmacy', 'Pharmacy'),
            ('home depot', 'The Home Depot', 'Hardware')
        ]
        cursor.executemany('''
        INSERT INTO known_merchant (search_pattern, display_name, category)
        VALUES (?, ?, ?)
        ''', default_merchants)
    
    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_upload_path(purchase_date=None):
    """Get the appropriate upload path based on purchase year"""
    base_path = app.config['UPLOAD_FOLDER']
    
    if purchase_date:
        try:
            # Try to parse the purchase date to get the year
            if isinstance(purchase_date, str):
                # Handle different date formats
                if '/' in purchase_date:
                    year = purchase_date.split('/')[-1]
                elif '-' in purchase_date:
                    year = purchase_date.split('-')[-1]
                else:
                    year = datetime.now().year
            else:
                year = purchase_date.year
        except:
            year = datetime.now().year
    else:
        year = datetime.now().year
    
    # Ensure the year directory exists
    year_path = os.path.join(base_path, str(year))
    os.makedirs(year_path, exist_ok=True)
    
    return year_path


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        
        # Initially store in the current year's directory
        upload_path = get_upload_path()
        filepath = os.path.join(upload_path, filename)
        file.save(filepath)
        
        # Store metadata in database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO receipt_file (file_name, file_path) 
        VALUES (?, ?)
        ''', (filename, filepath))
        file_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'File uploaded successfully',
            'file_id': file_id,
            'file_name': filename
        }), 201
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/validate/<int:file_id>', methods=['POST'])
def validate_file(file_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Get file info
    cursor.execute('SELECT file_path FROM receipt_file WHERE id = ?', (file_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return jsonify({'error': 'File not found'}), 404
    
    filepath = result[0]
    is_valid = False
    invalid_reason = None
    
    try:
        # Validate PDF
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            if len(reader.pages) > 0:
                is_valid = True
    except Exception as e:
        invalid_reason = str(e)
    
    # Update database
    cursor.execute('''
    UPDATE receipt_file 
    SET is_valid = ?, invalid_reason = ?, updated_at = ?
    WHERE id = ?
    ''', (is_valid, invalid_reason, datetime.now(), file_id))
    conn.commit()
    
    # Get updated record
    cursor.execute('SELECT * FROM receipt_file WHERE id = ?', (file_id,))
    record = cursor.fetchone()
    conn.close()
    
    if record:
        return jsonify({
            'file_id': record[0],
            'is_valid': bool(record[3]),
            'invalid_reason': record[4]
        }), 200
    
    return jsonify({'error': 'File not found'}), 404

@app.route('/process/<int:file_id>', methods=['POST'])
def process_file(file_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Get file info
    cursor.execute('SELECT file_path, is_valid FROM receipt_file WHERE id = ?', (file_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return jsonify({'error': 'File not found'}), 404
    
    old_filepath, is_valid = result
    
    if not is_valid:
        conn.close()
        return jsonify({'error': 'File is not valid'}), 400
    
    try:
        # Convert PDF to image
        images = convert_from_path(old_filepath)
        extracted_text = ""
        
        for image in images:
            extracted_text += pytesseract.image_to_string(image)
        
        # Enhanced parsing logic
        merchant_name = match_merchant(extracted_text)
        total_amount = None
        purchased_at = None
        
        # Common patterns in receipts
        lines = extracted_text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Total amount detection
            if not total_amount:
                total_keywords = ['total', 'amount', 'balance', 'payment']
                if any(keyword in line.lower() for keyword in total_keywords):
                    # Look for amounts in this line or next lines
                    amount_line = line + ' ' + ' '.join(lines[i:i+3])
                    # Find all potential amounts
                    amounts = re.findall(r'\d+\.\d{2}', amount_line)
                    if amounts:
                        total_amount = max(float(amt) for amt in amounts)
            
            # Date detection
            if not purchased_at:
                # Common date patterns
                date_patterns = [
                    r'\d{1,2}/\d{1,2}/\d{2,4}',  # MM/DD/YYYY
                    r'\d{1,2}-\d{1,2}-\d{2,4}',  # MM-DD-YYYY
                    r'\d{1,2} \w{3,} \d{4}',     # 01 January 2023
                ]
                for pattern in date_patterns:
                    match = re.search(pattern, line)
                    if match:
                        purchased_at = match.group()
                        break
        
        # Move file to appropriate year directory if we found a purchase date
        if purchased_at:
            new_upload_path = get_upload_path(purchased_at)
            filename = os.path.basename(old_filepath)
            new_filepath = os.path.join(new_upload_path, filename)
            
            # Only move if the path is different
            if os.path.dirname(old_filepath) != os.path.dirname(new_filepath):
                os.rename(old_filepath, new_filepath)
                filepath_for_db = new_filepath
            else:
                filepath_for_db = old_filepath
        else:
            filepath_for_db = old_filepath
        
        # Insert into receipt table
        cursor.execute('''
        INSERT INTO receipt (purchased_at, merchant_name, total_amount, file_path)
        VALUES (?, ?, ?, ?)
        ''', (purchased_at, merchant_name, total_amount, filepath_for_db))
        
        # Update receipt_file table with new path if it changed
        if purchased_at and filepath_for_db != old_filepath:
            cursor.execute('''
            UPDATE receipt_file 
            SET file_path = ?, is_processed = 1, updated_at = ?
            WHERE id = ?
            ''', (filepath_for_db, datetime.now(), file_id))
        else:
            cursor.execute('''
            UPDATE receipt_file 
            SET is_processed = 1, updated_at = ?
            WHERE id = ?
            ''', (datetime.now(), file_id))
        
        receipt_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'File processed successfully',
            'receipt_id': receipt_id,
            'merchant_name': merchant_name,
            'total_amount': total_amount,
            'purchased_at': purchased_at,
            'raw_text': extracted_text,
            'file_path': filepath_for_db
        }), 200
    
    except Exception as e:
        conn.close()

@app.route('/receipts', methods=['GET'])
def get_receipts():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT r.id, r.purchased_at, r.merchant_name, r.total_amount, 
           rf.file_name, rf.created_at as uploaded_at
    FROM receipt r
    JOIN receipt_file rf ON r.file_path = rf.file_path
    ORDER BY r.created_at DESC
    ''')
    
    receipts = []
    for row in cursor.fetchall():
        receipts.append({
            'id': row[0],
            'purchased_at': row[1],
            'merchant_name': row[2],
            'total_amount': row[3],
            'file_name': row[4],
            'uploaded_at': row[5]
        })
    
    conn.close()
    return jsonify(receipts), 200

@app.route('/receipts/<int:receipt_id>', methods=['GET'])
def get_receipt(receipt_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT r.id, r.purchased_at, r.merchant_name, r.total_amount, 
           r.file_path, r.created_at, r.updated_at,
           rf.file_name, rf.is_valid, rf.is_processed
    FROM receipt r
    JOIN receipt_file rf ON r.file_path = rf.file_path
    WHERE r.id = ?
    ''', (receipt_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return jsonify({'error': 'Receipt not found'}), 404
    
    return jsonify({
        'id': row[0],
        'purchased_at': row[1],
        'merchant_name': row[2],
        'total_amount': row[3],
        'file_path': row[4],
        'created_at': row[5],
        'updated_at': row[6],
        'file_name': row[7],
        'is_valid': bool(row[8]),
        'is_processed': bool(row[9])
    }), 200

@app.route('/merchants', methods=['GET'])
def get_merchants():
    """Get list of all known merchants"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, search_pattern, display_name, category FROM known_merchant')
    merchants = []
    for row in cursor.fetchall():
        merchants.append({
            'id': row[0],
            'search_pattern': row[1],
            'display_name': row[2],
            'category': row[3]
        })
    
    conn.close()
    return jsonify(merchants), 200

if __name__ == '__main__':
    app.run(debug=True)
