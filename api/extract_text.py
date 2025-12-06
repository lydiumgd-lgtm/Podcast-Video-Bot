from http.server import BaseHTTPRequestHandler
import json
import base64
import io
import PyPDF2
import sys

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Set longer timeout header
            self.timeout = 25
            
            # Read JSON body with size limit check
            content_length = int(self.headers.get("Content-Length", 0))
            
            # Vercel limit is 4.5MB, but let's be safe
            MAX_BODY_SIZE = 5 * 1024 * 1024  # 5MB
            if content_length > MAX_BODY_SIZE:
                self.send_error_response(413, "Request body too large. Max 5MB.")
                return
            
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Validate input
            if "file" not in data:
                self.send_error_response(400, "Missing 'file' field in request")
                return
            
            if not isinstance(data["file"], str):
                self.send_error_response(400, "File must be base64 encoded string")
                return
            
            # Decode base64 → PDF bytes with error handling
            try:
                pdf_bytes = base64.b64decode(data["file"])
            except Exception as e:
                self.send_error_response(400, f"Invalid base64 encoding: {str(e)}")
                return
            
            # Validate it's actually a PDF
            if not pdf_bytes.startswith(b'%PDF'):
                self.send_error_response(400, "File is not a valid PDF")
                return
            
            # Read PDF with robust error handling
            try:
                pdf_file = io.BytesIO(pdf_bytes)
                reader = PyPDF2.PdfReader(pdf_file)
                
                # Check if PDF is encrypted
                if reader.is_encrypted:
                    self.send_error_response(400, "PDF is password-protected. Please upload an unencrypted PDF.")
                    return
                
                total_pages = len(reader.pages)
                
                # Warn if too many pages (might timeout)
                if total_pages > 100:
                    self.send_error_response(400, f"PDF has {total_pages} pages. Maximum 100 pages supported. Please split your PDF.")
                    return
                
                # Extract text page by page
                all_text = ""
                extracted_pages = 0
                
                for page_num, page in enumerate(reader.pages):
                    try:
                        text = page.extract_text()
                        if text and text.strip():
                            all_text += text + "\n\n"
                            extracted_pages += 1
                    except Exception as page_error:
                        # Log but continue with other pages
                        print(f"Warning: Could not extract text from page {page_num + 1}: {str(page_error)}", file=sys.stderr)
                        continue
                
                # Check if we got any text
                if not all_text.strip():
                    self.send_error_response(400, "No text could be extracted. PDF might contain only images or be corrupted.")
                    return
                
                # Success response
                response_data = {
                    "text": all_text.strip(),
                    "pages": total_pages,
                    "extracted_pages": extracted_pages,
                    "characters": len(all_text.strip())
                }
                
                self.send_success_response(response_data)
                
            except PyPDF2.errors.PdfReadError as e:
                self.send_error_response(400, f"Invalid or corrupted PDF: {str(e)}")
                return
            except Exception as e:
                self.send_error_response(500, f"Error reading PDF: {str(e)}")
                return
                
        except json.JSONDecodeError as e:
            self.send_error_response(400, f"Invalid JSON: {str(e)}")
        except Exception as e:
            # Catch-all for unexpected errors
            self.send_error_response(500, f"Unexpected error: {str(e)}")
    
    def send_success_response(self, data):
        """Send successful JSON response"""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def send_error_response(self, status_code, error_message):
        """Send error JSON response"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": error_message}).encode('utf-8'))
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()