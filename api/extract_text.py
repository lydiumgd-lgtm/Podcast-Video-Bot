from PyPDF2 import PdfReader
import json
import base64
from io import BytesIO

def handler(request):
    try:
        body = request.json()
        pdf_base64 = body.get("file")

        if not pdf_base64:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "No file uploaded"})
            }

        # Decode base64 → bytes
        pdf_bytes = base64.b64decode(pdf_base64)

        # Read PDF
        reader = PdfReader(BytesIO(pdf_bytes))

        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"

        return {
            "statusCode": 200,
            "body": json.dumps({"text": text})
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
