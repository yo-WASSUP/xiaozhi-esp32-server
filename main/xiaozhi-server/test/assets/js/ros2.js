// ROS2命令检测和执行模块

// ROS2消息累积
let ros2MessageBuffer = '';
let ros2MessageTimer = null;

// 添加消息到ROS2缓冲区
function addToMessageBuffer(text) {
    ros2MessageBuffer += text + '\n';

    // 清除之前的定时器
    if (ros2MessageTimer) {
        clearTimeout(ros2MessageTimer);
    }

    // 设置定时器，在消息接收完成后检查ROS2命令
    ros2MessageTimer = setTimeout(() => {
        utils.log(`检查累积的消息: ${ros2MessageBuffer}`, 'debug');
        checkAndExecuteROS2Command(ros2MessageBuffer);
        ros2MessageBuffer = ''; // 清空缓冲区
    }, 1000); // 1秒后处理
}

// ROS2命令检测和执行函数
function checkAndExecuteROS2Command(text) {
    utils.log(`检查文本中的ROS2命令: ${text.substring(0, 100)}...`, 'debug');
    
    // 更宽松的正则表达式匹配，支持JSON格式的参数
    const ros2CommandRegex = /ros2\s+topic\s+pub\s+--once\s+[^\s]+\s+[^\s]+\s+'[^']*\{[^}]*\}[^']*'/gs;
    let matches = text.match(ros2CommandRegex);
    
    if (matches) {
        matches.forEach(command => {
            utils.log(`🎯 检测到完整ROS2命令: ${command}`, 'success');
            displayROS2Command(command.trim());
        });
        return;
    }
    
    // 如果没有匹配到完整命令，尝试逐行检查
    if (text.includes('ros2 topic pub') || text.includes('/cmd_vel')) {
        utils.log(`🔍 检测到ROS2相关内容，尝试提取命令...`, 'info');
        
        // 尝试匹配单行完整命令
        const singleLineRegex = /ros2\s+topic\s+pub\s+--once\s+[^\s]+\s+[^\s]+\s+'[^']*'/g;
        const singleLineMatches = text.match(singleLineRegex);
        if (singleLineMatches) {
            singleLineMatches.forEach(command => {
                utils.log(`🚀 检测到单行ROS2命令: ${command}`, 'success');
                displayROS2Command(command.trim());
            });
            return;
        }
        
        const lines = text.split(/[\r\n]+/);
        let commandParts = [];
        let inCommand = false;
        
        for (let line of lines) {
            line = line.trim();
            if (line.startsWith('ros2 topic pub')) {
                commandParts = [line];
                inCommand = true;
            } else if (inCommand && line) {
                commandParts.push(line);
                // 如果这行包含JSON格式的参数，说明命令完整了
                if (line.includes('{') && line.includes('}')) {
                    const fullCommand = commandParts.join(' ');
                    utils.log(`🚀 提取到完整ROS2命令: ${fullCommand}`, 'success');
                    displayROS2Command(fullCommand);
                    return;
                }
            }
        }
        
        // 如果还是没有找到完整命令，尝试简单合并
        if (commandParts.length > 0) {
            const fullCommand = commandParts.join(' ');
            if (fullCommand.includes('/cmd_vel') && fullCommand.includes('{')) {
                utils.log(`🔧 合并后的ROS2命令: ${fullCommand}`, 'info');
                displayROS2Command(fullCommand);
            } else {
                utils.log(`⚠️ ROS2命令不完整: ${fullCommand}`, 'warning');
            }
        }
    }
}

