from http.server import BaseHTTPRequestHandler
import json
import PyPDF2
import io

class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            # Read raw bytes
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)

            # Extract file from multipart form
            import cgi
            env = {'REQUEST_METHOD':'POST'}
            fs = cgi.FieldStorage(
                fp=io.BytesIO(body),
                headers=self.headers,
                environ=env
            )

            if 'file' not in fs:
                self.send_error(400, "No file uploaded")
                return

            file_item = fs['file']
            pdf_bytes = file_item.file.read()

            # Read PDF
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            all_text = ""
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"

            # Response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"text": all_text}).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
