#ifndef OFFLOAD_H
#define OFFLOAD_H

#include <Arduino.h>
#include "config.h"

/**
 * @brief 单次上传决策结果
 */
struct Decision {
    bool should_upload;     // 是否应当上传
    bool by_diff;           // 差分变化触发
    bool by_interval;       // 定时保底触发
    bool in_cooldown;       // 是否在冷却期
    bool window_ready;      // 滑动窗口是否已填满
    size_t current_size;    // 当前帧 JPEG 大小
    float avg_size;         // 滑动窗口平均 JPEG 大小
    float diff_ratio;       // 相对变化率
    const char* reason;     // "first" / "diff" / "interval" / "none"
};

/**
 * @brief 综合上传决策器
 *
 * 维护最近 SIZE_WINDOW 帧的 JPEG 大小滑动窗口，基于以下策略判断
 * 是否应当上传当前帧到边缘服务器：
 *   1. 首帧直接上传（冷启动）
 *   2. JPEG 大小滑动窗口差分触发（事件驱动）
 *   3. 定时保底刷新（时间驱动）
 *   4. 上传冷却控制（反馈抑制）
 *
 * 不解码像素数据，仅以 fb->len 作为零成本视觉变化代理信号。
 */
class OffloadDecider {
public:
    OffloadDecider();

    /**
     * @brief 传入当前帧大小，返回综合决策
     * @param current_size 当前帧 JPEG 大小（字节）
     * @param now          当前时间 millis()
     * @return Decision 决策结构体
     */
    Decision decide(size_t current_size, unsigned long now);

    /**
     * @brief 标记上传成功，更新 lastUploadTime 和 hasUploadedBefore
     * @param now 当前时间 millis()
     * @note 仅在 HTTP 上传成功后调用，失败不透传
     */
    void mark_uploaded(unsigned long now);

    /**
     * @brief 重置所有内部状态
     */
    void reset();

private:
    size_t window_[SIZE_WINDOW];
    int window_count_;
    int window_index_;
    unsigned long last_upload_time_;
    bool has_uploaded_;
};

#endif
