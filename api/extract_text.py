from http.server import BaseHTTPRequestHandler
import json
import base64
import io
import PyPDF2

class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            # Read JSON body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())

            if "file" not in data:
                self.send_error(400, "Missing base64 file")
                return

            # Decode base64 → PDF bytes
            pdf_bytes = base64.b64decode(data["file"])

            # Read PDF and extract text
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            all_text = ""
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"

            # Success response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"text": all_text}).encode())

        except Exception as e:
            # Error response
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
