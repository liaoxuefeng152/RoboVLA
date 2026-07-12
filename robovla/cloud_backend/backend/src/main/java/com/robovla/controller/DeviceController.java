package com.robovla.controller;

import com.robovla.service.DeviceService;
import com.robovla.service.ReportService;
import com.robovla.service.LicenseService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 设备管理接口
 */
@Slf4j
@RestController
@RequestMapping("/api/device")
@RequiredArgsConstructor
public class DeviceController {

    private final DeviceService deviceService;
    private final LicenseService licenseService;

    /**
     * 设备30s心跳上报
     */
    @PostMapping("/heartbeat")
    public ResponseEntity<?> heartbeat(@RequestBody Map<String, Object> body) {
        String sn = (String) body.get("hardware_sn");
        int production = (int) body.getOrDefault("total_production", 0);
        int faults = (int) body.getOrDefault("fault_count", 0);
        deviceService.heartbeat(sn, production, faults);
        return ResponseEntity.ok(Map.of("status", "ok"));
    }

    /**
     * 设备注册 + 授权
     */
    @PostMapping("/register")
    public ResponseEntity<?> register(@RequestBody Map<String, String> body) {
        String sn = body.get("hardware_sn");
        String type = body.getOrDefault("auth_type", "trial");
        String code = licenseService.generateLicenseCode(sn);
        var device = deviceService.register(sn, code, type);
        return ResponseEntity.ok(Map.of(
            "license_code", code,
            "hardware_sn", sn,
            "status", "registered"
        ));
    }

    /**
     * 设备集群监控摘要
     */
    @GetMapping("/cluster")
    public ResponseEntity<?> cluster() {
        return ResponseEntity.ok(deviceService.getClusterSummary());
    }

    /**
     * 到期提醒
     */
    @GetMapping("/expiring")
    public ResponseEntity<?> expiring(@RequestParam(defaultValue = "7") int days) {
        return ResponseEntity.ok(deviceService.getExpiringDevices(days));
    }
}

/**
 * 报表接口
 */
@Slf4j
@RestController
@RequestMapping("/api/report")
@RequiredArgsConstructor
class ReportController {

    private final ReportService reportService;

    @GetMapping("/daily")
    public ResponseEntity<?> daily(@RequestParam String date) {
        return ResponseEntity.ok(reportService.dailyReport(date));
    }

    @GetMapping("/utilization")
    public ResponseEntity<?> utilization(@RequestParam String deviceSn,
                                          @RequestParam String startDate,
                                          @RequestParam String endDate) {
        return ResponseEntity.ok(reportService.utilizationRate(deviceSn, startDate, endDate));
    }

    @GetMapping("/export")
    public ResponseEntity<?> export(@RequestParam String startDate,
                                     @RequestParam String endDate) {
        try {
            String path = reportService.exportExcel(startDate, endDate);
            return ResponseEntity.ok(Map.of("file", path, "status", "ok"));
        } catch (Exception e) {
            return ResponseEntity.internalServerError().body(Map.of("error", e.getMessage()));
        }
    }
}

/**
 * 远程运维接口
 */
@Slf4j
@RestController
@RequestMapping("/api/remote")
@RequiredArgsConstructor
class RemoteController {

    private final LicenseService licenseService;

    /**
     * 请求远程运维(需客户二次授权)
     */
    @PostMapping("/request")
    public ResponseEntity<?> requestAccess(@RequestBody Map<String, String> body) {
        String sn = body.get("hardware_sn");
        return ResponseEntity.ok(licenseService.requestRemoteAccess(sn));
    }
}

/**
 * 版本更新接口
 */
@Slf4j
@RestController
@RequestMapping("/api/version")
@RequiredArgsConstructor
class VersionController {

    @GetMapping("/latest")
    public ResponseEntity<?> latest() {
        return ResponseEntity.ok(Map.of(
            "version", "2.0.0",
            "release_date", "2025-06-01",
            "changelog", "V2.0 正式版本: 完整VLA推理、模仿学习、离线LLM、云端SaaS",
            "download_url", "/api/version/download/v2.0.0"
        ));
    }

    @GetMapping("/check")
    public ResponseEntity<?> check(@RequestParam String currentVersion) {
        String latestVersion = "2.0.0";
        boolean needUpdate = !latestVersion.equals(currentVersion);
        return ResponseEntity.ok(Map.of(
            "need_update", needUpdate,
            "current", currentVersion,
            "latest", latestVersion
        ));
    }
}
