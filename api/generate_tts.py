from http.server import BaseHTTPRequestHandler
import json
import base64
import io
import sys
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
            batch_index = data.get("batch_index", 0)
            batch_size = data.get("batch_size", 5)  # 5 parts per batch (TTS is slower)
            
            # Voice settings (with defaults)
            voice_lang = data.get("voice_lang", "tl")  # Language code (tl=Tagalog, en=English, etc.)
            voice_speed = data.get("voice_speed", False)  # False=normal, True=slow
            
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
            
            print(f"Generating audio for batch {batch_index + 1}: parts {start_idx + 1} to {end_idx} of {len(parts)}", file=sys.stderr)
            
            # Generate audio for batch
            audio_batch = []
            
            for i, part in enumerate(batch_parts):
                actual_index = start_idx + i
                
                if not part or not part.strip():
                    audio_batch.append({
                        "audio": None,
                        "duration": 0,
                        "size": 0,
                        "error": "Empty text"
                    })
                    continue
                
                try:
                    print(f"Generating audio for part {actual_index + 1}/{len(parts)}...", file=sys.stderr)
                    audio_data = self.generate_audio(part, voice_lang, voice_speed)
                    audio_batch.append(audio_data)
                    print(f"Part {actual_index + 1} audio generated: {audio_data['duration']:.1f}s, {audio_data['size']} bytes", file=sys.stderr)
                except Exception as e:
                    print(f"Part {actual_index + 1} audio generation failed: {str(e)}", file=sys.stderr)
                    audio_batch.append({
                        "audio": None,
                        "duration": 0,
                        "size": 0,
                        "error": str(e)
                    })
            
            # Determine if more batches remain
            has_more = end_idx < len(parts)
            
            response_data = {
                "audio_batch": audio_batch,
                "batch_index": batch_index,
                "batch_size": batch_size,
                "batch_start": start_idx,
                "batch_end": end_idx,
                "total_parts": len(parts),
                "has_more": has_more,
                "next_batch_index": batch_index + 1 if has_more else None
            }
            
            self.send_success_response(response_data)
            
        except json.JSONDecodeError as e:
            self.send_error_response(400, f"Invalid JSON: {str(e)}")
        except Exception as e:
            self.send_error_response(500, f"Unexpected error: {str(e)}")
    
    def generate_audio(self, text, lang='tl', slow=False):
        """
        Generate audio from text using gTTS.
        Args:
            text: Text to convert to speech
            lang: Language code (tl=Tagalog, en=English, etc.)
            slow: If True, speaks slower
        Returns dict with base64 audio data and metadata.
        """
        from gtts import gTTS
        from pydub import AudioSegment
        
        # Validate language code
        valid_langs = {
            'tl': 'Tagalog (Filipino)',
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'ja': 'Japanese',
            'ko': 'Korean',
            'zh': 'Chinese',
            'hi': 'Hindi',
            'ar': 'Arabic'
        }
        
        if lang not in valid_langs:
            lang = 'tl'  # Default to Tagalog if invalid
        
        # Create gTTS object with selected language and speed
        tts = gTTS(text=text, lang=lang, slow=slow)
        
        # Save to BytesIO buffer
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        
        # Get audio data
        audio_bytes = audio_buffer.getvalue()
        
        # Calculate duration using pydub
        try:
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            duration_seconds = len(audio_segment) / 1000.0  # pydub uses milliseconds
        except Exception as e:
            # Fallback: estimate duration based on text length
            # Average speaking rate: ~150 words per minute
            word_count = len(text.split())
            duration_seconds = (word_count / 150.0) * 60.0
            print(f"Could not get exact duration, estimated: {duration_seconds:.1f}s", file=sys.stderr)
        
        # Convert to base64 for JSON transmission
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        return {
            "audio": audio_base64,  # Base64 encoded MP3
            "duration": round(duration_seconds, 2),  # Seconds
            "size": len(audio_bytes),  # Bytes
            "format": "mp3"
        }
    
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