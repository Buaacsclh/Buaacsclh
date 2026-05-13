#ifndef NETWORK_H
#define NETWORK_H

#include <Arduino.h>

/**
 * @brief 识别结果结构体
 */
struct RecognitionResult {
    String status;      // "ok", "no_face", "error"
    String name;        // 识别到的名字，未知时为 "未知"
    float confidence;   // 置信度 0.0-1.0
};

/**
 * @brief 初始化 WiFi 连接
 * @return true 连接成功，false 连接超时
 */
bool wifi_init();

/**
 * @brief 检查 WiFi 是否连接
 */
bool wifi_is_connected();

/**
 * @brief 尝试重连 WiFi
 * @return true 重连成功，false 重连失败
 */
bool wifi_reconnect();

/**
 * @brief 发送 JPEG 图片到服务器进行识别
 * @param jpeg_buf JPEG 数据指针
 * @param jpeg_len JPEG 数据长度
 * @return RecognitionResult 识别结果
 */
RecognitionResult send_image(const uint8_t* jpeg_buf, size_t jpeg_len,
                                const char* reason = "unknown");

#endif
