#include <Arduino.h>
#include "config.h"
#include "camera.h"
#include "offload.h"
#include "network.h"
#include "display.h"

static OffloadDecider decider(OFFLOAD_THRESHOLD);
static unsigned long lastUploadTime = 0;

void setup() {
    Serial.begin(115200);
    Serial.println("\n=============================");
    Serial.println("  智能眼镜人脸识别系统 - ESP32");
    Serial.println("=============================\n");

    // 初始化显示
    if (!display_init()) {
        Serial.println("[MAIN] 显示初始化失败，继续运行");
    }

    // 初始化摄像头
    display_show_status("初始化摄像头...");
    if (!camera_init(CAMERA_FRAME_SIZE, CAMERA_JPEG_QUALITY)) {
        display_show_error("摄像头初始化失败");
        while (true) {
            delay(1000);
        }
    }

    // 连接 WiFi
    display_show_status("连接 WiFi...");
    if (!wifi_init()) {
        display_show_error("WiFi 连接失败");
        while (true) {
            delay(1000);
        }
    }

    display_show_status("系统就绪");
}

void loop() {
    // 检查 WiFi 连接
    if (!wifi_is_connected()) {
        display_show_status("WiFi 断开，重连中...");
        if (!wifi_reconnect()) {
            delay(2000);
            return;
        }
    }

    // 拍照（用于判断）
    camera_fb_t* fb = camera_capture();
    if (fb == nullptr) {
        display_show_error("拍照失败");
        delay(500);
        return;
    }

    Serial.printf("[MAIN] 当前帧大小: %u bytes\n", fb->len);

    // 卸载决策
    bool scene_changed = decider.should_upload(fb->len);

    // 冷却检查
    unsigned long now = millis();
    bool cooldown_ok = (now - lastUploadTime) > UPLOAD_COOLDOWN_MS;

    if (scene_changed && cooldown_ok) {
        Serial.printf("[MAIN] 场景变化，触发上传\n");
        Serial.printf("[MAIN] 冷却检查: 距上次上传 %lu ms > %d ms，允许上传\n",
                      now - lastUploadTime, UPLOAD_COOLDOWN_MS);

        // 释放判断帧
        camera_release(fb);

        // 等待画面稳定
        Serial.printf("[MAIN] 释放判断帧，等待稳定 %d ms...\n", STABLE_DELAY_MS);
        display_show_status("等待画面稳定...");
        delay(STABLE_DELAY_MS);

        // 连拍候选帧
        camera_fb_t* candidates[BURST_COUNT];
        int best_index = 0;
        size_t best_size = 0;

        for (int i = 0; i < BURST_COUNT; i++) {
            candidates[i] = camera_capture();
            if (candidates[i] != nullptr) {
                Serial.printf("[MAIN] 连拍候选帧 %d/%d: %u bytes\n",
                              i + 1, BURST_COUNT, candidates[i]->len);

                // 选择最大的作为最佳帧
                if (candidates[i]->len > best_size) {
                    best_size = candidates[i]->len;
                    best_index = i;
                }
            } else {
                Serial.printf("[MAIN] 连拍候选帧 %d/%d: 拍照失败\n",
                              i + 1, BURST_COUNT);
                candidates[i] = nullptr;
            }

            // 连拍间隔（最后一张不需要等待）
            if (i < BURST_COUNT - 1) {
                delay(BURST_INTERVAL_MS);
            }
        }

        // 上传最佳帧
        if (candidates[best_index] != nullptr) {
            Serial.printf("[MAIN] 选择最佳帧: %u bytes (帧 %d/%d)\n",
                          best_size, best_index + 1, BURST_COUNT);
            Serial.printf("[MAIN] 上传最佳帧...\n");
            display_show_status("上传最佳帧...");

            RecognitionResult result = send_image(
                candidates[best_index]->buf,
                candidates[best_index]->len
            );

            if (result.status == "ok") {
                Serial.printf("[MAIN] 上传结果: ok, %s, %.2f\n",
                              result.name.c_str(), result.confidence);
                display_show_result(result.name, result.confidence);
            } else if (result.status == "no_face") {
                Serial.printf("[MAIN] 上传结果: no_face\n");
                display_show_status("未检测到人脸");
            } else {
                Serial.printf("[MAIN] 上传结果: %s\n", result.status.c_str());
                display_show_error("识别失败: " + result.status);
            }

            // 记录上传时间
            lastUploadTime = millis();
            Serial.printf("[MAIN] 进入冷却期 %d ms\n", UPLOAD_COOLDOWN_MS);
        }

        // 释放所有候选帧
        for (int i = 0; i < BURST_COUNT; i++) {
            if (candidates[i] != nullptr) {
                camera_release(candidates[i]);
            }
        }

    } else {
        // 不需要上传或在冷却期
        if (scene_changed && !cooldown_ok) {
            Serial.printf("[MAIN] 场景变化，但在冷却期，跳过上传\n");
        }

        // 释放判断帧
        camera_release(fb);
    }

    delay(LOOP_INTERVAL_MS);
}
