package com.robovla.service;

import cn.hutool.core.util.StrUtil;
import com.robovla.entity.Device;
import com.robovla.mapper.DeviceMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class DeviceService {

    private final DeviceMapper deviceMapper;

    /**
     * 设备心跳上报(30s周期)
     */
    public void heartbeat(String hardwareSn, int totalProduction, int faultCount) {
        Device device = deviceMapper.selectBySn(hardwareSn);
        if (device != null) {
            device.setLastHeartbeat(LocalDateTime.now());
            device.setStatus("online");
            device.setTotalProduction(totalProduction);
            device.setFaultCount(faultCount);
            deviceMapper.updateById(device);
        }
    }

    /**
     * 注册新设备
     */
    public Device register(String hardwareSn, String licenseCode, String authType) {
        Device device = new Device();
        device.setHardwareSn(hardwareSn);
        device.setLicenseCode(licenseCode);
        device.setAuthType(authType);
        device.setStatus("offline");
        device.setActivatedAt(LocalDateTime.now());

        if ("trial".equals(authType)) {
            device.setAuthExpire(LocalDateTime.now().plusDays(30));
        } else if ("annual".equals(authType)) {
            device.setAuthExpire(LocalDateTime.now().plusDays(365));
        }

        deviceMapper.insert(device);
        log.info("新设备注册: SN={}, type={}", hardwareSn, authType);
        return device;
    }

    /**
     * 设备集群监控摘要
     */
    public Map<String, Object> getClusterSummary() {
        List<Device> all = deviceMapper.selectList(null);
        long online = all.stream().filter(d -> "online".equals(d.getStatus())).count();
        long total = all.size();
        int totalProduction = all.stream().mapToInt(d -> d.getTotalProduction() != null ? d.getTotalProduction() : 0).sum();

        return Map.of(
            "totalDevices", total,
            "onlineDevices", online,
            "offlineDevices", total - online,
            "totalProduction", totalProduction,
            "onlineRate", total > 0 ? Math.round(online * 100.0 / total) : 0
        );
    }

    /**
     * 检查授权到期 → 告警
     */
    public List<Device> getExpiringDevices(int days) {
        LocalDateTime threshold = LocalDateTime.now().plusDays(days);
        return deviceMapper.selectList(null).stream()
            .filter(d -> d.getAuthExpire() != null && d.getAuthExpire().isBefore(threshold))
            .filter(d -> !"perpetual".equals(d.getAuthType()))
            .collect(Collectors.toList());
    }

    /**
     * 离线设备检测(5分钟无心跳)
     */
    public void checkOfflineDevices() {
        LocalDateTime threshold = LocalDateTime.now().minusMinutes(5);
        deviceMapper.selectList(null).stream()
            .filter(d -> "online".equals(d.getStatus()))
            .filter(d -> d.getLastHeartbeat() != null && d.getLastHeartbeat().isBefore(threshold))
            .forEach(d -> {
                d.setStatus("offline");
                deviceMapper.updateById(d);
                log.warn("设备离线: SN={}", d.getHardwareSn());
            });
    }
}
