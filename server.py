#!/usr/bin/env python3
"""
Home Assistant Dashboard Server
Serves the dashboard and proxies API requests to Home Assistant
"""

import http.server
import socketserver
import urllib.request
import urllib.error
import urllib.parse
import ssl
import json
import os

# Import configuration from config.py
try:
    from config import HA_URL, HA_TOKEN, PORT
except ImportError:
    print("ERROR: config.py not found!")
    print("Copy config.example.py to config.py and update with your values")
    exit(1)

# Create SSL context that doesn't verify certificates (for self-signed certs)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/local/'):
            self.handle_local_request()
        elif self.path.startswith('/api/synology/'):
            self.proxy_synology_request()
        elif self.path.startswith('/api/'):
            self.proxy_request('GET')
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/api/'):
            self.proxy_request('POST')
        else:
            self.send_error(405, "Method Not Allowed")

    def proxy_request(self, method):
        try:
            # Read request body for POST
            body = None
            if method == 'POST':
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)

            # Build request to Home Assistant
            url = f"{HA_URL}{self.path}"
            req = urllib.request.Request(url, data=body, method=method)
            req.add_header('Authorization', f'Bearer {HA_TOKEN}')
            req.add_header('Content-Type', 'application/json')

            # Make request
            with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
                data = response.read()

                # Send response
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)

        except urllib.error.HTTPError as e:
            self.send_error(e.code, str(e.reason))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_local_request(self):
        """Handle local folder photo requests"""
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            folder_path = params.get('path', [''])[0]

            if '/api/local/photos' in self.path:
                # List photos in folder
                if not folder_path or not os.path.isdir(folder_path):
                    self.send_json_response({'success': False, 'error': 'Folder not found'})
                    return

                # Supported image extensions
                image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
                photos = []

                try:
                    for entry in os.scandir(folder_path):
                        if entry.is_file():
                            ext = os.path.splitext(entry.name)[1].lower()
                            if ext in image_extensions:
                                stat = entry.stat()
                                photos.append({
                                    'name': entry.name,
                                    'path': entry.path,
                                    'mtime': stat.st_mtime,
                                    'size': stat.st_size
                                })
                except PermissionError:
                    self.send_json_response({'success': False, 'error': 'Permission denied'})
                    return

                # Sort by modification time (newest first)
                photos.sort(key=lambda x: x['mtime'], reverse=True)

                self.send_json_response({'success': True, 'photos': photos})

            elif '/api/local/image' in self.path:
                # Serve image file
                image_path = params.get('path', [''])[0]

                if not image_path or not os.path.isfile(image_path):
                    self.send_error(404, "Image not found")
                    return

                # Validate path is under allowed directories (security)
                real_path = os.path.realpath(image_path)

                # Determine content type
                ext = os.path.splitext(image_path)[1].lower()
                content_types = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp',
                    '.bmp': 'image/bmp'
                }
                content_type = content_types.get(ext, 'application/octet-stream')

                try:
                    with open(real_path, 'rb') as f:
                        data = f.read()

                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', len(data))
                    self.send_header('Cache-Control', 'public, max-age=86400')
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as e:
                    self.send_error(500, str(e))

            else:
                self.send_error(404, "Local endpoint not found")

        except Exception as e:
            print(f"Local request error: {e}")
            self.send_error(500, str(e))

    def send_json_response(self, data):
        """Helper to send JSON response"""
        response = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(response)

    def proxy_synology_request(self):
        """Proxy requests to Synology Photos API"""
        try:
            # Parse the request path and query parameters
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            base_url = params.get('baseUrl', [''])[0]
            passphrase = params.get('passphrase', [''])[0]

            if not base_url or not passphrase:
                self.send_error(400, "Missing baseUrl or passphrase")
                return

            if '/api/synology/photos' in self.path:
                # List photos from shared album
                api_url = f"{base_url}/webapi/entry.cgi"
                query_params = urllib.parse.urlencode({
                    'api': 'SYNO.Foto.Browse.Item',
                    'version': '1',
                    'method': 'list',
                    'passphrase': passphrase,
                    'additional': '["thumbnail","resolution","orientation","gps"]',
                    'offset': '0',
                    'limit': '500'
                })
                full_url = f"{api_url}?{query_params}"

                req = urllib.request.Request(full_url)
                with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
                    data = response.read()

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(data)

            elif '/api/synology/thumbnail' in self.path:
                # Get thumbnail/image
                photo_id = params.get('id', [''])[0]
                size = params.get('size', ['xl'])[0]

                if not photo_id:
                    self.send_error(400, "Missing photo id")
                    return

                # Synology thumbnail sizes: sm, m, xl
                api_url = f"{base_url}/webapi/entry.cgi"
                query_params = urllib.parse.urlencode({
                    'api': 'SYNO.Foto.Thumbnail',
                    'version': '2',
                    'method': 'get',
                    'id': photo_id,
                    'cache_key': photo_id,
                    'size': size,
                    'passphrase': passphrase
                })
                full_url = f"{api_url}?{query_params}"

                req = urllib.request.Request(full_url)
                with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
                    data = response.read()
                    content_type = response.headers.get('Content-Type', 'image/jpeg')

                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cache-Control', 'public, max-age=86400')
                    self.end_headers()
                    self.wfile.write(data)

            else:
                self.send_error(404, "Synology endpoint not found")

        except urllib.error.HTTPError as e:
            self.send_error(e.code, str(e.reason))
        except Exception as e:
            print(f"Synology proxy error: {e}")
            self.send_error(500, str(e))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    with socketserver.TCPServer(("", PORT), ProxyHandler) as httpd:
        print(f"Dashboard server running at http://localhost:{PORT}/index.html")
        print(f"Proxying API requests to {HA_URL}")
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")


if __name__ == "__main__":
    main()
