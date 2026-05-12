#ifndef CONFIG_H
#define CONFIG_H

// WiFi 配置 —— 修改为你自己的 WiFi 信息
#define WIFI_SSID       "wananbuaa"
#define WIFI_PASSWORD   "clh520lzq"
#define WIFI_TIMEOUT_MS 10000

// 服务器配置
#define SERVER_HOST     "192.168.3.5"
#define SERVER_PORT     8000
#define SERVER_URL      "/api/recognize"
#define HTTP_TIMEOUT_MS 5000

// 摄像头配置
#define CAMERA_FRAME_SIZE   FRAMESIZE_VGA   // 640x480
#define CAMERA_JPEG_QUALITY 12              // 0-63，越小质量越高

// 卸载决策算法阈值
#define OFFLOAD_THRESHOLD   0.15f

// OLED 配置（预留）
#define OLED_I2C_ADDRESS    0x3C
#define OLED_SDA_PIN        14
#define OLED_SCL_PIN        15
#define OLED_WIDTH          128
#define OLED_HEIGHT         64

// 主循环间隔（毫秒）
#define LOOP_INTERVAL_MS    100

#endif
