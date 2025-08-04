#!/usr/bin/env node
/**
 * ROS2命令执行服务
 * 在Ubuntu客户端运行：node ros2_executor.js
 */

const express = require('express');
const { exec } = require('child_process');
const cors = require('cors');

const app = express();
const PORT = 3001;

// 启用CORS和JSON解析
app.use(cors());
app.use(express.json());

// 执行ROS2命令的API端点
app.post('/execute', (req, res) => {
    const { command } = req.body;
    
    console.log(`收到ROS2命令: ${command}`);
    
    // 验证命令是否为ROS2命令
    if (!command || !command.startsWith('ros2 topic pub')) {
        return res.status(400).json({
            success: false,
            error: '只允许执行ROS2 topic pub命令'
        });
    }
    
    // 执行命令
    exec(command, { timeout: 10000 }, (error, stdout, stderr) => {
        if (error) {
            console.error(`命令执行失败: ${error.message}`);
            return res.json({
                success: false,
                error: error.message
            });
        }
        
        if (stderr) {
            console.warn(`命令警告: ${stderr}`);
        }
        
        console.log(`命令执行成功: ${stdout}`);
        res.json({
            success: true,
            output: stdout,
            warning: stderr
        });
    });
});

// 健康检查端点
app.get('/health', (req, res) => {
    res.json({ status: 'ok', message: 'ROS2执行服务运行正常' });
});

app.listen(PORT, () => {
    console.log(`🤖 ROS2命令执行服务已启动，监听端口 ${PORT}`);
    console.log(`健康检查: http://localhost:${PORT}/health`);
});