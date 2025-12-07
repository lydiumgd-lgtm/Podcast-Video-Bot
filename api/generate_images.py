from http.server import BaseHTTPRequestHandler
import json
import base64
import io
import sys
import requests
from PIL import Image

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
            batch_size = data.get("batch_size", 1)  # Process 1 image at a time to avoid timeouts
            
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
            
            print(f"Generating images for batch {batch_index + 1}: parts {start_idx + 1} to {end_idx} of {len(parts)}", file=sys.stderr)
            
            # Generate images for batch
            image_batch = []
            
            for i, part in enumerate(batch_parts):
                actual_index = start_idx + i
                
                if not part or not part.strip():
                    image_batch.append({
                        "image": None,
                        "width": 0,
                        "height": 0,
                        "size": 0,
                        "error": "Empty text"
                    })
                    continue
                
                try:
                    print(f"Generating image for part {actual_index + 1}/{len(parts)}...", file=sys.stderr)
                    image_data = self.generate_image(part, actual_index + 1)
                    image_batch.append(image_data)
                    print(f"Part {actual_index + 1} image generated: {image_data['width']}x{image_data['height']}, {image_data['size']} bytes", file=sys.stderr)
                except Exception as e:
                    print(f"Part {actual_index + 1} image generation failed: {str(e)}", file=sys.stderr)
                    image_batch.append({
                        "image": None,
                        "width": 0,
                        "height": 0,
                        "size": 0,
                        "error": str(e)
                    })
            
            # Determine if more batches remain
            has_more = end_idx < len(parts)
            
            response_data = {
                "image_batch": image_batch,
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
    
    def generate_image(self, text, part_number):
        """
        Generate AI image from text using HuggingFace Stable Diffusion API (free).
        Returns dict with base64 image data and metadata.
        """
        # Extract key elements from text for prompt generation
        prompt = self.create_prompt_from_text(text, part_number)
        
        # Use HuggingFace Inference API (free, no API key required for public models)
        # Using runwayml/stable-diffusion-v1-5 or stabilityai/stable-diffusion-2-1
        api_url = "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "num_inference_steps": 30,  # Lower for faster generation
                "guidance_scale": 7.5,
                "width": 1080,
                "height": 1920  # 9:16 vertical format for short videos
            }
        }
        
        print(f"Requesting image with prompt: {prompt[:100]}...", file=sys.stderr)
        
        # Make request with timeout
        response = requests.post(api_url, headers=headers, json=payload, timeout=20)
        
        if response.status_code == 503:
            # Model is loading, wait a bit and retry once
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
        
        # Validate it's actually an image
        try:
            img = Image.open(io.BytesIO(image_bytes))
            width, height = img.size
        except Exception as e:
            raise Exception(f"Invalid image response: {str(e)}")
        
        # Optimize image size (compress if too large)
        img_optimized = self.optimize_image(img)
        output_buffer = io.BytesIO()
        img_optimized.save(output_buffer, format='JPEG', quality=85, optimize=True)
        image_bytes = output_buffer.getvalue()
        
        # Check size limit (4MB for Vercel)
        if len(image_bytes) > 3 * 1024 * 1024:  # 3MB safety margin
            # Further compress
            img_optimized.save(output_buffer, format='JPEG', quality=75, optimize=True)
            image_bytes = output_buffer.getvalue()
        
        # Convert to base64 for JSON transmission
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        return {
            "image": image_base64,  # Base64 encoded JPEG
            "width": width,
            "height": height,
            "size": len(image_bytes),  # Bytes
            "format": "jpeg",
            "prompt": prompt  # Return prompt for reference
        }
    
    def create_prompt_from_text(self, text, part_number):
        """
        Create an engaging image prompt from story text.
        Focuses on horror/true crime atmosphere.
        """
        # Extract first 2-3 sentences for context
        sentences = text.split('.')[:3]
        context = '. '.join(sentences).strip()
        
        # Remove common words and focus on key nouns/verbs
        words = context.split()
        key_words = [w for w in words if len(w) > 4][:5]  # Get 5 key words
        
        # Create horror/true crime style prompt
        base_prompt = f"dark atmospheric scene, horror, true crime story, cinematic lighting, dramatic shadows, mysterious, {', '.join(key_words[:3])}"
        
        # Add style modifiers
        style_modifiers = "high quality, detailed, 4k, professional photography, moody, suspenseful"
        
        prompt = f"{base_prompt}, {style_modifiers}"
        
        # Limit prompt length
        if len(prompt) > 200:
            prompt = prompt[:200]
        
        return prompt
    
    def optimize_image(self, img):
        """
        Optimize image for web use while maintaining quality.
        Resize if needed, convert to RGB if necessary.
        """
        # Ensure RGB mode (remove alpha channel if present)
        if img.mode != 'RGB':
            rgb_img = Image.new('RGB', img.size, (0, 0, 0))
            rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = rgb_img
        
        # Resize if too large (max 1920x1080 for vertical)
        max_width = 1080
        max_height = 1920
        
        if img.width > max_width or img.height > max_height:
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
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

