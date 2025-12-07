from http.server import BaseHTTPRequestHandler
import json
import os
import sys

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
            batch_index = data.get("batch_index", 0)  # Which batch to process
            batch_size = data.get("batch_size", 10)   # Parts per batch (default 10)
            
            if not isinstance(parts, list):
                self.send_error_response(400, "'parts' must be an array")
                return
            
            if len(parts) == 0:
                self.send_error_response(400, "Parts array cannot be empty")
                return
            
            # Calculate batch range
            start_idx = batch_index * batch_size
            end_idx = min(start_idx + batch_size, len(parts))
            batch_parts = parts[start_idx:end_idx]
            
            print(f"Processing batch {batch_index + 1}: parts {start_idx + 1} to {end_idx} of {len(parts)}", file=sys.stderr)
            
            # Translate batch
            translated_batch = []
            
            for i, part in enumerate(batch_parts):
                actual_index = start_idx + i
                if not part or not part.strip():
                    translated_batch.append("")
                    continue
                
                try:
                    print(f"Translating part {actual_index + 1}/{len(parts)}...", file=sys.stderr)
                    translated = self.translate_text(part)
                    translated_batch.append(translated)
                    print(f"Part {actual_index + 1} translated successfully", file=sys.stderr)
                except Exception as e:
                    print(f"Part {actual_index + 1} failed: {str(e)}", file=sys.stderr)
                    self.send_error_response(500, f"Translation failed at part {actual_index + 1}: {str(e)}")
                    return
            
            # Calculate statistics for this batch
            batch_original_chars = sum(len(part) for part in batch_parts)
            batch_translated_chars = sum(len(part) for part in translated_batch)
            
            # Determine if more batches remain
            has_more = end_idx < len(parts)
            
            response_data = {
                "translated_batch": translated_batch,
                "batch_index": batch_index,
                "batch_size": batch_size,
                "batch_start": start_idx,
                "batch_end": end_idx,
                "total_parts": len(parts),
                "has_more": has_more,
                "next_batch_index": batch_index + 1 if has_more else None,
                "original_chars": batch_original_chars,
                "translated_chars": batch_translated_chars
            }
            
            self.send_success_response(response_data)
            
        except json.JSONDecodeError as e:
            self.send_error_response(400, f"Invalid JSON: {str(e)}")
        except Exception as e:
            self.send_error_response(500, f"Unexpected error: {str(e)}")
    
    def translate_text(self, text):
        """
        Translate English text to Filipino (Tagalog).
        Uses multiple free translation services.
        """
        # Method 1: Google Translate (via googletrans library - most reliable)
        try:
            print("Trying Google Translate...", file=sys.stderr)
            return self.translate_with_google(text)
        except Exception as e:
            print(f"Google Translate failed: {str(e)}", file=sys.stderr)
        
        # Method 2: LibreTranslate public API
        try:
            print("Trying LibreTranslate...", file=sys.stderr)
            return self.translate_with_libretranslate(text)
        except Exception as e:
            print(f"LibreTranslate failed: {str(e)}", file=sys.stderr)
        
        # Method 3: MyMemory API
        try:
            print("Trying MyMemory...", file=sys.stderr)
            return self.translate_with_mymemory(text)
        except Exception as e:
            print(f"MyMemory failed: {str(e)}", file=sys.stderr)
        
        # If all methods fail
        raise Exception("All translation services failed. The text may be too long or services are temporarily unavailable.")
    
    def translate_with_google(self, text):
        """
        Use Google Translate via googletrans library (unofficial but free and reliable).
        """
        from googletrans import Translator
        import time
        
        translator = Translator()
        
        # Google Translate can handle long text, but we'll chunk for safety
        max_chunk_size = 5000  # characters
        
        if len(text) <= max_chunk_size:
            result = translator.translate(text, src='en', dest='tl')
            return result.text
        
        # Split into chunks by sentences
        sentences = text.replace('! ', '!|').replace('? ', '?|').replace('. ', '.|').split('|')
        translated_chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            if current_length + len(sentence) > max_chunk_size and current_chunk:
                # Translate current chunk
                chunk_text = ' '.join(current_chunk)
                result = translator.translate(chunk_text, src='en', dest='tl')
                translated_chunks.append(result.text)
                current_chunk = [sentence]
                current_length = len(sentence)
                time.sleep(0.5)  # Small delay to avoid rate limits
            else:
                current_chunk.append(sentence)
                current_length += len(sentence) + 1
        
        # Translate remaining chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            result = translator.translate(chunk_text, src='en', dest='tl')
            translated_chunks.append(result.text)
        
        return ' '.join(translated_chunks)
    
    def translate_with_libretranslate(self, text):
        """
        Use LibreTranslate public API (free, open-source).
        """
        import requests
        
        # Public LibreTranslate instance
        url = "https://libretranslate.com/translate"
        
        # Split text if too long (LibreTranslate has limits)
        max_chunk_size = 5000
        
        if len(text) <= max_chunk_size:
            payload = {
                "q": text,
                "source": "en",
                "target": "tl",
                "format": "text"
            }
            
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            return data.get("translatedText", "")
        
        # Split into chunks
        sentences = text.replace('! ', '!|').replace('? ', '?|').replace('. ', '.|').split('|')
        translated_chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            if current_length + len(sentence) > max_chunk_size and current_chunk:
                chunk_text = ' '.join(current_chunk)
                payload = {
                    "q": chunk_text,
                    "source": "en",
                    "target": "tl",
                    "format": "text"
                }
                response = requests.post(url, json=payload, timeout=60)
                response.raise_for_status()
                data = response.json()
                translated_chunks.append(data.get("translatedText", ""))
                current_chunk = [sentence]
                current_length = len(sentence)
            else:
                current_chunk.append(sentence)
                current_length += len(sentence) + 1
        
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            payload = {
                "q": chunk_text,
                "source": "en",
                "target": "tl",
                "format": "text"
            }
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            translated_chunks.append(data.get("translatedText", ""))
        
        return ' '.join(translated_chunks)
    
    def translate_with_mymemory(self, text):
        """
        Use MyMemory Translation API (free, no auth required).
        """
        import requests
        from urllib.parse import quote
        
        # Split text into chunks (MyMemory has 500 char limit)
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
                chunk_text = ' '.join(current_chunk)
                translated_chunks.append(self._translate_chunk_mymemory(chunk_text))
                current_chunk = [sentence]
                current_length = len(sentence)
            else:
                current_chunk.append(sentence)
                current_length += len(sentence) + 1
        
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            translated_chunks.append(self._translate_chunk_mymemory(chunk_text))
        
        return ' '.join(translated_chunks)
    
    def _translate_chunk_mymemory(self, text):
        """Helper to translate a single chunk with MyMemory API"""
        import requests
        from urllib.parse import quote
        
        encoded_text = quote(text)
        url = f"https://api.mymemory.translated.net/get?q={encoded_text}&langpair=en|tl"
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("responseStatus") == 200 or data.get("responseStatus") == "200":
            translated = data.get("responseData", {}).get("translatedText", "")
            if translated:
                return translated
        
        raise Exception(f"MyMemory API error: {data.get('responseDetails', 'Unknown error')}")
    
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