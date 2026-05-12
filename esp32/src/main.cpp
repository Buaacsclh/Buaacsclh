#include <Arduino.h>
#include "config.h"
#include "camera.h"
#include "offload.h"
#include "network.h"
#include "display.h"

static OffloadDecider decider(OFFLOAD_THRESHOLD);

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

    // 拍照
    camera_fb_t* fb = camera_capture();
    if (fb == nullptr) {
        display_show_error("拍照失败");
        delay(500);
        return;
    }

    // 卸载决策
    bool should_send = decider.should_upload(fb->len);

    if (should_send) {
        display_show_status("上传图片...");

        RecognitionResult result = send_image(fb->buf, fb->len);

        if (result.status == "ok") {
            display_show_result(result.name, result.confidence);
        } else if (result.status == "no_face") {
            display_show_status("未检测到人脸");
        } else {
            display_show_error("识别失败: " + result.status);
        }
    }

    // 释放 frame buffer
    camera_release(fb);

    delay(LOOP_INTERVAL_MS);
}
