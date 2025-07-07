import psycopg2
import re
import cv2
import numpy as np
import matplotlib.pyplot as plt
from paddleocr import PaddleOCR

# PostgreSQL connection setup
DB_PARAMS = {
    "dbname": "ocr_access_control",
    "user": "postgres",  # Change if using a different username
    "password": "meowthiebowingski",  # Replace with your actual password
    "host": "localhost",
    "port": "5432"
}

def connect_db():
    """Establish connection to PostgreSQL."""
    return psycopg2.connect(**DB_PARAMS)

def insert_non_resident(full_name, id_type, id_number):
    """Insert a new non-resident record into the database."""
    conn = connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO non_residents (full_name, id_type, id_number)
            VALUES (%s, %s, %s) RETURNING id;
        """, (full_name, id_type, id_number))
        
        non_resident_id = cursor.fetchone()[0]
        conn.commit()
        print(f"Inserted Non-Resident ID: {non_resident_id}")
        return non_resident_id

    except Exception as e:
        print(f"Database Error: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()

def insert_entry(non_resident_id):
    """Insert a new entry record for a non-resident."""
    conn = connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO entries (non_resident_id)
            VALUES (%s) RETURNING id;
        """, (non_resident_id,))
        
        entry_id = cursor.fetchone()[0]
        conn.commit()
        print(f"Inserted Entry ID: {entry_id}")
        return entry_id

    except Exception as e:
        print(f"Database Error: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()

def insert_exit(entry_id):
    """Insert an exit record for a non-resident."""
    conn = connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO exits (entry_id)
            VALUES (%s);
        """, (entry_id,))
        
        conn.commit()
        print(f"Exit recorded for Entry ID: {entry_id}")

    except Exception as e:
        print(f"Database Error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

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
        print(f"Checking for '{id_type}'...")  # Debugging statement to know which ID type we're checking
        
        for keyword in keywords:
            print(f"  Checking pattern: {keyword}")  # Debugging: Show each pattern being checked
            
            # Use re.search for pattern matching
            if re.search(keyword.lower(), extracted_text_lower):  # Use search to detect the keyword in the text
                print(f"  Match found for '{id_type}'")  # Debugging: If a match is found
                return id_type  # Return the matched ID type

    # If no match is found, return "Unknown ID Type"
    print("No match found.")  # Debugging: If no match is found
    return "Unknown ID Type"

def extract_registration_number(data, id_type):
    """Extract registration number from text based on ID format."""
    id_patterns = {
        "Philippine National ID": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",  # 1234-5678-9101-1213 or 1234567891011213
        "Driver's License": r"\b[A-Z0-9]{3}[-\s]?\d{2}[-\s]?\d{6}\b",  # 000-00-000000 or 000 00 000000
        "Postal ID": r"\b[A-Z]{3}[-\s]?\d{12}[A-Z]?\b",  # PRN 100141234567 P
        "PRC ID": r"\b\d{7}\b",  # 0012345 (No hyphen needed)
        "PhilHealth ID": r"\b\d{2}[-\s]?\d{8}[-\s]?\d{1}\b",  # 12-34567891-2 or 12 34567891 2
        "Unified Multi-Purpose ID/SSS ID": r"\b[A-Z]{3}[-\s]?\d{4}[-\s]?\d{7}[-\s]?\d\b"  # XYZ-0028-1215160-9 or XYZ 0028 1215160 9
    }
    
    pattern = id_patterns.get(id_type)
    if pattern: 
        match = re.search(pattern, data)
        return match.group(0) if match else "Not Found"
    return "Not Found"

def extract_name(data, id_type):
    """Extracts the full name from the given OCR-extracted text based on ID type."""
    
    if id_type == "Driver's License":
        name = re.search(r"(?:Name[,.]?\s*Middle\s*Name|Middle\s*Name|Name\s*,?\s*Middle\s*Name|Name\s*MiddleName)\s*([\w\s,\.]+?)(?=\s*(?:Nationality\s?|Sex\s?|Date\s?|Weight\s?|$))", data)
        if name:
            extracted_name = name.group(1).strip()

            # Check if there's a comma in the name, indicating last name before first name
            if ',' in extracted_name or '.' in extracted_name:
                parts = re.split('[,\.]', extracted_name)
                # Reorder so the part before the comma (last name) comes after the first/middle name
                reordered_name = f"{parts[1].strip()} {parts[0].strip()}"
                return reordered_name
            return extracted_name  # If no comma, return the name as it is

    elif id_type == "Philippine National ID":
        last_name_match = re.search(r"(?:Apelyido\s*/?\s*Last\s*Name|Apleyido\s*/?\s?Last\s*?Name)\s*([\w\s,.'\"-]+?)(?=\s*(?:Mga\s*Pangalan\s*/?\s*Given\s*Names|$))", data)
        given_name_match = re.search(r"(?:Mga\s*?Pangalan\s*/?\s*Given\s*Names)\s*([\w\s,.'\"-]+?)(?=\s*(?:Gitnang\s*Apelyido\s*/?\s*Middle\s*Name|$))", data)
        middle_name_match = re.search(r"(?:Gitnang\s*Apelyido\s*/?\s*Middle\s*Name)\s*([\w\s,.'\"-]+?)(?=(?:(e\s*)?ts|tsa|sa|a|Pets|Pet|Pe|Petsa\w?\s|Kapanganakan[\w\W]*\s*|Birth|$))", data)        
        
        last_name = last_name_match.group(1).strip() if last_name_match else ""
        given_name = given_name_match.group(1).strip() if given_name_match else ""
        middle_name = middle_name_match.group(1).strip() if middle_name_match else ""

        return f"{given_name} {middle_name} {last_name}".strip()

    
    elif id_type == "Postal ID":
        name = re.search(r"(?:\w?\sIDENTITY\s*CARD\s*?|\w?\s?CARD\s*?|\w?\s?Suffix)\s*([\w\s]+?)(?=\s\d{2,}|\sPRN|\sPOSTAL|$)", data)
        if name:
            return name.group(1).strip()
        return "Name not found"  # Added return in case name is not found

    elif id_type == "PRC ID":
        last_name_match = re.search(r"(?:\w?\s?LAST\w?\s?NAME)\s*([\w\s]+?)\s*(?:FIRST\w?\s?NAME\w?\s?|$)", data)
        given_name_match = re.search(r"(?:\w?\s?FIRST\w?\s?NAME)\s*([\w\s]+?)\s*(?:MIDDLE\w?\s?NAME\w?\s?|$)", data)
        middle_name_match = re.search(r"(?:\w?\s?MIDDLE\w?\s?NAME)\s*([\w\s]+?)\s*(?:REGISTRATION\w?\s?|$)", data)
        
        last_name = last_name_match.group(1).strip() if last_name_match else ""
        given_name = given_name_match.group(1).strip() if given_name_match else ""
        middle_name = middle_name_match.group(1).strip() if middle_name_match else ""
        
        return f"{given_name} {middle_name} {last_name}".strip()
    
    elif id_type == "Unified Multi-Purpose ID/SSS ID":
        last_name_match = re.search(r"(?:\w?\s?SUR\w?\s?NAME)\s*([\w\s]+?)\s*(?:GIVEN\w?\s?NAME\w?\s?|$)", data)
        given_name_match = re.search(r"(?:\w?\s?GIVEN\w?\s?NAME)\s*([\w\s]+?)\s*(?:MIDDLE\w?\s?NAME\w?\s?|$)", data)
        middle_name_match = re.search(r"(?:\w?\s?MIDDLE\w?\s?NAME)\s*([\w\s]+?)\s*(?:SEX\w?\s?|$)", data)
        
        last_name = last_name_match.group(1).strip() if last_name_match else ""
        given_name = given_name_match.group(1).strip() if given_name_match else ""
        middle_name = middle_name_match.group(1).strip() if middle_name_match else ""
    
        return f"{given_name} {middle_name} {last_name}".strip()
    
    if id_type == "PhilHealth ID":
        name = re.search(r"(?:\d{2}-\d{8}-\d{1})\s*([\w\s,]+?)(?=\s*(?:\w?\s?JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|$))", data)
        if name:
            extracted_name = name.group(1).strip()

            # Check if there's a comma in the name, indicating last name before first name
            if ',' in extracted_name or '.' in extracted_name:
                parts = re.split('[,\.]', extracted_name)
                # Reorder so the part before the comma (last name) comes after the first/middle name
                reordered_name = f"{parts[1].strip()} {parts[0].strip()}"
                return reordered_name
            return extracted_name  # If no comma, return the name as it is
        return "Name not found"

    return "Name not found"

# Initialize PaddleOCR model
ocr = PaddleOCR(use_angle_cls=True, lang='en')

# Load and process the image
image_path = "C:\\Users\\Julia Mae Panes\\Documents\\OCR\\sample IDs\\sample-national_id-3.png"
result = ocr.ocr(image_path, cls=True)

# Extract detected text
extracted_text = " ".join([word[1][0] for line in result for word in line])
print(f"Extracted Text:\n{extracted_text}\n")

# Detect ID type
id_type = detect_id_type(extracted_text)
print(f"Detected ID Type: {id_type}\n")

# Extract Registration Number
registration_number = extract_registration_number(extracted_text, id_type)
print(f"Extracted Registration Number: {registration_number}\n")

# Extract Name
extracted_name = extract_name(extracted_text, id_type)
print(f"Extracted Name: {extracted_name}\n")

# Insert Data into Database
if id_type != "Unknown ID Type" and registration_number != "Not Found":
    non_resident_id = insert_non_resident(extracted_name, id_type, registration_number)
    if non_resident_id:
        entry_id = insert_entry(non_resident_id)
        if entry_id:
            # Simulate exit record after some time (optional)
            insert_exit(entry_id)

# Load image with OpenCV and display it
image = cv2.imread(image_path)
plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
plt.axis('off')
plt.title(f"ID Type: {id_type}\nReg. No: {registration_number}\nName:{extracted_name}")
plt.show()
