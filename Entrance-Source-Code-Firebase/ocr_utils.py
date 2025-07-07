import re
from thefuzz import fuzz, process
import cv2
import qrcode
import numpy as np
import matplotlib.pyplot as plt
from paddleocr import PaddleOCR
import uuid
import os
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
# Construct the full path to the credentials file
cred_path = os.path.join(script_dir, "ocr-access-control-46a21-firebase-adminsdk-fbsvc-a648214418.json")

# Firebase initialization (singleton pattern)
def initialize_firebase():
    if not firebase_admin._apps:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cred_path = os.path.join(script_dir, "ocr-access-control-46a21-firebase-adminsdk-fbsvc-a648214418.json")
        
        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://ocr-access-control-46a21.firebaseio.com/'
            })
            print("Firebase initialized successfully")
            return True
        except FileNotFoundError:
            print(f"Error: Firebase credentials file not found at {cred_path}")
            return False
        except Exception as e:
            print(f"Error initializing Firebase: {e}")
            return False
    return True

def insert_vehicle_entry(full_name, id_type, id_number, qr_code):
    """Insert vehicle entry with transaction-based sequential IDs."""
    if not initialize_firebase():
        return None

    try:
        ref = db.reference('NonResidentLogs')
        counter_ref = db.reference('ID_Counter')

        def transaction_update(current_value):
            if current_value is None:
                return 1  # Start with 1 if no counter exists
            return current_value + 1

        # Atomically increment the counter and get new ID
        new_id = counter_ref.transaction(transaction_update)

        if new_id:  # Transaction succeeded
            new_entry = {
                'full_name': full_name,
                'id_type': id_type,
                'id_number': id_number,
                'qr_code': qr_code,
                'entry_time': datetime.now().isoformat(),
                'exit_time': None
            }
            ref.child(f"0{new_id}").set(new_entry)
            print(f"Successfully inserted entry with ID: {new_id}")
            return new_id
        else:
            print("Failed to generate sequential ID")
            return None

    except Exception as e:
        print(f"Error inserting into Firebase: {e}")
        return None

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
    """Extract registration number from text based on ID format and mask all but the last 4 characters, retaining hyphens."""
    id_patterns = {
        "Philippine National ID": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",  # 1234-5678-9101-1213 or 1234567891011213
        "Driver's License": r"\b(?:[A-Z0-9]{2,3}-[A-Z0-9]{2}-[A-Z0-9]{6}|[A-Z0-9]{2,3}-?[0-9]{2,4}-?[0-9]{6})\b",
        "Postal ID": r"PRN\s*[A-Z0-9]*\s*\d{11,12}[A-Z]?\b",  # PRN E20220548293 or PRN 100141234567P
        "PRC ID": r"\b[A-Z0-9]{7}\b",  # 0012345 or ABC1234
        "PhilHealth ID": r"\b\d{2}[-\s]?\d{8}[-\s]?\d{1}\b",  # 12-34567891-2
        "Unified Multi-Purpose ID/SSS ID": r"\b[A-Z0-9]{3}[-\s]?[A-Z0-9]{4}[-\s]?[A-Z0-9]{7}[-\s]?[A-Z0-9]{1}\b"  # XYZ-0028-1215160-9 or ABC 1234 1234567 D
    }
    
    pattern = id_patterns.get(id_type)
    if pattern:
        match = re.search(pattern, data)
        if match:
            # Extract the matched ID
            full_id = match.group(0)
            
            # Find the positions of the last 4 characters (digits or letters)
            last_four_indices = range(len(full_id) - 5, len(full_id))  # Get the indices of the last 4 characters
            
            # Mask all characters except the last 4 characters, retaining hyphens and spaces
            masked_id = []
            for i, char in enumerate(full_id):
                if i in last_four_indices or not char.isalnum():
                    masked_id.append(char)  # Retain the last 4 characters, hyphens, and spaces
                else:
                    masked_id.append("*")  # Mask all other characters
            
            return "".join(masked_id)
        else:
            return "Not Found"
    return "Not Found"

def fuzzy_match(text, keywords, threshold=70):
    """
    Check if extracted text closely matches any expected keyword using case-insensitive comparison.
    
    Possible Outputs:
    - If a match is found above the threshold, returns the matched keyword.
    - If no match is found, returns the original text.
    """
    if not text or not keywords:
        return text
    # Case-insensitive comparison using a processor
    best_match, score = process.extractOne(
        text,
        keywords,
        scorer=fuzz.partial_ratio,
        processor=lambda x: x.lower()
    )
    return best_match if score >= threshold else text

