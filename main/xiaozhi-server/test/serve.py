#!/usr/bin/env python3
"""修复 MIME type 的 HTTP 服务器"""
import http.server
import socketserver
import os
import signal
import sys

PORT = 8006

# Windows 下支持 Ctrl+C
signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))


class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # 禁用缓存
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isfile(path):
            # 根据扩展名强制设置 Content-Type
            ext = os.path.splitext(path)[1].lower()
            content_types = {
                '.js': 'application/javascript',
                '.mjs': 'application/javascript',
                '.json': 'application/json',
                '.wasm': 'application/wasm',
                '.html': 'text/html',
                '.css': 'text/css',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.svg': 'image/svg+xml',
                '.woff2': 'font/woff2',
                '.woff': 'font/woff',
            }
            ctype = content_types.get(ext)
            if ctype:
                f = open(path, 'rb')
                fs = os.fstat(f.fileno())
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(fs.st_size))
                self.end_headers()
                return f
        return super().send_head()


with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
    print(f"服务器启动: http://localhost:{PORT}/test_page.html")
    print("按 Ctrl+C 停止")
    httpd.serve_forever()
