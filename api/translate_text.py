from http.server import BaseHTTPRequestHandler
import json
import os

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Read JSON body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Validate input
            if "parts" not in data:
                self.send_error_response(400, "Missing 'parts' field in request")
                return
            
            parts = data["parts"]
            
            if not isinstance(parts, list):
                self.send_error_response(400, "'parts' must be an array")
                return
            
            if len(parts) == 0:
                self.send_error_response(400, "Parts array cannot be empty")
                return
            
            # Translate all parts
            translated_parts = []
            
            for i, part in enumerate(parts):
                if not part or not part.strip():
                    translated_parts.append("")
                    continue
                
                try:
                    translated = self.translate_text(part)
                    translated_parts.append(translated)
                except Exception as e:
                    # If one part fails, return partial results with error
                    self.send_error_response(500, f"Translation failed at part {i+1}: {str(e)}")
                    return
            
            # Calculate statistics
            original_chars = sum(len(part) for part in parts)
            translated_chars = sum(len(part) for part in translated_parts)
            
            response_data = {
                "translated_parts": translated_parts,
                "part_count": len(translated_parts),
                "original_chars": original_chars,
                "translated_chars": translated_chars
            }
            
            self.send_success_response(response_data)
            
        except json.JSONDecodeError as e:
            self.send_error_response(400, f"Invalid JSON: {str(e)}")
        except Exception as e:
            self.send_error_response(500, f"Unexpected error: {str(e)}")
    
    def translate_text(self, text):
        """
        Translate English text to Filipino (Tagalog).
        Uses HuggingFace Inference API (free tier).
        """
        import requests
        
        # HuggingFace Inference API endpoint (free, no API key needed for public models)
        API_URL = "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-en-tl"
        
        headers = {}
        
        # If you want to avoid rate limits, you can add a token (optional, still free)
        # Get token from: https://huggingface.co/settings/tokens
        # Uncomment below and set environment variable if needed:
        # hf_token = os.environ.get("HUGGINGFACE_TOKEN")
        # if hf_token:
        #     headers["Authorization"] = f"Bearer {hf_token}"
        
        payload = {
            "inputs": text,
            "options": {
                "wait_for_model": True  # Wait if model is loading
            }
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            # Handle different response formats
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], dict) and "translation_text" in result[0]:
                    return result[0]["translation_text"]
                elif isinstance(result[0], str):
                    return result[0]
            
            # If we get here, unexpected format
            raise Exception(f"Unexpected API response format: {result}")
            
        except requests.exceptions.Timeout:
            raise Exception("Translation API timeout. Please try again.")
        except requests.exceptions.RequestException as e:
            # Check if it's a rate limit error
            if hasattr(e.response, 'status_code') and e.response.status_code == 429:
                raise Exception("Translation API rate limit reached. Please wait a moment and try again.")
            raise Exception(f"Translation API error: {str(e)}")
    
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