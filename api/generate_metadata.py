from http.server import BaseHTTPRequestHandler
import json
import sys

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Read JSON body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Validate input
            if "translated_parts" not in data:
                self.send_error_response(400, "Missing 'translated_parts' field in request")
                return
            
            translated_parts = data["translated_parts"]
            
            if not isinstance(translated_parts, list):
                self.send_error_response(400, "'translated_parts' must be an array")
                return
            
            if len(translated_parts) == 0:
                self.send_error_response(400, "translated_parts array cannot be empty")
                return
            
            print(f"Generating metadata for {len(translated_parts)} parts", file=sys.stderr)
            
            # Generate metadata for all parts
            metadata_list = []
            
            for i, part_text in enumerate(translated_parts):
                part_number = i + 1
                try:
                    print(f"Generating metadata for part {part_number}/{len(translated_parts)}...", file=sys.stderr)
                    metadata = self.generate_part_metadata(part_text, part_number, len(translated_parts))
                    metadata_list.append(metadata)
                except Exception as e:
                    print(f"Part {part_number} metadata generation failed: {str(e)}", file=sys.stderr)
                    # Create default metadata on error
                    metadata_list.append(self.create_default_metadata(part_number, len(translated_parts)))
            
            # Generate full video metadata (for long-form compilation)
            full_metadata = self.generate_full_metadata(translated_parts)
            
            response_data = {
                "part_metadata": metadata_list,
                "full_metadata": full_metadata,
                "total_parts": len(translated_parts)
            }
            
            self.send_success_response(response_data)
            
        except json.JSONDecodeError as e:
            self.send_error_response(400, f"Invalid JSON: {str(e)}")
        except Exception as e:
            self.send_error_response(500, f"Unexpected error: {str(e)}")
    
    def generate_part_metadata(self, text, part_number, total_parts):
        """
        Generate title, description, and tags for a single video part.
        """
        # Extract key phrases from text
        sentences = text.split('.')[:3]  # First 3 sentences
        key_phrases = self.extract_key_phrases(text)
        
        # Generate title
        title = self.generate_title(text, part_number, total_parts, key_phrases)
        
        # Generate description
        description = self.generate_description(text, part_number, total_parts, key_phrases)
        
        # Generate tags
        tags = self.generate_tags(key_phrases, part_number, total_parts)
        
        return {
            "part_number": part_number,
            "title": title,
            "description": description,
            "tags": tags,
            "key_phrases": key_phrases[:5]  # Top 5 key phrases
        }
    
    def extract_key_phrases(self, text):
        """Extract important words/phrases from text"""
        # Simple keyword extraction (remove common words)
        common_words = {'ang', 'ng', 'sa', 'na', 'ay', 'at', 'o', 'si', 'ni', 'kay', 'para', 'nga', 'din', 'rin', 
                       'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
                       'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did'}
        
        words = text.lower().split()
        # Filter out common words and short words
        key_words = [w for w in words if len(w) > 4 and w not in common_words]
        
        # Count frequency
        from collections import Counter
        word_freq = Counter(key_words)
        
        # Return top keywords
        return [word for word, count in word_freq.most_common(10)]
    
    def generate_title(self, text, part_number, total_parts, key_phrases):
        """Generate engaging title for video part"""
        # Extract first sentence or key phrase
        first_sentence = text.split('.')[0].strip()
        
        # Create title with part number
        if total_parts > 1:
            title_prefix = f"Bahagi {part_number}: "
        else:
            title_prefix = ""
        
        # Use first 50 characters of first sentence, or key phrase
        if len(first_sentence) > 50:
            title_suffix = first_sentence[:47] + "..."
        else:
            title_suffix = first_sentence
        
        # If we have key phrases, try to incorporate them
        if key_phrases and len(key_phrases) > 0:
            # Try to use a key phrase if it's short enough
            for phrase in key_phrases[:3]:
                if len(phrase) <= 30:
                    title_suffix = phrase.capitalize()
                    break
        
        title = title_prefix + title_suffix
        
        # Ensure title isn't too long (YouTube limit is 100 chars, but shorter is better)
        if len(title) > 60:
            title = title[:57] + "..."
        
        return title
    
    def generate_description(self, text, part_number, total_parts, key_phrases):
        """Generate description for video part"""
        # Start with part info
        if total_parts > 1:
            description = f"Bahagi {part_number} ng {total_parts} na serye.\n\n"
        else:
            description = ""
        
        # Add first 2-3 sentences of the story
        sentences = [s.strip() for s in text.split('.') if s.strip()][:3]
        description += '. '.join(sentences)
        if len(sentences) > 0:
            description += "."
        
        # Add engagement hooks
        description += "\n\n"
        description += "🔔 Mag-subscribe para sa mas maraming kwentong takot!\n"
        description += "👍 I-like kung nagustuhan mo ang kwento!\n"
        description += "💬 Mag-comment ng iyong mga karanasan!"
        
        # Add hashtags from key phrases
        if key_phrases:
            description += "\n\n"
            hashtags = [f"#{phrase.replace(' ', '')}" for phrase in key_phrases[:3] if len(phrase.replace(' ', '')) < 20]
            description += " ".join(hashtags)
        
        # Add standard tags
        description += " #KwentongTakot #TrueCrime #HorrorStory #TagalogHorror #PinoyHorror"
        
        return description
    
    def generate_tags(self, key_phrases, part_number, total_parts):
        """Generate tags for video part"""
        # Base tags (always include)
        tags = [
            "kwentong takot",
            "true crime",
            "horror story",
            "tagalog horror",
            "pinoy horror",
            "filipino horror",
            "scary story",
            "true story",
            "mystery",
            "suspense"
        ]
        
        # Add part-specific tags
        if total_parts > 1:
            tags.append(f"bahagi {part_number}")
            tags.append("serye")
        
        # Add key phrase tags (if they're good keywords)
        for phrase in key_phrases[:5]:
            if len(phrase) > 3 and len(phrase) < 20:
                tags.append(phrase.lower())
        
        # Remove duplicates and limit to 20 tags
        unique_tags = list(dict.fromkeys(tags))[:20]
        
        return unique_tags
    
    def generate_full_metadata(self, translated_parts):
        """Generate metadata for the full long-form video"""
        # Combine all parts
        full_text = " ".join(translated_parts)
        
        # Extract key phrases from full text
        key_phrases = self.extract_key_phrases(full_text)
        
        # Generate title
        first_part = translated_parts[0] if translated_parts else ""
        first_sentence = first_part.split('.')[0].strip() if first_part else "Kwentong Takot"
        
        if len(first_sentence) > 60:
            title = first_sentence[:57] + "..."
        else:
            title = first_sentence
        
        title = f"Buong Kwento: {title}"
        
        # Generate description
        description = "🎬 BUONG KWENTO - Lahat ng Bahagi\n\n"
        description += "Panoorin ang buong kwento mula simula hanggang wakas.\n\n"
        
        # Add summary from first and last parts
        if len(translated_parts) > 0:
            first_sentences = '. '.join([s.strip() for s in translated_parts[0].split('.')[:2] if s.strip()])
            description += first_sentences + ".\n\n"
        
        description += "📌 Mga Bahagi:\n"
        for i, part in enumerate(translated_parts[:10], 1):  # List first 10 parts
            part_preview = part.split('.')[0][:50] if part else ""
            description += f"{i}. {part_preview}...\n"
        
        if len(translated_parts) > 10:
            description += f"... at {len(translated_parts) - 10} pang bahagi\n"
        
        description += "\n"
        description += "🔔 Mag-subscribe para sa mas maraming kwentong takot!\n"
        description += "👍 I-like kung nagustuhan mo ang kwento!\n"
        description += "💬 Mag-comment ng iyong mga karanasan!\n\n"
        description += "#KwentongTakot #TrueCrime #HorrorStory #TagalogHorror #PinoyHorror #BuongKwento"
        
        # Generate tags
        tags = [
            "kwentong takot",
            "true crime",
            "horror story",
            "tagalog horror",
            "pinoy horror",
            "filipino horror",
            "buong kwento",
            "full story",
            "complete story",
            "scary story",
            "true story",
            "mystery",
            "suspense",
            "compilation"
        ]
        
        # Add key phrase tags
        for phrase in key_phrases[:10]:
            if len(phrase) > 3 and len(phrase) < 20:
                tags.append(phrase.lower())
        
        # Remove duplicates and limit
        unique_tags = list(dict.fromkeys(tags))[:25]
        
        return {
            "title": title,
            "description": description,
            "tags": unique_tags,
            "total_parts": len(translated_parts)
        }
    
    def create_default_metadata(self, part_number, total_parts):
        """Create default metadata if generation fails"""
        return {
            "part_number": part_number,
            "title": f"Bahagi {part_number}: Kwentong Takot" if total_parts > 1 else "Kwentong Takot",
            "description": f"Bahagi {part_number} ng kwentong takot.\n\nMag-subscribe para sa mas maraming kwento!",
            "tags": ["kwentong takot", "true crime", "horror story", "tagalog horror"],
            "key_phrases": []
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

