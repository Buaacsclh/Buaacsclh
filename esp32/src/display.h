#ifndef DISPLAY_H
#define DISPLAY_H

#include <Arduino.h>

/**
 * @brief 初始化显示模块
 * @return true 初始化成功
 * @note 当前实现仅使用串口输出，后续可扩展为 OLED
 */
bool display_init();

/**
 * @brief 显示识别结果
 * @param name 识别到的名字
 * @param confidence 置信度
 */
void display_show_result(const String& name, float confidence);

/**
 * @brief 显示状态信息
 * @param message 状态消息
 */
void display_show_status(const String& message);

/**
 * @brief 显示错误信息
 * @param message 错误消息
 */
void display_show_error(const String& message);

#endif
