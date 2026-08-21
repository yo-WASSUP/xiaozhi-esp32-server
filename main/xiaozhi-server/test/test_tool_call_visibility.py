import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
WEBSOCKET_HANDLER = SERVER_ROOT / "test/js/core/network/websocket.js"


@unittest.skipUnless(shutil.which("node"), "node is required for browser handler replay")
class ToolCallVisibilityTests(unittest.TestCase):
    def test_tool_trace_is_hidden_from_chat_while_final_llm_reply_is_visible(self):
        harness = textwrap.dedent(
            r"""
            const fs = require('fs');
            const vm = require('vm');

            const file = process.argv[1];
            let source = fs.readFileSync(file, 'utf8')
                .replace(/^import .*;\s*$/gm, '')
                .replace('export class WebSocketHandler', 'class WebSocketHandler')
                .replace('export function getWebSocketHandler', 'function getWebSocketHandler');
            source += '\nglobalThis.WebSocketHandler = WebSocketHandler;';

            const logs = [];
            const context = {
                console,
                log: (message, level) => logs.push({ message, level }),
                uiController: { startAIChatSession() {} },
                getConfig: () => ({}),
                saveConnectionUrls() {},
                getAudioPlayer: () => ({}),
                getAudioRecorder: () => ({}),
                executeMcpTool() {},
                getMcpTools: () => [],
                setMcpWebSocket() {},
                webSocketConnect() {},
                window: { dispatchEvent() {}, chatApp: null },
                CustomEvent: function CustomEvent() {},
                setTimeout,
                clearTimeout,
                JSON,
            };
            vm.runInNewContext(source, context, { filename: file });

            const rendered = [];
            const handler = new context.WebSocketHandler();
            handler.onChatMessage = (text, isUser) => rendered.push({ text, isUser });

            handler.handleTextMessage({
                type: 'tool_call',
                function: 'get_weather',
                arguments: '{"location":"成都"}',
                result: '完整天气原始结果',
            });
            handler.handleTextMessage({
                type: 'llm',
                state: 'complete',
                text: '今天成都多云，晚上有雨。',
            });

            const toolTraceLogged = logs.some(
                item => item.message.startsWith('[Tool] get_weather(')
            );
            if (
                rendered.length !== 1
                || rendered[0].text !== '今天成都多云，晚上有雨。'
                || !toolTraceLogged
            ) {
                console.error(JSON.stringify({ rendered, logs }, null, 2));
                process.exit(1);
            }
            """
        )

        result = subprocess.run(
            ["node", "-e", harness, str(WEBSOCKET_HANDLER)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
