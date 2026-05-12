#include "network.h"
#include "config.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

bool wifi_init() {
    Serial.printf("[WIFI] 连接 %s ...\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start > WIFI_TIMEOUT_MS) {
            Serial.println("[WIFI] 连接超时");
            return false;
        }
        delay(500);
        Serial.print(".");
    }

    Serial.printf("\n[WIFI] 已连接，IP: %s\n", WiFi.localIP().toString().c_str());
    return true;
}

bool wifi_is_connected() {
    return WiFi.status() == WL_CONNECTED;
}

bool wifi_reconnect() {
    Serial.println("[WIFI] 尝试重连...");
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start > WIFI_TIMEOUT_MS) {
            Serial.println("[WIFI] 重连失败");
            return false;
        }
        delay(500);
    }

    Serial.printf("[WIFI] 重连成功，IP: %s\n", WiFi.localIP().toString().c_str());
    return true;
}

RecognitionResult send_image(const uint8_t* jpeg_buf, size_t jpeg_len) {
    RecognitionResult result;
    result.status = "error";
    result.name = "";
    result.confidence = 0.0f;

    if (!wifi_is_connected()) {
        Serial.println("[HTTP] WiFi 未连接");
        return result;
    }

    String url = String("http://") + SERVER_HOST + ":" + SERVER_PORT + SERVER_URL;

    WiFiClient client;
    HTTPClient http;
    http.begin(client, url);
    http.setTimeout(HTTP_TIMEOUT_MS);

    // 构建 multipart/form-data boundary
    String boundary = "----ESP32Boundary" + String(millis());

    // 构建请求体头部
    String head = "--" + boundary + "\r\n"
                  "Content-Disposition: form-data; name=\"image\"; filename=\"capture.jpg\"\r\n"
                  "Content-Type: image/jpeg\r\n\r\n";

    String tail = "\r\n--" + boundary + "--\r\n";

    // 计算总长度
    size_t total_len = head.length() + jpeg_len + tail.length();

    http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);

    // 分段发送：head + jpeg + tail
    // 使用 WiFiClient 手动发送以避免大缓冲区
    uint8_t* body_buf = (uint8_t*)ps_malloc(head.length() + tail.length());
    if (body_buf == nullptr) {
        Serial.println("[HTTP] 内存分配失败");
        http.end();
        return result;
    }

    memcpy(body_buf, head.c_str(), head.length());
    memcpy(body_buf + head.length(), tail.c_str(), tail.length());

    // 用 HTTPClient 的 send 方法手动构建
    // 更简单的方式：直接用 WiFiClient 发送原始 HTTP 请求
    http.end();

    if (!client.connect(SERVER_HOST, SERVER_PORT)) {
        Serial.println("[HTTP] 连接服务器失败");
        free(body_buf);
        return result;
    }

    // 发送 HTTP 请求头
    client.printf("POST %s HTTP/1.1\r\n", SERVER_URL);
    client.printf("Host: %s:%d\r\n", SERVER_HOST, SERVER_PORT);
    client.printf("Content-Type: multipart/form-data; boundary=%s\r\n", boundary.c_str());
    client.printf("Content-Length: %u\r\n", total_len);
    client.print("Connection: close\r\n\r\n");

    // 发送 multipart body
    client.print(head);
    client.write(jpeg_buf, jpeg_len);
    client.print(tail);

    free(body_buf);

    // 等待响应
    unsigned long timeout = millis();
    while (client.available() == 0) {
        if (millis() - timeout > HTTP_TIMEOUT_MS) {
            Serial.println("[HTTP] 响应超时");
            client.stop();
            return result;
        }
        delay(10);
    }

    // 读取响应（跳过 HTTP 头）
    String response;
    bool headers_done = false;
    while (client.available()) {
        String line = client.readStringUntil('\n');
        if (!headers_done) {
            if (line == "\r" || line.length() == 0) {
                headers_done = true;
            }
        } else {
            response += line;
        }
    }
    client.stop();

    // 解析 JSON 响应
    StaticJsonDocument<256> doc;
    DeserializationError err = deserializeJson(doc, response);
    if (err) {
        Serial.printf("[HTTP] JSON 解析失败: %s\n", err.c_str());
        Serial.printf("[HTTP] 原始响应: %s\n", response.c_str());
        return result;
    }

    result.status = doc["status"] | "error";
    result.name = doc["name"] | "";
    result.confidence = doc["confidence"] | 0.0f;

    Serial.printf("[HTTP] 识别结果: status=%s, name=%s, confidence=%.2f\n",
                  result.status.c_str(), result.name.c_str(), result.confidence);

    return result;
}
