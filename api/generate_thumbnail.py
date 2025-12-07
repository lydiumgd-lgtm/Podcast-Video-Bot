from http.server import BaseHTTPRequestHandler
import json
import base64
import io
import sys
import requests
from PIL import Image, ImageDraw, ImageFont

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Read JSON body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Validate input
            if "title" not in data:
                self.send_error_response(400, "Missing 'title' field in request")
                return
            
            title = data["title"]
            description = data.get("description", "")
            style = data.get("style", "horror")  # horror, true_crime, etc.
            
            print(f"Generating thumbnail for: {title[:50]}...", file=sys.stderr)
            
            try:
                # Generate thumbnail
                thumbnail_data = self.generate_thumbnail(title, description, style)
                
                response_data = {
                    "thumbnail": thumbnail_data["thumbnail"],
                    "width": thumbnail_data["width"],
                    "height": thumbnail_data["height"],
                    "size": thumbnail_data["size"],
                    "format": thumbnail_data["format"]
                }
                
                self.send_success_response(response_data)
                
            except Exception as e:
                print(f"Thumbnail generation failed: {str(e)}", file=sys.stderr)
                raise Exception(f"Thumbnail generation failed: {str(e)}")
            
        except json.JSONDecodeError as e:
            self.send_error_response(400, f"Invalid JSON: {str(e)}")
        except Exception as e:
            self.send_error_response(500, f"Unexpected error: {str(e)}")
    
    def generate_thumbnail(self, title, description, style):
        """
        Generate YouTube-style thumbnail with AI image and text overlay.
        Returns dict with base64 thumbnail data and metadata.
        """
        # Generate base image using Stable Diffusion
        prompt = self.create_thumbnail_prompt(title, description, style)
        
        # Use HuggingFace Inference API
        api_url = "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "num_inference_steps": 25,
                "guidance_scale": 7.5,
                "width": 1280,
                "height": 720  # YouTube thumbnail size (16:9)
            }
        }
        
        print(f"Requesting thumbnail image with prompt: {prompt[:100]}...", file=sys.stderr)
        
        # Make request with timeout
        response = requests.post(api_url, headers=headers, json=payload, timeout=20)
        
        if response.status_code == 503:
            # Model is loading, wait and retry
            print("Model loading, waiting 5 seconds...", file=sys.stderr)
            import time
            time.sleep(5)
            response = requests.post(api_url, headers=headers, json=payload, timeout=20)
        
        if response.status_code != 200:
            error_msg = f"API returned status {response.status_code}"
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_msg = error_data["error"]
            except:
                pass
            raise Exception(f"HuggingFace API error: {error_msg}")
        
        # Get image bytes
        image_bytes = response.content
        
        # Load and process image
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert('RGB')
        img = img.resize((1280, 720), Image.Resampling.LANCZOS)
        
        # Add text overlay
        img = self.add_text_overlay(img, title)
        
        # Optimize image
        output_buffer = io.BytesIO()
        img.save(output_buffer, format='JPEG', quality=90, optimize=True)
        thumbnail_bytes = output_buffer.getvalue()
        
        # Convert to base64
        thumbnail_base64 = base64.b64encode(thumbnail_bytes).decode('utf-8')
        
        return {
            "thumbnail": thumbnail_base64,
            "width": 1280,
            "height": 720,
            "size": len(thumbnail_bytes),
            "format": "jpeg"
        }
    
    def create_thumbnail_prompt(self, title, description, style):
        """Create prompt for thumbnail image generation"""
        # Extract key words from title
        words = title.lower().split()
        key_words = [w for w in words if len(w) > 3][:5]
        
        # Style-specific prompts
        if style == "horror" or "horror" in title.lower():
            base_prompt = f"dark atmospheric horror scene, mysterious, suspenseful, {', '.join(key_words[:3])}"
        elif style == "true_crime" or "crime" in title.lower():
            base_prompt = f"true crime scene, dramatic, investigative, mysterious, {', '.join(key_words[:3])}"
        else:
            base_prompt = f"dramatic scene, cinematic, {', '.join(key_words[:3])}"
        
        # Add style modifiers
        style_modifiers = "high quality, detailed, 4k, professional photography, YouTube thumbnail style, eye-catching, bold colors, high contrast"
        
        prompt = f"{base_prompt}, {style_modifiers}"
        
        # Limit prompt length
        if len(prompt) > 200:
            prompt = prompt[:200]
        
        return prompt
    
    def add_text_overlay(self, img, title):
        """Add title text overlay to thumbnail"""
        draw = ImageDraw.Draw(img)
        
        # Try to load a bold font
        font_size = 72
        try:
            # Try system fonts (varies by system)
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                # Fallback to default font (smaller)
                try:
                    font = ImageFont.load_default()
                    font_size = 20
                except:
                    font = None
        
        # Split title into lines (max 40 chars per line, max 2 lines)
        words = title.split()
        lines = []
        current_line = ""
        
        for word in words:
            if len(current_line + word) < 40:
                current_line += word + " "
            else:
                if current_line:
                    lines.append(current_line.strip())
                current_line = word + " "
                if len(lines) >= 1:  # Max 2 lines
                    break
        
        if current_line:
            lines.append(current_line.strip())
        
        # Calculate text position (center, slightly above middle)
        img_width, img_height = img.size
        text_y = int(img_height * 0.4)  # 40% down
        line_height = 90
        
        # Draw text with outline for readability
        for i, line in enumerate(lines):
            y_pos = text_y + (i * line_height)
            
            # Draw black outline (shadow) for better visibility
            for dx in [-3, -2, -1, 0, 1, 2, 3]:
                for dy in [-3, -2, -1, 0, 1, 2, 3]:
                    if dx != 0 or dy != 0:
                        draw.text((img_width // 2 + dx, y_pos + dy), line, 
                                 fill=(0, 0, 0), font=font, anchor="mm", stroke_width=2)
            
            # Draw white text
            draw.text((img_width // 2, y_pos), line, 
                     fill=(255, 255, 255), font=font, anchor="mm", stroke_width=1)
        
        return img
    
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

