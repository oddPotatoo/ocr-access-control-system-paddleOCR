import os
import sys
import cv2
import uuid
import numpy as np
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QStackedWidget
from PyQt5.QtGui import QPixmap, QImage, QFont
from PyQt5.QtCore import QTimer, Qt
from ocr_utils import insert_vehicle_entry, detect_id_type, extract_registration_number, extract_name, generate_qr_code, ocr, process_image_with_ocr
import firebase_admin
from firebase_admin import credentials
import firebase_admin
from firebase_admin import credentials, db
from receipt_printer import WindowsPrinter

# Initialize Firebase with proper path handling
def initialize_firebase():
    try:
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Construct the full path to the credentials file
        cred_path = os.path.join(script_dir, "ocr-access-control-46a21-firebase-adminsdk-fbsvc-a648214418.json")
        
        if not os.path.exists(cred_path):
            print(f"Error: Firebase credentials file not found at {cred_path}")
            print("Please ensure the JSON file is in the same directory as this script")
            return False
            
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://ocr-access-control-46a21-default-rtdb.asia-southeast1.firebasedatabase.app/'
        })
        print("Firebase initialized successfully")
        return True
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        return False

# Initialize Firebase at application start
if not initialize_firebase():
    print("Failed to initialize Firebase. Exiting...")
    sys.exit(1)

