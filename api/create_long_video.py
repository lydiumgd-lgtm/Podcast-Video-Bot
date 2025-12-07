from http.server import BaseHTTPRequestHandler
import json
import base64
import io
import sys
import os
import tempfile
import imageio

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Read JSON body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Validate input
            if "video_files" not in data:
                self.send_error_response(400, "Missing 'video_files' field in request")
                return
            
            video_files = data["video_files"]  # Array of {video: base64, duration, ...}
            
            if not isinstance(video_files, list) or len(video_files) == 0:
                self.send_error_response(400, "video_files must be a non-empty array")
                return
            
            print(f"Creating long-form video from {len(video_files)} parts", file=sys.stderr)
            
            try:
                # Create long video by concatenating all parts
                video_data = self.concatenate_videos(video_files)
                
                response_data = {
                    "video": video_data["video"],
                    "duration": video_data["duration"],
                    "width": video_data["width"],
                    "height": video_data["height"],
                    "size": video_data["size"],
                    "format": video_data["format"],
                    "total_parts": len(video_files)
                }
                
                self.send_success_response(response_data)
                
            except Exception as e:
                print(f"Video concatenation failed: {str(e)}", file=sys.stderr)
                # Return error but with helpful message
                raise Exception(f"Video concatenation failed: {str(e)}. Note: FFmpeg is required for video concatenation. This may not work on Vercel free tier.")
            
        except json.JSONDecodeError as e:
            self.send_error_response(400, f"Invalid JSON: {str(e)}")
        except Exception as e:
            self.send_error_response(500, f"Unexpected error: {str(e)}")
    
    def concatenate_videos(self, video_files):
        """
        Concatenate multiple video files into one long video.
        Note: This requires FFmpeg which may not be available on Vercel.
        """
        # Decode all videos
        video_paths = []
        temp_files = []
        
        try:
            for i, video_data in enumerate(video_files):
                video_bytes = base64.b64decode(video_data["video"])
                
                # Save to temporary file
                temp_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
                temp_file.write(video_bytes)
                temp_file.close()
                
                video_paths.append(temp_file.name)
                temp_files.append(temp_file.name)
            
            # Create output file
            output_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
            output_path = output_file.name
            output_file.close()
            
            # Concatenate videos using imageio (requires FFmpeg)
            # Note: This is a simplified approach - in production you'd use FFmpeg directly
            try:
                # Read all video frames
                all_frames = []
                fps = 30  # Assume 30 fps
                total_duration = 0
                width, height = 1080, 1920
                
                for video_path in video_paths:
                    try:
                        # Read video frames
                        reader = imageio.get_reader(video_path, fps=fps)
                        for frame in reader:
                            all_frames.append(frame)
                        reader.close()
                        
                        # Estimate duration (frames / fps)
                        # We'll use the duration from the video_data if available
                        pass
                    except Exception as e:
                        print(f"Error reading video {video_path}: {str(e)}", file=sys.stderr)
                        # Continue with other videos
                        continue
                
                # Calculate total duration
                total_duration = sum(vf.get("duration", 0) for vf in video_files)
                
                # Write concatenated video
                if all_frames:
                    imageio.mimwrite(output_path, all_frames, fps=fps, codec='libx264', quality=8)
                else:
                    raise Exception("No frames to write")
                
                # Read final video
                with open(output_path, 'rb') as f:
                    final_video_bytes = f.read()
                
                # Optimize if too large
                if len(final_video_bytes) > 10 * 1024 * 1024:  # 10MB
                    # Re-encode with lower quality
                    print("Video too large, re-encoding with lower quality...", file=sys.stderr)
                    imageio.mimwrite(output_path, all_frames, fps=fps, codec='libx264', quality=6)
                    with open(output_path, 'rb') as f:
                        final_video_bytes = f.read()
                
                # Convert to base64
                video_base64 = base64.b64encode(final_video_bytes).decode('utf-8')
                
                return {
                    "video": video_base64,
                    "duration": round(total_duration, 2),
                    "width": width,
                    "height": height,
                    "size": len(final_video_bytes),
                    "format": "mp4"
                }
                
            except Exception as e:
                # FFmpeg not available or other error
                raise Exception(f"Video concatenation requires FFmpeg: {str(e)}")
            
        finally:
            # Clean up temporary files
            for temp_file in temp_files + [output_path]:
                try:
                    os.unlink(temp_file)
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

