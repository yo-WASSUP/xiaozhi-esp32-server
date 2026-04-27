import asyncio
import os
import ssl as ssl_module
from typing import Optional
from aiohttp import web
from config.logger import setup_logging
from core.api.ota_handler import OTAHandler
from core.api.vision_handler import VisionHandler
from core.api.hospice import register_hospice_routes

TAG = __name__


def _disable_loop_sendfile(logger):
    """禁用事件循环的 sendfile 优化路径，强迫 aiohttp 用自己干净的分块 read+write。

    背景：HTTPS 下 asyncio 的 sendfile 会退到 _sendfile_fallback —— 该路径在
    Windows + SSL + 客户端中途 RST 时存在 bug：清理时 transport 已置 None，
    `transport.resume_reading()` 抛 AttributeError；伴随 OSError WinError 64。
    aiohttp 把这一坨当作 "Unhandled exception" 用 traceback.print_exc() 直接打到日志。

    解法：直接让 loop.sendfile 抛 NotImplementedError。aiohttp 的 _sendfile()
    内部 catch 它后会走自己的纯异步分块路径（边读边写），无 sendfile 调用，
    异常路径干净，客户端断开时也只产生预期的 ConnectionResetError 并被正常处理。
    """
    loop = asyncio.get_event_loop()

    async def _no_sendfile(*args, **kwargs):
        raise NotImplementedError("sendfile disabled (HTTPS race-bug workaround)")

    loop.sendfile = _no_sendfile
    logger.bind(tag=TAG).info("已禁用 loop.sendfile（绕开 asyncio+SSL+sendfile 的清理 bug）")


def _build_ssl_context(tls_cfg: dict, xiaozhi_root: str, logger) -> Optional[ssl_module.SSLContext]:
    """根据 server.tls 配置构建 SSL 上下文；失败返回 None（服务会回退到 HTTP）。

    支持相对路径（相对 main/xiaozhi-server/）和绝对路径。
    """
    if not tls_cfg:
        return None
    cert_file = tls_cfg.get("cert_file")
    key_file = tls_cfg.get("key_file")
    if not cert_file or not key_file:
        return None

    def resolve(p):
        return p if os.path.isabs(p) else os.path.join(xiaozhi_root, p)

    cert_path = resolve(cert_file)
    key_path = resolve(key_file)

    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        logger.bind(tag=TAG).warning(
            f"TLS 证书文件缺失，回退到 HTTP。cert={cert_path}, key={key_path}"
        )
        return None

    try:
        ctx = ssl_module.create_default_context(ssl_module.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(cert_path, key_path)
        logger.bind(tag=TAG).info(f"TLS 证书已加载: {cert_path}")
        return ctx
    except Exception as e:
        logger.bind(tag=TAG).error(f"加载 TLS 证书失败，回退到 HTTP: {e}")
        return None


class SimpleHttpServer:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging()
        self.ota_handler = OTAHandler(config)
        self.vision_handler = VisionHandler(config)

    def _get_websocket_url(self, local_ip: str, port: int) -> str:
        """获取websocket地址

        Args:
            local_ip: 本地IP地址
            port: 端口号

        Returns:
            str: websocket地址
        """
        server_config = self.config["server"]
        websocket_config = server_config.get("websocket")

        if websocket_config and "你" not in websocket_config:
            return websocket_config
        else:
            return f"ws://{local_ip}:{port}/xiaozhi/v1/"

    async def start(self):
        try:
            server_config = self.config["server"]
            read_config_from_api = self.config.get("read_config_from_api", False)
            host = server_config.get("ip", "0.0.0.0")
            port = int(server_config.get("http_port", 8003))

            if port:
                # 可选 TLS：若配置了 server.tls.cert_file / key_file，整个 aiohttp 走 HTTPS
                xiaozhi_root = os.path.dirname(os.path.dirname(__file__))
                ssl_context = _build_ssl_context(
                    server_config.get("tls") or {}, xiaozhi_root, self.logger
                )
                scheme = "https" if ssl_context else "http"
                # 启用 SSL 后必装：禁用 loop.sendfile 强迫 aiohttp 走自己的分块路径，
                # 绕开 asyncio + SSL 在客户端中途 RST 时的清理 bug
                if ssl_context:
                    _disable_loop_sendfile(self.logger)

                app = web.Application()

                if not read_config_from_api:
                    # 如果没有开启智控台，只是单模块运行，就需要再添加简单OTA接口，用于下发websocket接口
                    app.add_routes(
                        [
                            web.get("/xiaozhi/ota/", self.ota_handler.handle_get),
                            web.post("/xiaozhi/ota/", self.ota_handler.handle_post),
                            web.options(
                                "/xiaozhi/ota/", self.ota_handler.handle_options
                            ),
                            # 下载接口，仅提供 data/bin/*.bin 下载
                            web.get(
                                "/xiaozhi/ota/download/{filename}",
                                self.ota_handler.handle_download,
                            ),
                            web.options(
                                "/xiaozhi/ota/download/{filename}",
                                self.ota_handler.handle_options,
                            ),
                        ]
                    )
                # 添加路由
                app.add_routes(
                    [
                        web.get("/mcp/vision/explain", self.vision_handler.handle_get),
                        web.post(
                            "/mcp/vision/explain", self.vision_handler.handle_post
                        ),
                        web.options(
                            "/mcp/vision/explain", self.vision_handler.handle_options
                        ),
                    ]
                )

                # 注册安宁疗护 API 路由
                register_hospice_routes(app, self.config)

                # 静态文件服务：患者端和家属端 PWA
                apps_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "apps")
                from core.utils.util import get_local_ip
                local_ip = get_local_ip()
                if os.path.exists(os.path.join(apps_dir, "patient")):
                    app.router.add_static("/patient/", os.path.join(apps_dir, "patient"), show_index=True)
                    self.logger.bind(tag=TAG).info(f"患者端 PWA:\t{scheme}://{local_ip}:{port}/patient/index.html")
                if os.path.exists(os.path.join(apps_dir, "family")):
                    app.router.add_static("/family/", os.path.join(apps_dir, "family"), show_index=True)
                    self.logger.bind(tag=TAG).info(f"家属端面板:\t{scheme}://{local_ip}:{port}/family/index.html")
                if os.path.exists(os.path.join(apps_dir, "shared")):
                    app.router.add_static("/shared/", os.path.join(apps_dir, "shared"), show_index=False)

                # 将 test 目录作为静态资源暴露，供患者端复用其 WebSocket/音频模块
                test_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test")
                if os.path.exists(test_dir):
                    app.router.add_static("/test-assets/", test_dir, show_index=False)

                # 家属消息上传的媒体文件（语音/图片）
                media_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "hospice_media")
                os.makedirs(media_dir, exist_ok=True)
                app.router.add_static("/hospice-media/", media_dir, show_index=False)

                # 运行服务（可选 SSL）
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, host, port, ssl_context=ssl_context)
                await site.start()

                # 保持服务运行
                while True:
                    await asyncio.sleep(3600)  # 每隔 1 小时检查一次
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"HTTP服务器启动失败: {e}")
            import traceback

            self.logger.bind(tag=TAG).error(f"错误堆栈: {traceback.format_exc()}")
            raise
