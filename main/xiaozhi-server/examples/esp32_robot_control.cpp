/*
ESP32机器人运动控制示例代码
需要添加到ESP32固件中以支持机器人运动控制
*/

#include <ArduinoJson.h>
#include <WebSocketsClient.h>

// 机器人运动控制引脚定义
#define MOTOR_LEFT_FORWARD    2
#define MOTOR_LEFT_BACKWARD   4
#define MOTOR_RIGHT_FORWARD   16
#define MOTOR_RIGHT_BACKWARD  17
#define MOTOR_LEFT_PWM        5
#define MOTOR_RIGHT_PWM       18

// 机器人状态变量
struct RobotStatus {
    bool isMoving = false;
    String currentDirection = "stop";
    int currentSpeed = 0;
    unsigned long moveStartTime = 0;
    unsigned long moveDuration = 0;
};

RobotStatus robotStatus;

// 初始化机器人控制引脚
void initRobotControl() {
    pinMode(MOTOR_LEFT_FORWARD, OUTPUT);
    pinMode(MOTOR_LEFT_BACKWARD, OUTPUT);
    pinMode(MOTOR_RIGHT_FORWARD, OUTPUT);
    pinMode(MOTOR_RIGHT_BACKWARD, OUTPUT);
    pinMode(MOTOR_LEFT_PWM, OUTPUT);
    pinMode(MOTOR_RIGHT_PWM, OUTPUT);
    
    // 设置PWM频率
    ledcSetup(0, 5000, 8); // 左电机PWM通道
    ledcSetup(1, 5000, 8); // 右电机PWM通道
    ledcAttachPin(MOTOR_LEFT_PWM, 0);
    ledcAttachPin(MOTOR_RIGHT_PWM, 1);
    
    stopRobot();
    Serial.println("机器人控制系统已初始化");
}

// 停止机器人
void stopRobot() {
    digitalWrite(MOTOR_LEFT_FORWARD, LOW);
    digitalWrite(MOTOR_LEFT_BACKWARD, LOW);
    digitalWrite(MOTOR_RIGHT_FORWARD, LOW);
    digitalWrite(MOTOR_RIGHT_BACKWARD, LOW);
    ledcWrite(0, 0);
    ledcWrite(1, 0);
    
    robotStatus.isMoving = false;
    robotStatus.currentDirection = "stop";
    robotStatus.currentSpeed = 0;
}

// 机器人前进
void moveForward(int speed) {
    digitalWrite(MOTOR_LEFT_FORWARD, HIGH);
    digitalWrite(MOTOR_LEFT_BACKWARD, LOW);
    digitalWrite(MOTOR_RIGHT_FORWARD, HIGH);
    digitalWrite(MOTOR_RIGHT_BACKWARD, LOW);
    
    int pwmValue = map(speed, 0, 100, 0, 255);
    ledcWrite(0, pwmValue);
    ledcWrite(1, pwmValue);
    
    robotStatus.currentDirection = "forward";
    robotStatus.currentSpeed = speed;
    Serial.printf("机器人前进，速度: %d%%\n", speed);
}

// 机器人后退
void moveBackward(int speed) {
    digitalWrite(MOTOR_LEFT_FORWARD, LOW);
    digitalWrite(MOTOR_LEFT_BACKWARD, HIGH);
    digitalWrite(MOTOR_RIGHT_FORWARD, LOW);
    digitalWrite(MOTOR_RIGHT_BACKWARD, HIGH);
    
    int pwmValue = map(speed, 0, 100, 0, 255);
    ledcWrite(0, pwmValue);
    ledcWrite(1, pwmValue);
    
    robotStatus.currentDirection = "backward";
    robotStatus.currentSpeed = speed;
    Serial.printf("机器人后退，速度: %d%%\n", speed);
}

// 机器人左转
void turnLeft(int speed) {
    digitalWrite(MOTOR_LEFT_FORWARD, LOW);
    digitalWrite(MOTOR_LEFT_BACKWARD, HIGH);
    digitalWrite(MOTOR_RIGHT_FORWARD, HIGH);
    digitalWrite(MOTOR_RIGHT_BACKWARD, LOW);
    
    int pwmValue = map(speed, 0, 100, 0, 255);
    ledcWrite(0, pwmValue);
    ledcWrite(1, pwmValue);
    
    robotStatus.currentDirection = "left";
    robotStatus.currentSpeed = speed;
    Serial.printf("机器人左转，速度: %d%%\n", speed);
}

