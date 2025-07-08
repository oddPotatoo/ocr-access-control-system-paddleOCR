# OCR-Based Access Control System Application

![Banner Image](assets/ocr-logo-land.png)

## 📌 Description

The proposed OCR-Based Access Control System for Visitor Vehicle Entry in Gated Areas integrates these technologies to automate visitor verification through ID scanning. The system extracts essential data from valid IDs via OCR, and generates a unique QR code as a temporary access pass. Utilizing open-source and cost-efficient hardware, including a Raspberry Pi 4, cameras, thermal printer, and LCD display, the system provides a scalable, secure, and user-friendly solution. Its implementation is expected to reduce processing times, minimize human error, and improve both traffic flow and security in gated communities.

Developed using Python, PaddleOCR, PostgreSQL, and Firebase, the system provides efficient method to automate visitor entries in private subdivisions, offices, and other gated communities who regulates visitors by ID presentation.

---

## 🖼️ Entrance UI
  <div align="center">
    <img src="assets/Entrance-1.png" alt="UI Preview" width="600"/>
    <img src="assets/Entrance-2.png" alt="UI Preview" width="600"/>
  </div>

## 🖼️ Exit UI
  <div align="center">
    <img src="assets/Exit-1.png" alt="UI Preview" width="600"/>
    <img src="assets/Exit-2.png" alt="UI Preview" width="600"/>
  </div>
  
## 🖼️ OCR-Based Access Control System

| Sample Prototype - Front | Sample Prototype - Back |
|--------------|--------------|
| ![Screenshot 1](assets/sample-prototype-1.png) | ![Screenshot 2](assets/sample-prototype-2.png) |

## 🖼️ System Architecture
  <div align="center">
    <img src="assets/Exit-1.png" alt="UI Preview" width="600"/>
  </div>
The web-based app monitoring is not included in this repository. You may develop your own web-based app by using the firebase real-time database for data synchronization.


---

## ✨ Features

- ✅ Real-time data synchronization using Firebase
- ⏱️ Faster and automated visitor entrance and exit for gated communities
- 📊 Extract relevant information for valid IDs using PaddleOCR

---

## 🚀 How to Use / Install (Optional)

```bash
# Clone the repository
git clone https://github.com/yourusername/your-repo-name.git

# Navigate to project directory
cd your-repo-name

# Install dependencies
npm install

# Run the app
npm start