// 显示ROS2命令并尝试自动执行
function displayROS2Command(command) {
    try {
        utils.log(`处理ROS2命令: ${command}`, 'info');

        // 自动执行命令
        executeROS2CommandAuto(command);

        // 在会话区域显示ROS2命令
        const conversationDiv = document.getElementById('conversation');
        if (conversationDiv) {
            const commandDiv = document.createElement('div');
            commandDiv.className = 'message server';
            commandDiv.innerHTML = `
                <div style="margin-bottom: 10px;">
                    <strong style="color: #2196F3;">🤖 ROS2机器人控制命令:</strong>
                </div>
                <div style="font-family: monospace; background-color: #f0f0f0; padding: 10px; border-radius: 5px; margin: 5px 0; font-size: 12px; word-break: break-all;">
                    ${command}
                </div>
                <div style="margin-top: 10px;">
                    <button onclick="executeROS2CommandAuto('${command.replace(/'/g, "\\'")}')" 
                            style="background-color: #4CAF50; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer; margin-right: 5px;">
                        执行命令
                    </button>
                    <button onclick="copyROS2Command('${command.replace(/'/g, "\\'")}')" 
                            style="background-color: #2196F3; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer;">
                        复制命令
                    </button>
                </div>
            `;
            
            conversationDiv.appendChild(commandDiv);
            conversationDiv.scrollTop = conversationDiv.scrollHeight;
        }

    } catch (error) {
        utils.log(`显示ROS2命令时出错: ${error.message}`, 'error');
    }
}

// 自动执行ROS2命令
async function executeROS2CommandAuto(command) {
    const ROS2_EXECUTOR_URL = 'http://localhost:3001';
    
    try {
        utils.log(`尝试自动执行ROS2命令: ${command}`, 'info');
        
        // 检查ROS2执行服务是否可用
        const response = await fetch(`${ROS2_EXECUTOR_URL}/execute`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                command: command
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const result = await response.json();
        
        if (result.success) {
            utils.log(`ROS2命令执行成功: ${result.output}`, 'success');
            window.ui.addMessage(`✅ ROS2命令执行成功`);
        } else {
            utils.log(`ROS2命令执行失败: ${result.error}`, 'error');
            window.ui.addMessage(`❌ ROS2命令执行失败: ${result.error}`);
        }
        
    } catch (error) {
        utils.log(`自动执行失败，请确保ROS2执行服务已启动 (http://localhost:3001): ${error.message}`, 'warning');
        window.ui.addMessage(`⚠️ 无法连接到ROS2执行服务，请手动执行命令`);
        
        // 显示服务启动提示
        showROS2ServiceTip();
    }
}

// 显示ROS2服务启动提示
function showROS2ServiceTip() {
    const tipExists = document.getElementById('ros2-service-tip');
    if (tipExists) return;

    const tip = document.createElement('div');
    tip.id = 'ros2-service-tip';
    tip.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 5px;
        padding: 15px;
        max-width: 400px;
        z-index: 1000;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    `;
    
    tip.innerHTML = `
        <strong>💡 启动ROS2执行服务以支持自动执行:</strong>
        <pre style="background-color: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 3px; font-size: 12px;">cd /path/to/ros2_server
npm start</pre>
        <button onclick="this.parentElement.remove()" style="float: right; background: none; border: none; font-size: 16px; cursor: pointer;">×</button>
    `;
    
    document.body.appendChild(tip);
    
    // 10秒后自动隐藏
    setTimeout(() => {
        if (tip.parentElement) {
            tip.remove();
        }
    }, 10000);
}

// 复制ROS2命令到剪贴板
function copyROS2Command(command) {
    navigator.clipboard.writeText(command).then(() => {
        utils.log('ROS2命令已复制到剪贴板', 'success');
    }).catch(err => {
        utils.log('复制失败: ' + err.message, 'error');
    });
}

// 导出到全局
window.ros2 = {
    addToMessageBuffer,
    checkAndExecuteROS2Command,
    displayROS2Command,
    executeROS2CommandAuto,
    copyROS2Command,
    showROS2ServiceTip
};

// 将函数也添加到全局作用域，以便HTML中的onclick可以访问
window.executeROS2CommandAuto = executeROS2CommandAuto;
window.copyROS2Command = copyROS2Command;