// 机器人右转
void turnRight(int speed) {
    digitalWrite(MOTOR_LEFT_FORWARD, HIGH);
    digitalWrite(MOTOR_LEFT_BACKWARD, LOW);
    digitalWrite(MOTOR_RIGHT_FORWARD, LOW);
    digitalWrite(MOTOR_RIGHT_BACKWARD, HIGH);
    
    int pwmValue = map(speed, 0, 100, 0, 255);
    ledcWrite(0, pwmValue);
    ledcWrite(1, pwmValue);
    
    robotStatus.currentDirection = "right";
    robotStatus.currentSpeed = speed;
    Serial.printf("机器人右转，速度: %d%%\n", speed);
}

// 执行机器人运动
void executeRobotMove(String direction, float duration, int speed) {
    robotStatus.isMoving = true;
    robotStatus.moveStartTime = millis();
    robotStatus.moveDuration = duration * 1000; // 转换为毫秒
    
    if (direction == "forward") {
        moveForward(speed);
    } else if (direction == "backward") {
        moveBackward(speed);
    } else if (direction == "left") {
        turnLeft(speed);
    } else if (direction == "right") {
        turnRight(speed);
    } else if (direction == "stop") {
        stopRobot();
        return;
    }
    
    Serial.printf("开始执行运动: %s, 持续时间: %.1f秒, 速度: %d%%\n", 
                  direction.c_str(), duration, speed);
}

// 检查运动是否完成
void checkRobotMovement() {
    if (robotStatus.isMoving && robotStatus.moveDuration > 0) {
        unsigned long elapsed = millis() - robotStatus.moveStartTime;
        if (elapsed >= robotStatus.moveDuration) {
            stopRobot();
            Serial.println("运动完成，机器人停止");
        }
    }
}

// 处理机器人控制命令
void handleRobotControlMessage(DynamicJsonDocument& doc) {
    if (!doc.containsKey("command")) {
        Serial.println("机器人控制消息格式错误：缺少command字段");
        return;
    }
    
    JsonObject command = doc["command"];
    String action = command["action"].as<String>();
    
    if (action == "move") {
        // 单次运动控制
        String direction = command["direction"].as<String>();
        float duration = command["duration"].as<float>();
        int speed = command["speed"].as<int>();
        
        executeRobotMove(direction, duration, speed);
        
    } else if (action == "sequence") {
        // 序列运动控制
        JsonArray sequence = command["sequence"];
        int speed = command["speed"].as<int>();
        
        Serial.println("开始执行运动序列：");
        for (JsonObject step : sequence) {
            String direction = step["direction"].as<String>();
            float duration = step["duration"].as<float>();
            
            Serial.printf("  - %s: %.1f秒\n", direction.c_str(), duration);
            executeRobotMove(direction, duration, speed);
            
            // 等待当前动作完成
            while (robotStatus.isMoving) {
                checkRobotMovement();
                delay(10);
            }
            
            delay(100); // 动作间隔
        }
        
    } else if (action == "get_status") {
        // 状态查询
        DynamicJsonDocument statusDoc(512);
        statusDoc["type"] = "robot_status";
        statusDoc["data"]["isMoving"] = robotStatus.isMoving;
        statusDoc["data"]["direction"] = robotStatus.currentDirection;
        statusDoc["data"]["speed"] = robotStatus.currentSpeed;
        statusDoc["data"]["battery"] = getBatteryLevel(); // 需要实现电池电量获取
        
        String statusMessage;
        serializeJson(statusDoc, statusMessage);
        
        // 发送状态到服务器
        webSocket.sendTXT(statusMessage);
        Serial.println("机器人状态已发送");
    }
}

// 获取电池电量（示例实现）
int getBatteryLevel() {
    // 这里应该读取实际的电池电量
    // 示例：通过ADC读取电池电压
    int adcValue = analogRead(A0);
    int batteryLevel = map(adcValue, 0, 4095, 0, 100);
    return constrain(batteryLevel, 0, 100);
}

// WebSocket消息处理函数（添加到现有的消息处理中）
void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
    switch(type) {
        case WStype_TEXT: {
            String message = String((char*)payload);
            Serial.printf("收到消息: %s\n", message.c_str());
            
            DynamicJsonDocument doc(1024);
            DeserializationError error = deserializeJson(doc, message);
            
            if (error) {
                Serial.println("JSON解析失败");
                return;
            }
            
            String messageType = doc["type"].as<String>();
            
            if (messageType == "robot_control") {
                handleRobotControlMessage(doc);
            }
            // 处理其他消息类型...
            
            break;
        }
        // 处理其他WebSocket事件...
    }
}

// 在主循环中调用
void loop() {
    webSocket.loop();
    
    // 检查机器人运动状态
    checkRobotMovement();
    
    // 其他循环逻辑...
    delay(10);
}