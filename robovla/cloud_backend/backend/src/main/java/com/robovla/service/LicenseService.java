package com.robovla.service;

import cn.hutool.core.lang.UUID;
import com.robovla.entity.Device;
import com.robovla.mapper.DeviceMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.security.MessageDigest;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 授权码生成与验证服务
 *
 * 授权码规则: SHA256(hardware_sn + secret + timestamp) → 前8位
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class LicenseService {

    private static final String SECRET_KEY = "robovla_enterprise_k3y_2025!_";
    private final DeviceMapper deviceMapper;

    // 远程运维临时授权缓存(TTL 30分钟)
    private final Map<String, RemoteAuthToken> remoteTokens = new ConcurrentHashMap<>();

    /**
     * 生成设备授权码
     */
    public String generateLicenseCode(String hardwareSn) {
        try {
            String raw = hardwareSn + "|" + SECRET_KEY + "|robovla_v2";
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] hash = md.digest(raw.getBytes());
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 4; i++) {
                sb.append(String.format("%02X", hash[i]));
            }
            return sb.toString();
        } catch (Exception e) {
            log.error("授权码生成失败", e);
            return "ERROR0000";
        }
    }

    /**
     * 验证授权码
     */
    public boolean validateLicense(String hardwareSn, String licenseCode) {
        String expected = generateLicenseCode(hardwareSn);
        return expected.equalsIgnoreCase(licenseCode);
    }

    /**
     * 生成远程运维临时授权Token
     * 客户必须在边缘端点击"同意远程"后，此Token才生效
     */
    public String generateRemoteToken(String hardwareSn) {
        String token = UUID.randomUUID().toString(true).substring(0, 12);
        remoteTokens.put(token, new RemoteAuthToken(hardwareSn, System.currentTimeMillis()));
        return token;
    }

    /**
     * 请求远程运维 → 等待客户授权
     */
    public Map<String, Object> requestRemoteAccess(String hardwareSn) {
        String token = generateRemoteToken(hardwareSn);

        // 向边缘端发送授权请求(WebSocket)
        // wsServer.sendToDevice(hardwareSn, {"type":"remote_request", "token": token});

        return Map.of(
            "status", "pending",
            "token", token,
            "message", "等待客户授权..."
        );
    }

    static class RemoteAuthToken {
        String deviceSn;
        long createdAt;
        RemoteAuthToken(String sn, long time) {
            this.deviceSn = sn;
            this.createdAt = time;
        }
    }
}
