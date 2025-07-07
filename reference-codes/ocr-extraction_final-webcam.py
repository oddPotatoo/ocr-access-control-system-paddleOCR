import qrcode
import psycopg2
import re
from thefuzz import fuzz
import cv2
import numpy as np
import matplotlib.pyplot as plt
from paddleocr import PaddleOCR
import uuid  # Unique QR Codes for every entry
from datetime import datetime  # For entry_time and exit_time
import os  # For directory operations

# PostgreSQL connection setup
DB_PARAMS = {
    "dbname": "non_resident_logs",  # Replace with your new database name
    "user": "postgres",  # Change if using a different username
    "password": "meowthiebowingski",  # Replace with your actual password
    "host": "localhost",
    "port": "5432"
}

def connect_db():
    """Establish connection to PostgreSQL."""
    return psycopg2.connect(**DB_PARAMS)

def insert_vehicle_entry(full_name, id_type, id_number, qr_code):
    """Insert vehicle entry into the database."""
    conn = connect_db()
    cursor = conn.cursor()

    # Insert into the single table
    cursor.execute("""
        INSERT INTO "NonResidentLogs" (full_name, id_type, id_number, qr_code, entry_time)
        VALUES (%s, %s, %s, %s, %s) RETURNING id;
    """, (full_name, id_type, id_number, qr_code, datetime.now()))
    
    entry_id = cursor.fetchone()[0]
    conn.commit()
    
    cursor.close()
    conn.close()
    return entry_id

def generate_qr_code(data):
    """Generate QR Code and save it as an image."""
    qr = qrcode.make(data)

    # Ensure the directory exists
    qr_directory = "qrcodes"
    if not os.path.exists(qr_directory):
        os.makedirs(qr_directory)

    # Save QR code
    qr_path = f"{qr_directory}/{data}.png"
    qr.save(qr_path)
    return qr_path

