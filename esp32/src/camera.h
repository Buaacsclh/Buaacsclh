#ifndef CAMERA_H
#define CAMERA_H

#include <Arduino.h>
#include "esp_camera.h"

// AI Thinker ESP32-CAM 引脚定义
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

/**
 * @brief 初始化 OV2640 摄像头
 * @param frame_size 帧大小（FRAMESIZE_VGA 等）
 * @param jpeg_quality JPEG 质量（0-63，越小质量越高）
 * @return true 初始化成功，false 初始化失败
 */
bool camera_init(framesize_t frame_size, int jpeg_quality);

/**
 * @brief 拍照并获取 JPEG 图片
 * @param[out] out_len 输出 JPEG 数据长度
 * @return JPEG 数据指针，失败返回 nullptr
 * @note 调用方必须在使用完毕后调用 camera_release() 释放 buffer
 */
camera_fb_t* camera_capture();

/**
 * @brief 释放 frame buffer
 * @param fb 要释放的 frame buffer
 */
void camera_release(camera_fb_t* fb);

#endif
