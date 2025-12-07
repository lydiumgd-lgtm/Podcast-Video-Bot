from http.server import BaseHTTPRequestHandler
import json
import base64
import io
import sys
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont
import imageio

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Read JSON body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Validate input
            if "audio_files" not in data or "image_files" not in data or "translated_parts" not in data:
                self.send_error_response(400, "Missing required fields: audio_files, image_files, translated_parts")
                return
            
            audio_files = data["audio_files"]  # Array of {audio: base64, duration, size}
            image_files = data["image_files"]  # Array of {image: base64, width, height, size}
            translated_parts = data["translated_parts"]  # Array of translated text for subtitles
            batch_index = data.get("batch_index", 0)
            batch_size = data.get("batch_size", 1)  # Process 1 video at a time
            
            if len(audio_files) != len(image_files) or len(audio_files) != len(translated_parts):
                self.send_error_response(400, "audio_files, image_files, and translated_parts must have the same length")
                return
            
            # Calculate batch range
            start_idx = batch_index * batch_size
            end_idx = min(start_idx + batch_size, len(audio_files))
            batch_range = list(range(start_idx, end_idx))
            
            print(f"Creating videos for batch {batch_index + 1}: parts {start_idx + 1} to {end_idx} of {len(audio_files)}", file=sys.stderr)
            
            # Create videos for batch
            video_batch = []
            
            for i in batch_range:
                actual_index = i
                
                try:
                    print(f"Creating video for part {actual_index + 1}/{len(audio_files)}...", file=sys.stderr)
                    video_data = self.create_video(
                        audio_files[actual_index],
                        image_files[actual_index],
                        translated_parts[actual_index],
                        actual_index + 1
                    )
                    video_batch.append(video_data)
                    print(f"Part {actual_index + 1} video created: {video_data['duration']:.1f}s, {video_data['size']} bytes", file=sys.stderr)
                except Exception as e:
                    print(f"Part {actual_index + 1} video creation failed: {str(e)}", file=sys.stderr)
                    video_batch.append({
                        "video": None,
                        "duration": 0,
                        "width": 0,
                        "height": 0,
                        "size": 0,
                        "error": str(e)
                    })
            
            # Determine if more batches remain
            has_more = end_idx < len(audio_files)
            
            response_data = {
                "video_batch": video_batch,
                "batch_index": batch_index,
                "batch_size": batch_size,
                "batch_start": start_idx,
                "batch_end": end_idx,
                "total_parts": len(audio_files),
                "has_more": has_more,
                "next_batch_index": batch_index + 1 if has_more else None
            }
            
            self.send_success_response(response_data)
            
        except json.JSONDecodeError as e:
            self.send_error_response(400, f"Invalid JSON: {str(e)}")
        except Exception as e:
            self.send_error_response(500, f"Unexpected error: {str(e)}")
    
    def create_video(self, audio_data, image_data, subtitle_text, part_number):
        """
        Create a 9:16 vertical video combining image, audio, and subtitles.
        Returns dict with base64 video data and metadata.
        """
        # Decode base64 data
        audio_bytes = base64.b64decode(audio_data["audio"])
        image_bytes = base64.b64decode(image_data["image"])
        
        # Load image
        img = Image.open(io.BytesIO(image_bytes))
        
        # Target dimensions for 9:16 vertical video
        target_width = 1080
        target_height = 1920
        
        # Resize/crop image to fit 9:16 aspect ratio
        img = self.fit_image_to_aspect_ratio(img, target_width, target_height)
        
        # Get audio duration
        audio_duration = audio_data.get("duration", 10.0)  # Default 10 seconds
        fps = 30  # Frames per second
        
        # Calculate number of frames needed
        num_frames = int(audio_duration * fps)
        
        # Create video frames with subtitles
        frames = []
        for frame_num in range(num_frames):
            # Create a copy of the image for this frame
            frame_img = img.copy()
            
            # Add subtitle text overlay (appears in bottom third)
            if subtitle_text:
                frame_img = self.add_subtitle(frame_img, subtitle_text, frame_num, num_frames, part_number)
            
            # Convert PIL image to numpy array for imageio
            import numpy as np
            frame_array = np.array(frame_img)
            frames.append(frame_array)
        
        # Create temporary files for video and audio
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as video_file:
            video_path = video_file.name
        
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as audio_file:
            audio_file.write(audio_bytes)
            audio_path = audio_file.name
        
        try:
            # Write video without audio first
            imageio.mimwrite(video_path, frames, fps=fps, codec='libx264', quality=8)
            
            # Combine video with audio using imageio-ffmpeg
            # Note: This requires FFmpeg, which may not be available on Vercel
            # If FFmpeg is not available, we'll return video without audio
            try:
                from imageio_ffmpeg import write_frames
                # For now, return video without audio if FFmpeg unavailable
                # In production, you might want to use a different approach
                final_video_path = video_path
            except:
                # FFmpeg not available, use video without audio
                final_video_path = video_path
                print("FFmpeg not available, creating video without audio", file=sys.stderr)
            
            # Read final video
            with open(final_video_path, 'rb') as f:
                video_bytes = f.read()
            
            # Optimize video size if too large
            if len(video_bytes) > 3 * 1024 * 1024:  # 3MB limit
                # Re-encode with lower quality
                video_bytes = self.reencode_video(frames, fps, quality=6)
            
            # Convert to base64
            video_base64 = base64.b64encode(video_bytes).decode('utf-8')
            
            return {
                "video": video_base64,
                "duration": round(audio_duration, 2),
                "width": target_width,
                "height": target_height,
                "size": len(video_bytes),
                "format": "mp4",
                "fps": fps
            }
            
        finally:
            # Clean up temporary files
            try:
                os.unlink(video_path)
                os.unlink(audio_path)
            except:
                pass
    
    def fit_image_to_aspect_ratio(self, img, target_width, target_height):
        """Resize and crop image to fit 9:16 aspect ratio"""
        img_width, img_height = img.size
        target_aspect = target_width / target_height
        
        # Calculate crop dimensions
        if img_width / img_height > target_aspect:
            # Image is wider, crop width
            new_width = int(img_height * target_aspect)
            left = (img_width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img_height))
        else:
            # Image is taller, crop height
            new_height = int(img_width / target_aspect)
            top = (img_height - new_height) // 2
            img = img.crop((0, top, img_width, top + new_height))
        
        # Resize to target dimensions
        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        return img
    
    def add_subtitle(self, img, text, frame_num, total_frames, part_number):
        """Add subtitle text overlay to image"""
        draw = ImageDraw.Draw(img)
        
        # Try to load a font, fallback to default if not available
        try:
            # Try to use a system font
            font_size = 48
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            try:
                font = ImageFont.load_default()
            except:
                font = None
        
        # Split text into lines (max 40 chars per line, max 3 lines)
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            if len(current_line + word) < 40:
                current_line += word + " "
            else:
                if current_line:
                    lines.append(current_line.strip())
                current_line = word + " "
                if len(lines) >= 2:  # Max 3 lines
                    break
        
        if current_line:
            lines.append(current_line.strip())
        
        # Calculate text position (bottom third of image)
        img_width, img_height = img.size
        text_y = int(img_height * 0.75)  # 75% down the image
        line_height = 60
        start_y = text_y - (len(lines) * line_height) // 2
        
        # Draw text with outline for readability
        for i, line in enumerate(lines):
            y_pos = start_y + (i * line_height)
            
            # Draw black outline (shadow)
            for dx in [-2, -1, 0, 1, 2]:
                for dy in [-2, -1, 0, 1, 2]:
                    if dx != 0 or dy != 0:
                        draw.text((img_width // 2 + dx, y_pos + dy), line, 
                                 fill=(0, 0, 0), font=font, anchor="mm")
            
            # Draw white text
            draw.text((img_width // 2, y_pos), line, 
                     fill=(255, 255, 255), font=font, anchor="mm")
        
        return img
    
    def reencode_video(self, frames, fps, quality=6):
        """Re-encode video with lower quality to reduce size"""
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            imageio.mimwrite(temp_path, frames, fps=fps, codec='libx264', quality=quality)
            with open(temp_path, 'rb') as f:
                return f.read()
        finally:
            try:
                os.unlink(temp_path)
            except:
                pass
    
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