def capture_from_webcam():
    """Capture an image from the webcam and preprocess it."""
    cap = cv2.VideoCapture(3)  # Open webcam
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            continue

        cv2.imshow("Press 's' to Scan or 'q' to Quit", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('s'):  # Press 's' to scan
            # Ensure the captureIDs directory exists
            capture_directory = "captureIDs"
            if not os.path.exists(capture_directory):
                os.makedirs(capture_directory)

            # Generate a unique filename for the captured image
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = f"{capture_directory}/captured_id_{timestamp}.jpg"

            # Convert to grayscale and save the image
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            cv2.imwrite(image_path, gray)  # Save processed image

            cap.release()
            cv2.destroyAllWindows()
            return image_path
        elif key == ord('q'):  # Press 'q' to quit
            cap.release()
            cv2.destroyAllWindows()
            return None

def detect_id_type(extracted_text):
    """Detect the ID type based on extracted text."""
    # Remove common phrases that may interfere with detection
    extracted_text = re.sub(r"\b(REPUBLIC OF THE PHILIPPINES|REPUBLIKA NG PILIPINAS|Republic of the Philippines|Republika ng Pilipinas)\b", "", extracted_text, flags=re.IGNORECASE)

    # ID keyword patterns
    id_keywords = {
        "Philippine National ID": [
            r"PAMBANSANG\s*PAGKAKAKILANLAN\s*", 
            r"Philippine\s*Identification\s*Card\s*"
        ],
        "Driver's License": [
            r"NON-PROFESSIONAL\s*DRIVER'S\s*LICENSE\s*", 
            r"PROFESSIONAL\s*DRIVER'S\s*LICENSE\s*", 
            r"DRIVER'S\s*LICENSE\s*", 
            r"LAND\s*TRANSPORTATION\s*OFFICE\s*", 
            r"DEPARTMENT\s*OF\s*TRANSPORTATION\s*"
        ],
        "Postal ID": [
            r"POSTAL\s*IDENTITY\s*CARD\s*", 
            r"Philippine\s*Postal\s*Corporation\s*", 
            r"POSTAL\s*", 
            r"PHLPOST\s*"
        ],
        "Unified Multi-Purpose ID/SSS ID": [
            r"Unified\s*Multi-Purpose\s*ID\s*", 
            r"CRN\s*"
        ], 
        "PRC ID": [
            r"PROFESSIONAL\s*IDENTIFICATION\s*CARD\s*", 
            r"PROFESSIONAL\s*REGULATION\s*COMMISSION\s*"
        ],
        "PhilHealth ID": [
            r"Philippine\s*Health\s*Insurance\s*Corporation\s*", 
            r"Health\s*", 
            r"PhilHealth\s*"
        ]
    }

    # Convert extracted text to lowercase for comparison
    extracted_text_lower = extracted_text.lower()

    # Iterate through the ID keywords
    for id_type, keywords in id_keywords.items():
        for keyword in keywords:
            if re.search(keyword.lower(), extracted_text_lower):
                return id_type  # Return the matched ID type

    return "Unknown ID Type"

def extract_registration_number(data, id_type):
    """Extract registration number from text based on ID format."""
    id_patterns = {
        "Philippine National ID": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",  # 1234-5678-9101-1213 or 1234567891011213
        "Driver's License": r"\b[A-Z0-9]{3}[-\s]?\d{2}[-\s]?\d{6}\b",  # 000-00-000000 or 000 00 000000
        "Postal ID": r"\bPRN\s+[A-Z]\d{11}\b",  # PRN E20220548293
        "PRC ID": r"\b\d{7}\b",  # 0012345 (No hyphen needed)
        "PhilHealth ID": r"\b\d{2}[-\s]?\d{8}[-\s]?\d{1}\b",  # 12-34567891-2 or 12 34567891 2
        "Unified Multi-Purpose ID/SSS ID": r"\b[A-Z]{3}[-\s]?\d{4}[-\s]?\d{7}[-\s]?\d\b"  # XYZ-0028-1215160-9 or XYZ 0028 1215160 9
    }
    
    pattern = id_patterns.get(id_type)
    if pattern: 
        match = re.search(pattern, data)
        return match.group(0) if match else "Not Found"
    return "Not Found"

def fuzzy_match(text, keywords, threshold=70):
    """Check if extracted text closely matches any expected keyword."""
    for keyword in keywords:
        similarity = fuzz.partial_ratio(text.lower(), keyword.lower())
        if similarity >= threshold:
            return keyword  # Return the best match
    return text  # If no match found, return original text

def extract_name(data, id_type):
    """Extracts the full name from the given OCR-extracted text based on ID type, using fuzzy matching."""
    # Expected keyword variations for different fields
    last_name_keywords = ["Apelyido/Last Name", "Apleyido/Last Name", "Apeyido/Last Name", "Surname", "LAST NAME", "SURNAME", "SUR NAME"]
    given_name_keywords = ["Mga Pangalan/Given Names", "tga Pargalan/Given Names", "Mea Pangalan/Given Names", "First Name", "FIRST NAME", "FirstName", "FIRSTNAME"]
    middle_name_keywords = ["Gitnang Apelyido/Middle Name", "Gitnang Apelyido/Middie Name", "Gitnang Apelyido/Middie Nome", "Middle Name", "MIDDLE Name", "MIDDLENAME", "middlename"]

    if id_type == "Driver's License":
        name = re.search(r"(?:Name[,.]?\s*Middle\s*Name|Middle\s*Name|Name\s*,?\s*Middle\s*Name|Name\s*MiddleName)\s*([\w\s,\.]+?)(?=\s*(?:Nationality\s?|Sex\s?|Date\s?|Weight\s?|$))", data)
        if name:
            extracted_name = name.group(1).strip()
            if ',' in extracted_name or '.' in extracted_name:
                parts = re.split('[,\.]', extracted_name)
                reordered_name = f"{parts[1].strip()} {parts[0].strip()}"
                return reordered_name
            return extracted_name

    elif id_type == "Philippine National ID":
        last_name_match = re.search(r"(?:Apelyido\s*/?\s*Last\s*Name|Apleyido\s*/?\s?Last\s*?Name|Apeyido\s*/?\s?Last\s*?Name|Ape'yido\s*/?\s?Last\s*?Name)\s*([\w\s,.'\"-]+?)(?=\s*(?:Mga\s*Pangalan\s*/?\s*Given\s*Names|tga\s*Pargalan\s*/?\s*Given\s*Names|Mea\s*Pangalan\s*/?\s*Given\s*Names|$))", data)
        given_name_match = re.search(r"(?:Mga\s*?Pangalan\s*/?\s*Given\s*Names|tga\s*Pargalan\s*/?\s*Given\s*Names|Mea\s*Pangalan\s*/?\s*Given\s*Names)\s*([\w\s,.'\"-]+?)(?=\s*(?:Gitnang\s*Apelyido\s*/?\s*Middle\s*Name|Gitnang\s*Apelyido\s*/?\s*Middie\s*Name|Gitnang\s*Apelyido\s*/?\s*Middie\s*Nome|$))", data)
        middle_name_match = re.search(r"(?:Gitnang\s*Apelyido\s*/?\s*Middle\s*Name|Gitnang\s*Apelyido\s*/?\s*Middie\s*Name|Gitnang\s*Apelyido\s*/?\s*Middie\s*Nome)\s*([\w\s,.'\"-]+?)(?=(?:(e\s*)?ts|tsa|sa|a|Pets|Pet|Pe|Petsa\w?\s*|Kapanganakan[\w\W]*\s*|Birth|$))", data)

    elif id_type == "Postal ID":
        name_match = re.search(r"(?:First\s*Name\s*,?\s*Middle\s*Name\s*,?\s*Surname\s*,?\s*Suffix|First\s*NMidd\s*NameSumameSuffi|First\s*Nan\.Middle\s*Name\.Sumame\.Suffi|First\s*Name\s*Midd\s*NameSumame\s*Suffi)\s*([\w\s]+)", data)
        if not name_match:
            name_match = re.search(r"IDENTITY\s*CARD\s*([\w\s]+?)(?=\s*(?:ADDRESS|POSTAL|PRN|\d{2,}|\b[A-Z]{3}[-\s]?\d{12}\b|$))", data)
        return name_match.group(1).strip() if name_match else "Name not found"

    elif id_type == "PRC ID":
        last_name_match = re.search(r"(?:\w?\s?LAST\w?\s?NAME)\s*([\w\s]+?)\s*(?:FIRST\w?\s?NAME\w?\s?|$)", data)
        given_name_match = re.search(r"(?:\w?\s?FIRST\w?\s?NAME)\s*([\w\s]+?)\s*(?:MIDDLE\w?\s?NAME\w?\s?|$)", data)
        middle_name_match = re.search(r"(?:\w?\s?MIDDLE\w?\s?NAME)\s*([\w\s]+?)\s*(?:REGISTRATION\w?\s?|$)", data)

    elif id_type == "Unified Multi-Purpose ID/SSS ID":
        last_name_match = re.search(r"(?:\w?\s?SUR\w?\s?NAME)\s*([\w\s]+?)\s*(?:GIVEN\w?\s?NAME\w?\s?|$)", data)
        given_name_match = re.search(r"(?:\w?\s?GIVEN\w?\s?NAME)\s*([\w\s]+?)\s*(?:MIDDLE\w?\s?NAME\w?\s?|$)", data)
        middle_name_match = re.search(r"(?:\w?\s?MIDDLE\w?\s?NAME)\s*([\w\s]+?)\s*(?:SEX\w?\s?|$)", data)

    elif id_type == "PhilHealth ID":
        name = re.search(r"(?:\d{2}-\d{8}-\d{1})\s*([\w\s,]+?)(?=\s*(?:\w?\s?JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|$))", data)
        if name:
            extracted_name = name.group(1).strip()
            if ',' in extracted_name or '.' in extracted_name:
                parts = re.split('[,\.]', extracted_name)
                reordered_name = f"{parts[1].strip()} {parts[0].strip()}"
                return reordered_name
            return extracted_name
        return "Name not found"

    # Apply fuzzy matching if any names were found
    last_name = fuzzy_match(last_name_match.group(1).strip(), last_name_keywords) if last_name_match else ""
    given_name = fuzzy_match(given_name_match.group(1).strip(), given_name_keywords) if given_name_match else ""
    middle_name = fuzzy_match(middle_name_match.group(1).strip(), middle_name_keywords) if middle_name_match else ""

    return f"{given_name} {middle_name} {last_name}".strip()

# Initialize PaddleOCR model
ocr = PaddleOCR(use_angle_cls=True, lang='en')

# Capture image from webcam
image_path = capture_from_webcam()
if image_path is None:
    print("No image captured. Exiting...")
    exit()

# Process the image with OCR
result = ocr.ocr(image_path, cls=True)

# Extract detected text
extracted_text = " ".join([word[1][0] for line in result for word in line])
print(f"Extracted Text:\n{extracted_text}\n")

# Detect ID type
id_type = detect_id_type(extracted_text)
print(f"Detected ID Type: {id_type}\n")

# Extract ID Number (Registration Number)
registration_number = extract_registration_number(extracted_text, id_type)
print(f"Extracted ID Number: {registration_number}\n")

# Extract Name
extracted_name = extract_name(extracted_text, id_type)
print(f"Extracted Name: {extracted_name}\n")

# Generate Unique QR Code for This Entry
qr_code_value = str(uuid.uuid4())  # Generate unique QR string
qr_code_path = generate_qr_code(qr_code_value)

print(f"Generated QR Code: {qr_code_value}")
print(f"Saved at: {qr_code_path}")

# Insert Data into Database
entry_id = insert_vehicle_entry(extracted_name, id_type, registration_number, qr_code_value)
print(f"Entry inserted with ID: {entry_id}")

# Display the QR code
qr_image = cv2.imread(qr_code_path)
plt.imshow(cv2.cvtColor(qr_image, cv2.COLOR_BGR2RGB))
plt.axis('off')
plt.title(f"QR Code for {extracted_name}")
plt.show()

# Display the captured image
image = cv2.imread(image_path)
plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
plt.axis('off')
plt.title(f"ID Type: {id_type}\nReg. No: {registration_number}\nName:{extracted_name}")
plt.show()