def remove_unwanted_words(text, unwanted_words, threshold=70):
    """
    Removes unwanted words or phrases from the extracted text using fuzzy matching.
    """
    for word in unwanted_words:
        # Check if the text contains a fuzzy match to the unwanted word
        if fuzzy_match(text, [word], threshold) == word:
            # Remove all case-insensitive occurrences of the unwanted word
            text = re.sub(re.escape(word), '', text, flags=re.IGNORECASE)
            # Clean up extra spaces
            text = re.sub(r'\s+', ' ', text).strip()
    return text

def normalize_ocr_spaces(text):
    """ Insert missing spaces between headers and names. """
    fixed_text = re.sub(r"(SURNAME|SORNAME|GIVENNAME|MIDDLENAME)",
                        r" \1 ", text.upper())  # Ensure consistent case
    fixed_text = re.sub(r'\s+', ' ', fixed_text).strip()  # Normalize multiple spaces
    return fixed_text


def extract_name(data, id_type):
    """
    Extracts the full name from the given OCR-extracted text based on ID type, using fuzzy matching.
    """

    keyword_variations = {
        "Driver's License": {
            "keywords": ["Last Name", "First Name", "Middle Name"],
            "unwanted": ["Nationality","Nationallty", "Noticnalty", "Date of Birth", "Weight", "Height", "Sex", "Address", "License No", "Expiration Date", "Agency Code", "Blood Type", "Eyes Color", "Restrictions", "Conditions"]
        },
        "Philippine National ID": {
            "keywords": ["Apelyido/Last Name", "Mga Pangalan/Given Names", "Gitnang Apelyido/Middle Name"],
            "unwanted": ["Petsang Kapanganakan", "Date of Birth", "Tirahan", "Address", "Philippine Identification Card", "PAMBANSANG PAGKAKAKILANLAN"]
        },
        "Postal ID": {
            "keywords": ["First Name", "Middle Name", "Surname"],
            "unwanted": ["Philippine Postal Corporation", "POSTAL IDENTITY CARD", "PHILPOSTS", "Address", "PRN", "FINL", "PREMIUM"]
        },
        "PRC ID": {
            "keywords": ["LAST NAME", "FIRST NAME", "MIDDLE NAME"],
            "unwanted": ["PROFESSIONAL REGULATION COMMISSION", "PROFESSIONAL IDENTIFICATION CARD", "REGISTRATION NO", "REGISTRATION DATE", "VALID UNTIL", "OCCUPATIONAL THERAPY TECHNICIAN"]
        },
        "Unified Multi-Purpose ID/SSS ID": {
            "keywords": ["SURNAME", "GIVEN NAME", "MIDDLE NAME"],
            "unwanted": ["Unified Multi-Purpose ID", "CRN", "DATE OF BIRTH", "ADDRESS", "FEMALE", "MALE", "SEX", "SURNAME", "GIVEN NAME", "GIVENNAME", "MIDDLE NAME", "NAME"]
        },
        "PhilHealth ID": {
            "keywords": ["First Name", "Middle Name", "Last Name"],
            "unwanted": ["Philippine Health Insurance Corporation", "SignUnre", "FORMAL ECONOMY", "MALE", "FEMALE", "Date of Birth"]
        }
    }
    
    # Get keywords and unwanted words for the current ID type
    keywords = keyword_variations[id_type]["keywords"]
    unwanted_words = keyword_variations[id_type]["unwanted"]
    
    # Driver's License handling (example, apply similar logic to other ID types)
    if id_type == "Driver's License":
        name_match = re.search(
            r"(?:Last|Lest|Lust|Last\s*Nane)\s*Name\s*[,\.\-]?\s*"
            r"(?:First|Frst|Fist|First\s*Nane)\s*Name\s*[,\.\-]?\s*"
            r"(?:Middle|Midle|Middie|Middle\s*Nane)\s*Name\s*"
            r"([A-Z]+)\s*[,\.\-]?\s*([A-Z]+(?:\s+[A-Z]+)*)\s*([A-Z]*)\s*"
            r"(?=Nationality|Nationallty|Noticnalty|Date\s*of\s*Birth|Weight|Height|Sex|$)",
            data,
            re.I
        )
        if name_match:
            last_name, first_name, middle_name = name_match.groups()
            uncleaned_name = f"{first_name} {middle_name} {last_name}".strip()
            
            # Clean extracted name
            extracted_name = remove_unwanted_words(uncleaned_name, unwanted_words)
            return extracted_name

        return extracted_name if extracted_name else "Name not found"


    elif id_type == "Philippine National ID":
        # Enhanced regex patterns with strict boundaries
        last_name_regex = r"""
            (?:Ap\w*?yido\s*[/\\.\-]?\s*Last[\.\s]*Name\w*)  # Fixed: \s* instead of \s+ for "LastName"
            \s*([A-Z]+(?:[\s\-][A-Z]+)*)  # Last name capture
            (?=\s*(?:Mga\s+Pangalan|tga\s+Pargalan|Mga|Mea|Mea\s+Pangalan|Given\s+Names|$))
        """
        
        given_name_regex = r"""
            (?:Mga\s*Pangalan\s*[/\\]?\s*Given['\s]*Name['\s]?\w*)
            \s*([A-Z]+(?:[\s\-][A-Z]+)*)  # Given name capture
            (?=\s*(?:Gitnang['\s-]?Apelyido|[G]?itnang|Gitnang['\s-]?|Midd?l?e\s+Name|$))
        """
        
        middle_name_regex = r"""
            (?:Gitnang['\s-]*Ap?e?lyi?do\s*[/\\]?\s*Midd?l?e\s*Name\w*)  # Flexible header
            \s*([A-Z]+(?:[\s\-][A-Z]+)*)  # Middle name capture
            (?=\s*(?:[PR]?etsa|[PR]?etsa\s*ng\s*Kapanganakan|Date\s+of\s+Birth|$))  # Ensure it stops before irrelevant text
        """

        # Execute regex with flags
        last_name_match = re.search(last_name_regex, data, re.X | re.I)
        given_name_match = re.search(given_name_regex, data, re.X | re.I)
        middle_name_match = re.search(middle_name_regex, data, re.X | re.I) 

        def clean_ocr_text(text):
            text = re.sub(r'\s+', ' ', re.sub(r'[^A-Z\s-]', '', text.strip()))  # Remove non-alphabetic chars
            text = re.sub(r'\b[A-Z]\b', '', text)  # Remove stray single-letter words (like "K")
            return text.strip()

        last_name = clean_ocr_text(last_name_match.group(1)) if last_name_match else ""
        given_name = clean_ocr_text(given_name_match.group(1)) if given_name_match else ""
        middle_name = clean_ocr_text(middle_name_match.group(1)) if middle_name_match else ""

        uncleaned_name = f"{given_name} {middle_name} {last_name}".strip()
        
        # Remove unwanted words from extracted name
        extracted_name = remove_unwanted_words(uncleaned_name, unwanted_words)
        
        return extracted_name if extracted_name else "Name not found"

    elif id_type == "Postal ID":
        name = re.search(
            r"(?:\w?\sIDENTITY\s*CARD\s*?|\w?\s?CARD\s*?|\w?\s?Suffix)\s*([\w\s]+?)(?=\s\d{2,}|\sPRN|\sPOSTAL|$)",
            data,
            re.I  # Added case-insensitive flag
        )

        if name:
            extracted_name = name.group(1).strip()

            # Apply similar logic from Driver's License (removing unwanted words)
            extracted_name = remove_unwanted_words(extracted_name, unwanted_words)

            return extracted_name  

        return extracted_name if extracted_name else "Name not found"
    
    elif id_type == "PRC ID":
        # Step 1: Fix OCR Issues (same as in Unified Multi-Purpose ID/SSS ID)
        fixed_data = normalize_ocr_spaces(data)

        # Keep the original regex patterns
        last_name_match = re.search(r"(?:\w?\s?LAST\w?\s?NAME)\s*([\w\s]+?)\s*(?:FIRST\w?\s?NAME\w?\s?|$)", fixed_data, re.I)
        given_name_match = re.search(r"(?:\w?\s?FIRST\w?\s?NAME)\s*([\w\s]+?)\s*(?:MIDDLE\w?\s?NAME\w?\s?|$)", fixed_data, re.I)
        middle_name_match = re.search(r"(?:\w?\s?MIDDLE\w?\s?NAME)\s*([\w\s]+?)\s*(?:REGISTRATION\w?\s?|$)", fixed_data, re.I)

        # Clean extracted text like in Unified Multi-Purpose ID/SSS ID
        def clean_ocr_text(text):
            if not text:
                return ""
            text = re.sub(r'[^A-Z\s-]', '', text.strip())  # Remove non-alphabetic chars
            text = re.sub(r'\b[A-Z]\b', '', text)  # Remove stray single-letter words
            return re.sub(r'\s+', ' ', text).strip()  # Normalize spaces

        last_name = clean_ocr_text(last_name_match.group(1)) if last_name_match else ""
        given_name = clean_ocr_text(given_name_match.group(1)) if given_name_match else ""
        middle_name = clean_ocr_text(middle_name_match.group(1)) if middle_name_match else ""

        uncleaned_name = f"{given_name} {middle_name} {last_name}".strip()

        # Apply unwanted words removal (same as in Unified Multi-Purpose ID/SSS ID)
        extracted_name = remove_unwanted_words(uncleaned_name, unwanted_words)

        return extracted_name if extracted_name else "Name not found"

    elif id_type == "Unified Multi-Purpose ID/SSS ID":
        # Step 1: Fix OCR Issues
        fixed_data = normalize_ocr_spaces(data)
        
        # Enhanced regex patterns with strict boundaries
        # Updated regex patterns with flexible boundaries
        last_name_regex = r"""
            \b(?:SURNAME|SORNAME)\b\s*  # Handle OCR errors
            ([A-Z]+(?:\s[A-Z]+)*)  # Capture last name
            (?=\s*(?:GIVEN\s*NAME|GIVENNAME))  # Ensure "GIVEN NAME" follows
            """

        given_name_regex = r"""
            \b(?:GIVEN\s*NAME|GIVENNAME)\b\s*  # Handle OCR errors
            ([A-Z]+(?:\s[A-Z]+)*)  # Capture given name
            (?=\s*(?:MIDDLE\s*NAME|MIDDLENAME|MIDOLE\s*NAME|MIDDLE[\-\.\,]NAME))  # Ensure "MIDDLE NAME" follows
        """

        middle_name_regex = r"""
            \b(?:MIDDLE\s*NAME|MIDDLENAME|MIDOLE\s*NAME|MIDDLE[,\.\-]NAME)\b\s*  # Handle OCR errors
            ([A-Z]+(?:[\s\-][A-Z]+)*)  # Capture middle name
            (?=\s*(?:SEX|ADORESS|ADDRESS|\n|$))  # Ensure "SEX" or end of line follows
        """

        # Execute regex with flags (Fixed argument issue)
        last_name_match = re.search(last_name_regex, fixed_data, re.X | re.I)
        given_name_match = re.search(given_name_regex, fixed_data, re.X | re.I)
        middle_name_match = re.search(middle_name_regex, fixed_data, re.X | re.I)

        def clean_ocr_text(text):
            if not text:
                return ""
            text = re.sub(r'[^A-Z\s-]', '', text.strip())  # Remove non-alphabetic chars
            text = re.sub(r'\b[A-Z]\b', '', text)  # Remove stray single-letter words (like "K")
            return re.sub(r'\s+', ' ', text).strip()  # Normalize spaces

        last_name = clean_ocr_text(last_name_match.group(1)) if last_name_match else ""
        given_name = clean_ocr_text(given_name_match.group(1)) if given_name_match else ""
        middle_name = clean_ocr_text(middle_name_match.group(1)) if middle_name_match else ""

        uncleaned_name = f"{given_name} {middle_name} {last_name}".strip()
        
        # Remove unwanted words from extracted name
        extracted_name = remove_unwanted_words(uncleaned_name, unwanted_words)
        
        return extracted_name if extracted_name else "Name not found"
    
    elif id_type == "PhilHealth ID":
        name_match = re.search(
            r"(?:\d{2}-\d{8}-\d{1})\s*([\w\s,]+?)(?=\s*(?:\w?\s?JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|$))",
            data
        )

        if name_match:
            extracted_name = name_match.group(1).strip()

            # Check for comma (indicating last name before first name) and reorder if needed
            if ',' in extracted_name or '.' in extracted_name:
                parts = re.split(r'[,\.]', extracted_name)
                reordered_name = f"{parts[1].strip()} {parts[0].strip()}"
                cleaned_name = reordered_name
            else:
                cleaned_name = extracted_name  # No comma, use as is

            # Step 1: Clean OCR text (Same as in Unified Multi-Purpose ID/SSS ID)
            def clean_ocr_text(text):
                if not text:
                    return ""
                text = re.sub(r'[^A-Z\s-]', '', text.strip())  # Remove non-alphabetic characters
                text = re.sub(r'\b[A-Z]\b', '', text)  # Remove stray single-letter words
                return re.sub(r'\s+', ' ', text).strip()  # Normalize spaces

            cleaned_name = clean_ocr_text(cleaned_name)

            # Step 2: Remove unwanted words
            extracted_name = remove_unwanted_words(cleaned_name, unwanted_words)

        return extracted_name if extracted_name else "Name not found"
    
    return "Name not found"

def process_image_with_ocr(image_path):
    """Process an image with OCR and extract relevant information."""
    # Process the image with OCR
    result = ocr.ocr(image_path, cls=True)
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

    return extracted_name, id_type, registration_number

# Initialize PaddleOCR model
ocr = PaddleOCR(use_angle_cls=True, lang='en')