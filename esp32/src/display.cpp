#include "display.h"
#include "config.h"

// OLED 预留：后续购买 SSD1306 后在此添加
// #include <Wire.h>
// #include <Adafruit_GFX.h>
// #include <Adafruit_SSD1306.h>
// static Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);

bool display_init() {
    Serial.println("[DISPLAY] 初始化成功（串口模式）");
    // OLED 预留：
    // Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
    // if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDRESS)) {
    //     Serial.println("[DISPLAY] OLED 初始化失败");
    //     return false;
    // }
    // display.clearDisplay();
    // display.setTextSize(1);
    // display.setTextColor(SSD1306_WHITE);
    // display.setCursor(0, 0);
    // display.println("Smart Glasses");
    // display.display();
    return true;
}

void display_show_result(const String& name, float confidence) {
    Serial.println("=== 识别结果 ===");
    Serial.printf("  姓名: %s\n", name.c_str());
    Serial.printf("  置信度: %.2f\n", confidence);
    Serial.println("================");

    // OLED 预留：
    // display.clearDisplay();
    // display.setCursor(0, 0);
    // display.setTextSize(2);
    // display.println(name);
    // display.setTextSize(1);
    // display.printf("Conf: %.2f", confidence);
    // display.display();
}

void display_show_status(const String& message) {
    Serial.printf("[STATUS] %s\n", message.c_str());

    // OLED 预留：
    // display.clearDisplay();
    // display.setCursor(0, 0);
    // display.setTextSize(1);
    // display.println(message);
    // display.display();
}

void display_show_error(const String& message) {
    Serial.printf("[ERROR] %s\n", message.c_str());

    // OLED 预留：
    // display.clearDisplay();
    // display.setCursor(0, 0);
    // display.setTextSize(1);
    // display.println("ERROR:");
    // display.println(message);
    // display.display();
}
