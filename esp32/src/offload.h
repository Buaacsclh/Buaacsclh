#ifndef OFFLOAD_H
#define OFFLOAD_H

#include <Arduino.h>

/**
 * @brief 计算卸载决策器
 *
 * 采用 JPEG 文件大小差分法判断场景是否变化。
 * 连续两帧 JPEG 大小差异超过阈值则判定场景变化，需要上传。
 */
class OffloadDecider {
public:
    /**
     * @param threshold 变化率阈值，默认 0.15
     */
    explicit OffloadDecider(float threshold = 0.15f);

    /**
     * @brief 判断当前帧是否需要上传
     * @param current_size 当前帧 JPEG 大小（字节）
     * @return true 需要上传（场景变化），false 跳过
     * @note 首帧直接返回 true
     */
    bool should_upload(size_t current_size);

    /**
     * @brief 重置状态（清空历史记录）
     */
    void reset();

private:
    float threshold_;
    size_t prev_size_;
    bool has_prev_;
};

#endif
