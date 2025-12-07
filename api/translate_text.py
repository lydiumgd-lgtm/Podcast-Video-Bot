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
        Uses multiple fallback methods for reliability.
        """
        import requests
        import sys
        
        # Method 1: Try MyMemory first (simpler, more reliable)
        try:
            print(f"Trying MyMemory translation...", file=sys.stderr)
            return self.translate_with_mymemory(text)
        except Exception as e:
            print(f"MyMemory translation failed: {str(e)}", file=sys.stderr)
        
        # Method 2: Try Facebook's NLLB model
        try:
            print(f"Trying NLLB translation...", file=sys.stderr)
            return self.translate_with_nllb(text)
        except Exception as e:
            print(f"NLLB translation failed: {str(e)}", file=sys.stderr)
        
        # If all methods fail
        raise Exception("All translation methods failed. Please try again later.")
    
    def translate_with_nllb(self, text):
        """
        Use Facebook's NLLB (No Language Left Behind) model via HuggingFace.
        Better for Filipino/Tagalog translation.
        """
        import requests
        import sys
        
        # NLLB-200 model - supports Filipino well
        API_URL = "https://api-inference.huggingface.co/models/facebook/nllb-200-distilled-600M"
        
        headers = {"Content-Type": "application/json"}
        hf_token = os.environ.get("HUGGINGFACE_TOKEN")
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"
        
        payload = {
            "inputs": text,
            "parameters": {
                "src_lang": "eng_Latn",  # English
                "tgt_lang": "tgl_Latn"   # Tagalog (Filipino)
            },
            "options": {
                "wait_for_model": True,
                "use_cache": True
            }
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            
            # Log status for debugging
            print(f"NLLB API Status: {response.status_code}", file=sys.stderr)
            
            # Check if response is JSON
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' not in content_type:
                print(f"Non-JSON response: {response.text[:200]}", file=sys.stderr)
                raise Exception(f"API returned non-JSON response (status {response.status_code})")
            
            response.raise_for_status()
            result = response.json()
            
            # Handle response format
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], dict):
                    return result[0].get("translation_text", result[0].get("generated_text", ""))
                elif isinstance(result[0], str):
                    return result[0]
            elif isinstance(result, dict):
                # Check for error in response
                if "error" in result:
                    raise Exception(f"API error: {result['error']}")
                return result.get("translation_text", result.get("generated_text", ""))
            
            raise Exception(f"Unexpected API response format: {result}")
            
        except requests.exceptions.Timeout:
            raise Exception("Translation timed out. Text may be too long.")
        except requests.exceptions.RequestException as e:
            print(f"Request error: {str(e)}", file=sys.stderr)
            raise Exception(f"Translation API request failed: {str(e)}")
    
    def translate_with_mymemory(self, text):
        """
        Use MyMemory Translation API (free, no auth required).
        Fallback method if HuggingFace fails.
        """
        import requests
        from urllib.parse import quote
        
        # Split text into chunks if too long (MyMemory has 500 char limit per request)
        max_chars = 500
        if len(text) <= max_chars:
            return self._translate_chunk_mymemory(text)
        
        # Split into sentences and translate in chunks
        sentences = text.replace('! ', '!|').replace('? ', '?|').replace('. ', '.|').split('|')
        translated_chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            if current_length + len(sentence) > max_chars and current_chunk:
                # Translate current chunk
                chunk_text = ' '.join(current_chunk)
                translated_chunks.append(self._translate_chunk_mymemory(chunk_text))
                current_chunk = [sentence]
                current_length = len(sentence)
            else:
                current_chunk.append(sentence)
                current_length += len(sentence) + 1
        
        # Translate remaining chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            translated_chunks.append(self._translate_chunk_mymemory(chunk_text))
        
        return ' '.join(translated_chunks)
    
    def _translate_chunk_mymemory(self, text):
        """Helper to translate a single chunk with MyMemory API"""
        import requests
        from urllib.parse import quote
        import sys
        
        # MyMemory free API
        encoded_text = quote(text)
        url = f"https://api.mymemory.translated.net/get?q={encoded_text}&langpair=en|tl"
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            print(f"MyMemory response status: {data.get('responseStatus')}", file=sys.stderr)
            
            if data.get("responseStatus") == 200 or data.get("responseStatus") == "200":
                translated = data.get("responseData", {}).get("translatedText", "")
                if translated:
                    return translated
            
            # If no translation or error
            error_msg = data.get('responseDetails', 'Unknown error')
            print(f"MyMemory error details: {error_msg}", file=sys.stderr)
            raise Exception(f"MyMemory API error: {error_msg}")
            
        except requests.exceptions.RequestException as e:
            print(f"MyMemory request error: {str(e)}", file=sys.stderr)
            raise Exception(f"MyMemory request failed: {str(e)}")
    
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