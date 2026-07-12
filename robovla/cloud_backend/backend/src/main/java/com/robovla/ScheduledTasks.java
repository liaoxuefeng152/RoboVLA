package com.robovla;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Scheduled;
import com.robovla.service.DeviceService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 定时任务调度
 */
@Slf4j
@Configuration
@RequiredArgsConstructor
public class ScheduledTasks {

    private final DeviceService deviceService;

    /**
     * 每5分钟检查离线设备
     */
    @Scheduled(fixedRate = 300_000)
    public void checkOfflineDevices() {
        deviceService.checkOfflineDevices();
    }

    /**
     * 每天9:00推送到期提醒
     */
    @Scheduled(cron = "0 0 9 * * ?")
    public void pushExpirationReminders() {
        var devices = deviceService.getExpiringDevices(7);
        if (!devices.isEmpty()) {
            log.warn("到期提醒: {} 台设备即将到期", devices.size());
            // 实际生产环境: 发送邮件/短信通知
        }
    }
}