class HomeScreen(QMainWindow):
    def __init__(self, stacked_widget):
        super().__init__()
        self.stacked_widget = stacked_widget
        self.initUI()

    def initUI(self):
        self.setWindowTitle("ID Scanner - Home")
        self.setFixedSize(1152, 648)  # Fixed screen size

        # Load logo
        logo = QLabel(self)
        pixmap = QPixmap("assets/logo.png")
        logo.setPixmap(pixmap.scaled(400, 400, Qt.KeepAspectRatio))
        logo.setAlignment(Qt.AlignCenter)

        # Add text "BF FEDERATION OF HOMEOWNERS ASSOCIATION, INC"
        title_label = QLabel("BF FEDERATION OF HOMEOWNERS ASSOCIATION, INC", self)
        title_label.setFont(QFont("Arial", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)

        # Start button
        start_button = QPushButton("Start ID Scanning", self)
        start_button.clicked.connect(self.go_to_scan_screen)
        start_button.setFixedSize(200, 50)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(logo)
        layout.addWidget(title_label)
        layout.addWidget(start_button, alignment=Qt.AlignCenter)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def go_to_scan_screen(self):
        self.stacked_widget.setCurrentIndex(1)
        self.stacked_widget.currentWidget().start_webcam()  # Start webcam when switching to ScanScreen

class ScanScreen(QMainWindow):
    def __init__(self, stacked_widget):
        super().__init__()
        self.stacked_widget = stacked_widget
        self.cap = None  # Webcam capture object
        self.timer = QTimer()  # Timer for updating the webcam feed
        self.id_detected = False  # Flag to track ID detection
        self.countdown_timer = QTimer()  # Timer for countdown
        self.cooldown_timer = QTimer()  # Timer for cooldown after capturing an ID
        self.countdown_seconds = 5  # 5-second countdown
        self.cooldown_seconds = 7  # 7-second cooldown
        self.initUI()

    def initUI(self):
        self.setWindowTitle("ID Scanner - Live Feed")
        self.setFixedSize(1152, 648)  # Fixed screen size

        # Webcam feed label
        self.video_label = QLabel(self)
        self.video_label.setAlignment(Qt.AlignCenter)

        # Countdown label
        self.countdown_label = QLabel("Countdown: 5", self)
        self.countdown_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet("color: red;")  # Set text color to red

        # Capture button
        capture_button = QPushButton("Capture Image", self)
        capture_button.clicked.connect(self.capture_image)
        capture_button.setFixedSize(200, 50)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.video_label)
        layout.addWidget(self.countdown_label)  # Add countdown label to the layout
        layout.addWidget(capture_button, alignment=Qt.AlignCenter)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def start_webcam(self):
        """Start the webcam feed."""
        if self.cap is None:
            self.cap = cv2.VideoCapture(3)  # Initialize webcam
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.timer.timeout.connect(self.update_frame)
            self.timer.start(20)  # Update every 20ms

    def update_frame(self):
        """Update the webcam feed and perform automatic ID detection."""
        if self.cap is not None:
            ret, frame = self.cap.read()
            if ret:
                # Convert frame to grayscale for ID detection
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Draw guiding lines on the frame
                frame = self.draw_guiding_lines(frame)

                # Perform automatic ID detection (only if not in cooldown)
                if not self.id_detected and not self.cooldown_timer.isActive():
                    self.id_detected = self.detect_id(gray_frame)

                # Display the frame
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                convert_to_Qt_format = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                self.video_label.setPixmap(QPixmap.fromImage(convert_to_Qt_format).scaled(1152, 648, Qt.KeepAspectRatio))

    def draw_guiding_lines(self, frame):
        """Draw guiding lines on the frame to indicate the ID placement area."""
        h, w, _ = frame.shape
        # Draw a rectangle in the center of the frame
        cv2.rectangle(frame, (w // 4, h // 4), (3 * w // 4, 3 * h // 4), (0, 255, 0), 2)
        return frame

    def detect_id(self, gray_frame):
        """
        Detect the presence of an ID in the frame using edge detection.
        Returns True if an ID is detected, otherwise False.
        """
        # Apply edge detection
        edges = cv2.Canny(gray_frame, 100, 200)

        # Count the number of edges (high pixel values)
        edge_count = np.sum(edges > 0)

        # If the edge count is above a threshold, assume an ID is present
        if edge_count > 20000:  # Adjust this threshold as needed
            print("ID detected automatically! Starting countdown...")
            self.start_countdown()  # Start the 5-second countdown
            return True
        return False

    def start_countdown(self):
        """Start a 5-second countdown before capturing the image."""
        # Stop the timer if it's already running
        if self.countdown_timer.isActive():
            self.countdown_timer.stop()

        # Reset the countdown seconds
        self.countdown_seconds = 5

        # Disconnect any existing connections to avoid multiple signals
        try:
            self.countdown_timer.timeout.disconnect()
        except TypeError:
            pass  # No connections to disconnect

        # Connect the timeout signal to the update_countdown method
        self.countdown_timer.timeout.connect(self.update_countdown)

        # Start the timer
        self.countdown_timer.start(1000)  # Update every 1 second

    def update_countdown(self):
        """Update the countdown and capture the image when it reaches 0."""
        if self.countdown_seconds > 0:
            print(f"Countdown: {self.countdown_seconds} seconds")
            self.countdown_label.setText(f"Countdown: {self.countdown_seconds}")  # Update the countdown label
            self.countdown_seconds -= 1
        else:
            self.countdown_timer.stop()
            self.countdown_label.setText("Countdown: 0")  # Set countdown to 0
            self.capture_image()  # Capture the image after countdown

    def capture_image(self):
        """Capture an image and process it."""
        if self.cap is not None:
            ret, frame = self.cap.read()
            if ret:
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                timestamp = uuid.uuid4().hex
                image_path = f"captureIDs/captured_id_{timestamp}.jpg"
                cv2.imwrite(image_path, gray_frame)

                # OCR processing only (no DB insert here)
                extracted_name, id_type, registration_number = process_image_with_ocr(image_path)

                if extracted_name == "Name not found":
                    print("Name not found, restarting countdown...")
                    self.start_countdown()
                    return

                # Generate QR and insert only if name is found
                qr_code_value = str(uuid.uuid4())
                qr_code_path = generate_qr_code(qr_code_value)
                print(f"Generated QR Code: {qr_code_value}")
                print(f"Saved at: {qr_code_path}")

                entry_id = insert_vehicle_entry(extracted_name, id_type, registration_number, qr_code_value)
                print(f"Entry inserted with ID: {entry_id}")

                # Print receipt
                printer = WindowsPrinter()
                if printer.print_receipt(qr_code_path, extracted_name, id_type, registration_number):
                    print("Receipt printed successfully")
                else:
                    print("Failed to print receipt (but data was saved)")

                # Display QR and image
                qr_image = cv2.imread(qr_code_path)
                plt.imshow(cv2.cvtColor(qr_image, cv2.COLOR_BGR2RGB))
                plt.axis('off')
                plt.title(f"QR Code for {extracted_name}")
                plt.show()

                image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
                plt.imshow(image, cmap='gray')
                plt.axis('off')
                plt.title(f"ID Type: {id_type}\nReg. No: {registration_number}\nName:{extracted_name}")
                plt.show()

                self.id_detected = False
                self.start_cooldown()

    def start_cooldown(self):
        """Start a 7-second cooldown after capturing an ID."""
        # Stop the timer if it's already running
        if self.cooldown_timer.isActive():
            self.cooldown_timer.stop()

        # Reset the cooldown seconds
        self.cooldown_seconds = 7

        # Disconnect any existing connections to avoid multiple signals
        try:
            self.cooldown_timer.timeout.disconnect()
        except TypeError:
            pass  # No connections to disconnect

        # Connect the timeout signal to the update_cooldown method
        self.cooldown_timer.timeout.connect(self.update_cooldown)

        # Start the timer
        self.cooldown_timer.start(1000)  # Update every 1 second

    def update_cooldown(self):
        """Update the cooldown and allow ID detection when it reaches 0."""
        if self.cooldown_seconds > 0:
            print(f"Cooldown: {self.cooldown_seconds} seconds")
            self.cooldown_seconds -= 1
        else:
            self.cooldown_timer.stop()
            print("Cooldown finished. Ready to detect another ID.")

    def closeEvent(self, event):
        """Release the webcam when the window is closed."""
        if self.cap is not None:
            self.cap.release()
        event.accept()

class MainApp(QApplication):
    def __init__(self, sys_argv):
        super().__init__(sys_argv)
        self.stacked_widget = QStackedWidget()

        # Create screens
        self.home_screen = HomeScreen(self.stacked_widget)
        self.scan_screen = ScanScreen(self.stacked_widget)

        # Add screens to stacked widget
        self.stacked_widget.addWidget(self.home_screen)
        self.stacked_widget.addWidget(self.scan_screen)

        # Show the home screen
        self.stacked_widget.setFixedSize(1152, 648)  # Fixed screen size
        self.stacked_widget.show()

if __name__ == "__main__":
    app = MainApp(sys.argv)
    sys.exit(app.exec_())