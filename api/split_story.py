from http.server import BaseHTTPRequestHandler
import json
import re

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Read JSON body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Validate input
            if "text" not in data:
                self.send_error_response(400, "Missing 'text' field in request")
                return
            
            raw_text = data["text"]
            target_words = data.get("target_words", 350)  # Default 350 words for 2-3 min videos
            
            if not raw_text or not raw_text.strip():
                self.send_error_response(400, "Text cannot be empty")
                return
            
            # Clean and split the text
            cleaned_text = self.clean_transcript(raw_text)
            story_parts = self.split_into_parts(cleaned_text, target_words)
            
            # Validate we got parts
            if not story_parts:
                self.send_error_response(400, "Could not create any story parts from text")
                return
            
            # Calculate statistics
            total_words = sum(len(part.split()) for part in story_parts)
            
            response_data = {
                "parts": story_parts,
                "part_count": len(story_parts),
                "total_words": total_words,
                "avg_words_per_part": total_words // len(story_parts) if story_parts else 0,
                "target_words": target_words
            }
            
            self.send_success_response(response_data)
            
        except json.JSONDecodeError as e:
            self.send_error_response(400, f"Invalid JSON: {str(e)}")
        except Exception as e:
            self.send_error_response(500, f"Unexpected error: {str(e)}")
    
    def clean_transcript(self, text):
        """
        Remove timestamps, speaker labels, and other non-story content.
        Keep only the pure story text.
        """
        # Remove timestamp patterns like "0 (59s):", "0 (1m 43s):", "1 (2m 32s):"
        text = re.sub(r'\d+\s*\(\d+[smh]+\s*\d*[smh]*\):', '', text)
        
        # Remove standalone timestamps like "[00:15]", "(1:23)", etc.
        text = re.sub(r'\[?\d{1,2}:\d{2}:\d{2}\]?', '', text)
        text = re.sub(r'\[?\d{1,2}:\d{2}\]?', '', text)
        
        # Remove common speaker labels (Host:, Guest:, Narrator:, etc.)
        text = re.sub(r'\b(Host|Guest|Narrator|Speaker \d+):\s*', '', text, flags=re.IGNORECASE)
        
        # Remove common intro/outro phrases (can expand this list)
        removal_phrases = [
            r'welcome to [^.!?]+[.!?]',
            r'don\'t forget to subscribe[^.!?]*[.!?]',
            r'this episode is brought to you by[^.!?]*[.!?]',
            r'thanks to our sponsor[^.!?]*[.!?]',
            r'before we begin[^.!?]*[.!?]',
            r'let\'s get into it[.!?]',
        ]
        
        for phrase in removal_phrases:
            text = re.sub(phrase, '', text, flags=re.IGNORECASE)
        
        # Remove music/sound effect markers
        text = re.sub(r'\[MUSIC\]|\[SOUND EFFECT\]|\[SFX\]|\[AUDIO\]', '', text, flags=re.IGNORECASE)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        return text
    
    def split_into_parts(self, text, target_words=350):
        """
        Split text into parts of approximately target_words each.
        Ensures parts end at sentence boundaries for natural flow.
        """
        # Split into sentences (handles common punctuation)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        parts = []
        current_part = []
        current_word_count = 0
        
        # Min and max word bounds (allow some flexibility)
        min_words = int(target_words * 0.8)  # 80% of target (280 words for 350 target)
        max_words = int(target_words * 1.2)  # 120% of target (420 words for 350 target)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            sentence_words = len(sentence.split())
            
            # If adding this sentence would exceed max, start a new part
            if current_word_count > 0 and (current_word_count + sentence_words) > max_words:
                # Only create part if it meets minimum word count
                if current_word_count >= min_words:
                    parts.append(' '.join(current_part))
                    current_part = [sentence]
                    current_word_count = sentence_words
                else:
                    # Still too short, add the sentence anyway
                    current_part.append(sentence)
                    current_word_count += sentence_words
            else:
                # Add sentence to current part
                current_part.append(sentence)
                current_word_count += sentence_words
                
                # If we've reached target and have good stopping point, finalize part
                if current_word_count >= target_words:
                    parts.append(' '.join(current_part))
                    current_part = []
                    current_word_count = 0
        
        # Add any remaining text as the final part
        if current_part:
            parts.append(' '.join(current_part))
        
        return parts
    
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