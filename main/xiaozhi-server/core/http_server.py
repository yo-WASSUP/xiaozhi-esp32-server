import asyncio
import os
from aiohttp import web
from config.logger import setup_logging
from core.api.ota_handler import OTAHandler
from core.api.vision_handler import VisionHandler
from core.api.hospice import register_hospice_routes

TAG = __name__


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
                    self.logger.bind(tag=TAG).info(f"患者端 PWA:\thttp://{local_ip}:{port}/patient/index.html")
                if os.path.exists(os.path.join(apps_dir, "family")):
                    app.router.add_static("/family/", os.path.join(apps_dir, "family"), show_index=True)
                    self.logger.bind(tag=TAG).info(f"家属端面板:\thttp://{local_ip}:{port}/family/index.html")
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

                # 运行服务
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, host, port)
                await site.start()

                # 保持服务运行
                while True:
                    await asyncio.sleep(3600)  # 每隔 1 小时检查一次
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"HTTP服务器启动失败: {e}")
            import traceback

            self.logger.bind(tag=TAG).error(f"错误堆栈: {traceback.format_exc()}")
            raise
