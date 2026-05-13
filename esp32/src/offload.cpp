#include "offload.h"
#include <math.h>

OffloadDecider::OffloadDecider()
    : window_count_(0)
    , window_index_(0)
    , last_upload_time_(0)
    , has_uploaded_(false)
{
    memset(window_, 0, sizeof(window_));
}

Decision OffloadDecider::decide(size_t current_size, unsigned long now) {
    Decision d;
    d.current_size = current_size;

    // 计算滑动窗口平均大小（用当前窗口内的历史帧，不含当前帧）
    float sum = 0;
    for (int i = 0; i < window_count_; i++) {
        sum += window_[i];
    }
    d.avg_size = (window_count_ > 0) ? (sum / window_count_) : 0.0f;
    d.window_ready = (window_count_ >= SIZE_WINDOW);

    // 计算相对变化率
    if (d.avg_size > 0.0f) {
        d.diff_ratio = fabs((float)current_size - d.avg_size) / d.avg_size;
    } else {
        d.diff_ratio = 0.0f;
    }

    // 判断冷却
    d.in_cooldown = has_uploaded_ && ((now - last_upload_time_) < COOLDOWN_MS);

    // 原始条件（冷却未纳入）
    d.by_diff = d.window_ready
                && d.avg_size >= MIN_AVG_SIZE
                && d.diff_ratio > DIFF_THRESHOLD_RATIO;

    d.by_interval = has_uploaded_
                    && ((now - last_upload_time_) >= FORCE_UPLOAD_INTERVAL_MS);

    // 优先决策
    if (!has_uploaded_) {
        d.should_upload = true;
        d.reason = "first";
    } else if (d.by_diff && !d.in_cooldown) {
        d.should_upload = true;
        d.reason = "diff";
    } else if (d.by_interval) {
        d.should_upload = true;
        d.reason = "interval";
    } else {
        d.should_upload = false;
        d.reason = "none";
    }

    // 最后把当前帧加入滑动窗口
    window_[window_index_] = current_size;
    window_index_ = (window_index_ + 1) % SIZE_WINDOW;
    if (window_count_ < SIZE_WINDOW) {
        window_count_++;
    }

    return d;
}

void OffloadDecider::mark_uploaded(unsigned long now) {
    last_upload_time_ = now;
    has_uploaded_ = true;
}

void OffloadDecider::reset() {
    memset(window_, 0, sizeof(window_));
    window_count_ = 0;
    window_index_ = 0;
    last_upload_time_ = 0;
    has_uploaded_ = false;
}
