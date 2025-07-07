import os
import tempfile
import win32print
import win32ui
from PIL import Image, ImageWin, ImageDraw, ImageFont

class WindowsPrinter:
    def __init__(self, printer_name=None):
        """
        Initialize with specific printer or default printer
        """
        self.printer_name = printer_name or win32print.GetDefaultPrinter()
        
    def print_receipt(self, qr_path, name, id_type, id_num):
        """Print using Windows GDI with proper resource handling"""
        temp_file_path = None
        try:
            # Create temporary file (manually managed)
            temp_file_path = tempfile.mktemp(suffix='.bmp')
            
            # Generate receipt image
            self._create_receipt_image(temp_file_path, qr_path, name, id_type, id_num)
            
            # Print the image
            self._print_image(temp_file_path)
            
            return True
        except Exception as e:
            print(f"Print error: {e}")
            return False
        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    print(f"Warning: Could not delete temp file: {e}")

    def _create_receipt_image(self, output_path, qr_path, name, id_type, id_num):
        """Generate receipt as bitmap image"""
        # Constants for 80mm paper (300dpi)
        PAPER_WIDTH = 800  # pixels (~80mm at 300dpi)
        PAPER_HEIGHT = 800  # pixels
        
        # Create blank image
        img = Image.new("RGB", (PAPER_WIDTH, PAPER_HEIGHT), "white")
        draw = ImageDraw.Draw(img)
        
        # Load fonts (scale for receipt)
        try:
            font_large = ImageFont.truetype("arial.ttf", 40)
            font_medium = ImageFont.truetype("arial.ttf", 30)
            font_small = ImageFont.truetype("arial.ttf", 24)
        except:
            # Fallback to default fonts
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Draw header
        draw.text((PAPER_WIDTH//2, 50), "BF FEDERATION HOMEOWNERS ASSOCIATION, INC.", 
                 font=font_small, fill="black", anchor="mm")
        draw.text((PAPER_WIDTH//2, 100), "VISITOR PASS", 
                 font=font_small, fill="black", anchor="mm")
        draw.line([(50, 150), (PAPER_WIDTH-50, 150)], fill="black", width=2)
        
        # Draw visitor info
        y_pos = 180
        draw.text((50, y_pos), f"NAME: {name}", font=font_small, fill="black")
        y_pos += 40
        draw.text((50, y_pos), f"ID TYPE: {id_type}", font=font_small, fill="black")
        y_pos += 40
        draw.text((50, y_pos), f"ID NO: {id_num}", font=font_small, fill="black")
        y_pos += 60
        draw.line([(50, y_pos), (PAPER_WIDTH-50, y_pos)], fill="black", width=2)
        
        # Draw QR code
        if os.path.exists(qr_path):
            try:
                qr_img = Image.open(qr_path).resize((300, 300))
                img.paste(qr_img, (PAPER_WIDTH//2 - 150, y_pos + 20))
                draw.text((PAPER_WIDTH//2, y_pos + 340), 
                         "EXIT ONLY AT LOPEZ GATE", 
                         font=font_large, fill="black", anchor="mm")
            except Exception as e:
                print(f"QR error: {e}")
        
        # Draw footer
        y_pos = PAPER_HEIGHT - 100
        draw.text((PAPER_WIDTH//2, y_pos), 
                 "Thank you for visiting!", 
                 font=font_small, fill="black", anchor="mm")
        
        # Save image
        img.save(output_path, "BMP")

    def _print_image(self, image_path):
        """Send image to Windows printer with proper resource handling"""
        hdc = None
        try:
            # Open the image first to ensure it exists
            bmp = Image.open(image_path)
            width, height = bmp.size
            
            # Create device context
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(self.printer_name)
            
            # Start document
            hdc.StartDoc("Visitor Receipt")
            hdc.StartPage()
            
            # Print the image
            dib = ImageWin.Dib(bmp)
            dib.draw(hdc.GetHandleOutput(), (0, 0, width, height))
            
            # End document
            hdc.EndPage()
            hdc.EndDoc()
            
        finally:
            # Clean up resources
            if hdc:
                try:
                    hdc.DeleteDC()
                except:
                    pass
            if 'bmp' in locals():
                try:
                    bmp.close()
                except:
                    pass

# Example usage:
if __name__ == "__main__":
    printer = WindowsPrinter()  # Uses default printer
    success = printer.print_receipt(
        "qrcode.png",
        "JUAN DELA CRUZ",
        "DRIVER'S LICENSE",
        "DL-12345678"
    )
    print("Print successful!" if success else "Print failed")