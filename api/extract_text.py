from http.server import BaseHTTPRequestHandler
import json
import PyPDF2
import io
import base64

class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            # Read body
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body)

            if "file" not in data:
                self.send_error(400, "Missing 'file' in JSON")
                return

            # Decode base64 → bytes
            pdf_bytes = base64.b64decode(data["file"])

            # Extract text
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            all_text = ""
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    all_text += t + "\n"

            # Response OK
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"text": all_text}).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
