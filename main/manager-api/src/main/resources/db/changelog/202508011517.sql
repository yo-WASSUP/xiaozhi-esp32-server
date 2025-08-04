-- ===============================
-- 添加ROS2机器人控制插件
-- ===============================
START TRANSACTION;

-- 添加ROS2机器人控制插件
INSERT INTO ai_model_provider (id, model_type, provider_code, name, fields,
                               sort, creator, create_date, updater, update_date)
VALUES ('SYSTEM_PLUGIN_ROS2_ROBOT_CONTROL',
        'Plugin',
        'ros2_robot_move',
        'ROS2机器人控制',
        JSON_ARRAY(),
        80, 0, NOW(), 0, NOW());

COMMIT;