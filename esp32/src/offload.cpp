#include "offload.h"
#include <math.h>

OffloadDecider::OffloadDecider(float threshold)
    : threshold_(threshold), prev_size_(0), has_prev_(false) {}

bool OffloadDecider::should_upload(size_t current_size) {
    if (!has_prev_) {
        prev_size_ = current_size;
        has_prev_ = true;
        Serial.printf("[OFFLOAD] 首帧，直接上传 (size=%u)\n", current_size);
        return true;
    }

    if (prev_size_ == 0) {
        prev_size_ = current_size;
        return true;
    }

    float delta = fabs((float)current_size - (float)prev_size_) / (float)prev_size_;
    prev_size_ = current_size;

    if (delta > threshold_) {
        Serial.printf("[OFFLOAD] 场景变化 Δ=%.2f > %.2f，上传 (size=%u)\n",
                      delta, threshold_, current_size);
        return true;
    }

    Serial.printf("[OFFLOAD] 场景无变化 Δ=%.2f <= %.2f，跳过\n", delta, threshold_);
    return false;
}

void OffloadDecider::reset() {
    prev_size_ = 0;
    has_prev_ = false;
}
