#include <Arduino.h>
#include "config.h"
#include "camera.h"
#include "offload.h"
#include "network.h"
#include "display.h"

static OffloadDecider decider;

void setup() {
    Serial.begin(115200);
    Serial.println("\n=============================");
    Serial.println("  智能眼镜人脸识别系统 - ESP32");
    Serial.println("=============================\n");

    if (!display_init()) {
        Serial.println("[MAIN] 显示初始化失败，继续运行");
    }

    display_show_status("初始化摄像头...");
    if (!camera_init(CAMERA_FRAME_SIZE, CAMERA_JPEG_QUALITY)) {
        display_show_error("摄像头初始化失败");
        while (true) {
            delay(1000);
        }
    }

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
    // WiFi 保活
    if (!wifi_is_connected()) {
        display_show_status("WiFi 断开，重连中...");
        if (!wifi_reconnect()) {
            delay(2000);
            return;
        }
    }

    // 拍照（判断帧，仅用于读取 fb->len）
    camera_fb_t* judge_fb = camera_capture();
    if (judge_fb == nullptr) {
        display_show_error("拍照失败");
        delay(500);
        return;
    }

    unsigned long now = millis();
    Decision d = decider.decide(judge_fb->len, now);

    // 每轮串口日志
    Serial.printf("[LOOP] currentSize=%u avgSize=%.1f diffRatio=%.4f "
                  "windowReady=%d byDiff=%d byInterval=%d inCooldown=%d "
                  "shouldUpload=%d reason=%s\n",
                  d.current_size, d.avg_size, d.diff_ratio,
                  d.window_ready, d.by_diff, d.by_interval, d.in_cooldown,
                  d.should_upload, d.reason);

    if (d.should_upload) {
        // 释放判断帧（不上传触发帧）
        camera_release(judge_fb);
        Serial.printf("[MAIN] 触发上传，reason=%s，释放判断帧\n", d.reason);

        // 等待画面稳定
        display_show_status("等待画面稳定...");
        delay(STABLE_DELAY_MS);

        // 重新采集稳定帧用于上传
        camera_fb_t* stable_fb = camera_capture();
        if (stable_fb == nullptr) {
            Serial.println("[MAIN] 稳定帧采集失败，跳过本次上传");
            delay(LOOP_INTERVAL_MS);
            return;
        }

        Serial.printf("[MAIN] 上传稳定帧 (size=%u bytes, reason=%s)\n",
                      stable_fb->len, d.reason);
        display_show_status("上传中...");

        unsigned long upload_start = millis();
        RecognitionResult result = send_image(
            stable_fb->buf, stable_fb->len, d.reason
        );
        unsigned long upload_cost = millis() - upload_start;

        bool upload_ok = (result.status != "error");
        Serial.printf("[MAIN] 上传完成: status=%s reason=%s stableSize=%u costMs=%lu\n",
                      result.status.c_str(), d.reason, stable_fb->len, upload_cost);

        if (upload_ok) {
            decider.mark_uploaded(millis());

            if (result.status == "ok") {
                Serial.printf("[MAIN] 识别结果: ok, %s, %.2f\n",
                              result.name.c_str(), result.confidence);
                display_show_result(result.name, result.confidence);
            } else if (result.status == "no_face") {
                Serial.println("[MAIN] 识别结果: no_face");
                display_show_status("未检测到人脸");
            }
        } else {
            Serial.println("[MAIN] HTTP 上传或解析失败，不计入上传记录");
            display_show_error("上传失败");
        }

        camera_release(stable_fb);
    } else {
        // 无需上传，直接释放判断帧
        camera_release(judge_fb);
    }

    delay(LOOP_INTERVAL_MS);
}
