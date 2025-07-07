import sys
import cv2
import firebase_admin
from firebase_admin import credentials, db
from pyzbar.pyzbar import decode
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget
from PyQt5.QtGui import QImage, QPixmap, QIcon
from PyQt5.QtCore import QTimer, Qt, QSize
import os
import threading

# Firebase initialization
script_dir = os.path.dirname(os.path.abspath(__file__))
cred_path = os.path.join(script_dir, "ocr-access-control-46a21-firebase-adminsdk-fbsvc-a648214418.json")

# Initialize Firebase
try:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://ocr-access-control-46a21-default-rtdb.asia-southeast1.firebasedatabase.app/'  # Replace with your actual database URL
    })
    print("Firebase initialized successfully")
except FileNotFoundError:
    print(f"Error: Firebase credentials file not found at {cred_path}")
    sys.exit(1)
except Exception as e:
    print(f"Error initializing Firebase: {e}")
    sys.exit(1)

def record_exit(qr_code):
    """Find the entry with the scanned QR and record exit time in Firebase Realtime Database."""
    try:
        print(f"Searching for QR code: {qr_code}")
        
        # Get reference to the NonResidentLogs in Realtime Database
        ref = db.reference('NonResidentLogs')
        
        # Query for the QR code
        query_result = ref.order_by_child('qr_code').equal_to(qr_code).get()
        
        print(f"Query result: {query_result}")
        
        if not query_result:
            # Print all QR codes for debugging
            all_logs = ref.get()
            print("Existing QR codes in database:")
            if all_logs:
                for key, value in all_logs.items():
                    print(f"- {value.get('qr_code')}")
            
            return False, "No matching entry found for this QR Code."
        
        # Get the first matching entry (there should only be one)
        entry_key = next(iter(query_result.keys()))
        entry_data = query_result[entry_key]
        
        print(f"Found document: {entry_data}")
        
        if entry_data.get('exit_time'):
            return False, "QR Code is already used"
        
        # Update exit_time in Firebase
        update_time = datetime.now().isoformat()
        ref.child(entry_key).update({'exit_time': update_time})
        
        print(f"Successfully updated exit time for QR: {qr_code}")
        return True, "Scan Successful"
    
    except Exception as e:
        print(f"Error recording exit: {e}")
        return False, "An error occurred while processing the QR Code."

class QRScannerApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # Set window properties
        self.setWindowTitle("BF Homes Exit Scanning")
        self.setGeometry(100, 100, 1152, 648)
        self.setWindowIcon(QIcon("assets/bfexiticon.png"))
        
        # Central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Layout
        self.layout = QVBoxLayout(self.central_widget)

        # Load the logo from the assets folder
        self.logo_path = "assets/logo.png"
        if os.path.exists(self.logo_path):
            self.logo_label = QLabel(self)
            self.logo_pixmap = QPixmap(self.logo_path).scaled(300, 300, Qt.KeepAspectRatio)
            self.logo_label.setPixmap(self.logo_pixmap)
            self.logo_label.setAlignment(Qt.AlignCenter)
            self.layout.addWidget(self.logo_label)
        else:
            print("Logo not found. Ensure 'logo.png' is in the 'assets' folder.")
            self.logo_label = QLabel("QR Code Scanner", self)
            self.logo_label.setAlignment(Qt.AlignCenter)
            self.logo_label.setStyleSheet("font-size: 20px;")
            self.layout.addWidget(self.logo_label)

        # Create a label for the webcam feed
        self.video_label = QLabel(self)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.video_label)

        # Create a status label
        self.status_label = QLabel("BF FEDERATION OF HOMEOWNERS ASSOCIATION, INC", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 18px;")
        self.layout.addWidget(self.status_label)

        # Create a message label for displaying scan results
        self.message_label = QLabel(self)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("font-size: 24px; color: white; background-color: rgba(0, 0, 0, 150); padding: 20px;")
        self.message_label.hide()
        self.layout.addWidget(self.message_label)

        # Create a cooldown label for displaying the cooldown timer
        self.cooldown_label = QLabel(self)
        self.cooldown_label.setAlignment(Qt.AlignCenter)
        self.cooldown_label.setStyleSheet("font-size: 24px; color: red; background-color: rgba(0, 0, 0, 150); padding: 20px;")
        self.cooldown_label.hide()
        self.layout.addWidget(self.cooldown_label)

        # Create buttons
        self.start_button = QPushButton("Start Scanning", self)
        self.start_button.clicked.connect(self.start_scanning)
        self.layout.addWidget(self.start_button)

        self.exit_button = QPushButton("Exit", self)
        self.exit_button.clicked.connect(self.close_application)
        self.layout.addWidget(self.exit_button)

        # Load the back button image
        self.back_button_path = "assets/back-button.png"
        if os.path.exists(self.back_button_path):
            self.back_button = QPushButton(self)
            self.back_button.setIcon(QIcon(self.back_button_path))
            icon_size = QSize(24, 24)
            self.back_button.setIconSize(icon_size)
            self.back_button.setFixedSize(icon_size.width() + 10, icon_size.height() + 10)
            self.back_button.setStyleSheet("background-color: transparent; border: none;")
            self.back_button.clicked.connect(self.stop_scanning)
            self.back_button.hide()
        else:
            print("Back button image not found. Ensure 'back-button.png' is in the 'assets' folder.")
            self.back_button = QPushButton("Back", self)
            self.back_button.clicked.connect(self.stop_scanning)
            self.back_button.hide()

        # Webcam capture
        self.cap = None
        self.scanning = False

        # Timer for updating the webcam feed
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

        # Cooldown timer
        self.cooldown_timer = QTimer()
        self.cooldown_timer.timeout.connect(self.update_cooldown)
        self.cooldown_active = False
        self.cooldown_seconds = 3

    def start_scanning(self):
        """Start the QR code scanning process."""
        if not self.scanning:
            self.scanning = True
            self.status_label.setText("Scanning...")
            self.logo_label.hide()
            self.start_button.hide()
            self.exit_button.hide()
            self.status_label.hide()
            self.back_button.show()
            self.back_button.move(10, 10)
            self.cap = cv2.VideoCapture(3)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 854)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.timer.start(10)

    def stop_scanning(self):
        """Stop the QR code scanning process and close the webcam feed."""
        self.scanning = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.timer.stop()
        self.video_label.clear()
        self.back_button.hide()
        self.logo_label.show()
        self.start_button.show()
        self.exit_button.show()
        self.status_label.show()
        self.status_label.setText("Scanning stopped.")
    
    def update_frame(self):
        """Update the webcam feed in the GUI."""
        if self.scanning:
            ret, frame = self.cap.read()
            if ret:
                rect_width = 400
                rect_height = 400
                rect_x = (frame.shape[1] - rect_width) // 2
                rect_y = (frame.shape[0] - rect_height) // 2
                cv2.rectangle(frame, (rect_x, rect_y), (rect_x + rect_width, rect_y + rect_height), (0, 255, 0), 2)

                if not self.cooldown_active:
                    decoded_objects = decode(frame)
                    for obj in decoded_objects:
                        qr_data = obj.data.decode("utf-8")
                        print(f"Scanned QR Code: {qr_data}")

                        success, message = record_exit(qr_data)
                        
                         # Custom message handling
                        if success:
                            display_text = "🎉 Thank you for visiting BF Homes!\n\nSafe travels and come again!"
                            style = "color: #2ECC71; background-color: rgba(46, 204, 113, 0.2);"
                        else:
                            display_text = f"⚠️ {message}"
                            style = "color: #E74C3C; background-color: rgba(231, 76, 60, 0.2);"
                        
                        self.message_label.setStyleSheet(f"""
                            font-size: 28px; 
                            font-weight: bold;
                            padding: 25px;
                            border-radius: 10px;
                            {style}
                        """)
                        self.message_label.setText(display_text)
                        self.message_label.show()

                        QTimer.singleShot(3000, self.message_label.hide)
                        self.start_cooldown()
                        break

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                self.video_label.setPixmap(QPixmap.fromImage(qt_image))

    def start_cooldown(self):
        """Start a 3-second cooldown before scanning another QR code."""
        self.cooldown_active = True
        self.cooldown_seconds = 3
        self.cooldown_label.setText(f"Cooldown: {self.cooldown_seconds} seconds")
        self.cooldown_label.show()
        self.cooldown_timer.start(1000)

    def update_cooldown(self):
        """Update the cooldown timer and allow scanning again when it reaches 0."""
        if self.cooldown_seconds > 0:
            self.cooldown_seconds -= 1
            self.cooldown_label.setText(f"Cooldown: {self.cooldown_seconds} seconds")
        else:
            self.cooldown_timer.stop()
            self.cooldown_active = False
            self.cooldown_label.hide()

    def close_application(self):
        """Completely close the application"""
        if self.cap:
            self.cap.release()
        self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QRScannerApp()
    window.show()
    sys.exit(app.exec_())