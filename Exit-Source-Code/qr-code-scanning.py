import sys
import cv2
import psycopg2
from pyzbar.pyzbar import decode
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget
from PyQt5.QtGui import QImage, QPixmap, QIcon
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtCore import QSize
import os

# PostgreSQL connection setup
DB_PARAMS = {
    "dbname": "non_resident_logs",
    "user": "postgres",
    "password": "meowthiebowingski",
    "host": "localhost",
    "port": "5432"
}

def connect_db():
    """Establish connection to PostgreSQL."""
    return psycopg2.connect(**DB_PARAMS)

def record_exit(qr_code):
    """Find the entry with the scanned QR and record exit time."""
    conn = connect_db()
    cursor = conn.cursor()

    # Find the entry record associated with this QR
    cursor.execute('SELECT id, exit_time FROM "NonResidentLogs" WHERE qr_code = %s', (qr_code,))
    entry = cursor.fetchone()

    if entry:
        entry_id, exit_time = entry
        if exit_time is not None:
            # QR code is already used
            cursor.close()
            conn.close()
            return False, "QR Code is already used"
        else:
            # Update exit_time for this entry
            cursor.execute("""
                UPDATE "NonResidentLogs"
                SET exit_time = %s
                WHERE id = %s;
            """, (datetime.now(), entry_id))
            conn.commit()
            cursor.close()
            conn.close()
            return True, "Scan Successful"
    else:
        cursor.close()
        conn.close()
        return False, "No matching entry found for this QR Code."

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
        self.message_label.setStyleSheet("font-size: 24px; font-weight: bold; color: white; background-color: rgba(0, 0, 0, 150);  border-radius: 10px; padding: 25px;")
        self.message_label.setWordWrap(True)
        self.message_label.hide()  # Initially hidden
        self.layout.addWidget(self.message_label)

        # Create a cooldown label for displaying the cooldown timer
        self.cooldown_label = QLabel(self)
        self.cooldown_label.setAlignment(Qt.AlignCenter)
        self.cooldown_label.setStyleSheet("font-size: 24px; color: red; background-color: rgba(0, 0, 0, 150); padding: 20px;")
        self.cooldown_label.hide()  # Initially hidden
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

            # Set the desired icon size
            icon_size = QSize(24, 24)  # Adjust width and height as needed
            self.back_button.setIconSize(icon_size)

            # Set the button size to match or be slightly larger than the icon
            self.back_button.setFixedSize(icon_size.width() + 10, icon_size.height() + 10)

            self.back_button.setStyleSheet("background-color: transparent; border: none;")
            self.back_button.clicked.connect(self.stop_scanning)
            self.back_button.hide()  # Initially hidden

        else:
            print("Back button image not found. Ensure 'back-button.png' is in the 'assets' folder.")
            self.back_button = QPushButton("Back", self)
            self.back_button.clicked.connect(self.stop_scanning)
            self.back_button.hide()  # Initially hidden

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
        self.cooldown_seconds = 3  # 3-second cooldown

    def start_scanning(self):
        """Start the QR code scanning process."""
        if not self.scanning:
            self.scanning = True
            self.status_label.setText("Scanning...")

            # Hide the logo, buttons, and status label
            self.logo_label.hide()
            self.start_button.hide()
            self.exit_button.hide()
            self.status_label.hide()

            # Show the back button
            self.back_button.show()
            self.back_button.move(10, 10)  # Position the back button in the top-left corner

            # Open the webcam
            self.cap = cv2.VideoCapture(3)  # Open webcam
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 854)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            # Start the timer to update the webcam feed
            self.timer.start(10)  # Update every 10ms

    def stop_scanning(self):
        """Stop the QR code scanning process and close the webcam feed."""
        self.scanning = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None  # Ensure the capture object is fully released

        # Stop the timer
        self.timer.stop()

        # Clear the video feed
        self.video_label.clear()

        # Hide the back button
        self.back_button.hide()

        # Show the logo, buttons, and status label again
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
                # Draw a rectangle to guide the user where to place the QR code
                rect_width = 400
                rect_height = 400
                rect_x = (frame.shape[1] - rect_width) // 2
                rect_y = (frame.shape[0] - rect_height) // 2
                cv2.rectangle(frame, (rect_x, rect_y), (rect_x + rect_width, rect_y + rect_height), (0, 255, 0), 2)

                # Only process QR codes if not in cooldown
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

                # Convert the frame to RGB and display it in the GUI
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                self.video_label.setPixmap(QPixmap.fromImage(qt_image))

    def start_cooldown(self):
        """Start a 3-second cooldown before scanning another QR code."""
        self.cooldown_active = True
        self.cooldown_seconds = 3  # Reset cooldown seconds
        self.cooldown_label.setText(f"Cooldown: {self.cooldown_seconds} seconds")
        self.cooldown_label.show()
        self.cooldown_timer.start(1000)  # Update every 1 second

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

# Run the application
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QRScannerApp()
    window.show()
    sys.exit(app.exec_())