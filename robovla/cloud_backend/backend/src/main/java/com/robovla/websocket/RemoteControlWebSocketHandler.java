package com.robovla.websocket;

import com.robovla.entity.Device;
import com.robovla.service.DeviceService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.*;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * WebSocket 远程控制通道
 * 客户需二次弹窗授权后，建立安全远程调试连接
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RemoteControlWebSocketHandler extends TextWebSocketHandler {

    private final DeviceService deviceService;

    /** deviceSn -> WebSocketSession 映射 */
    private static final Map<String, WebSocketSession> CLIENTS = new ConcurrentHashMap<>();

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        String deviceSn = getDeviceSn(session);
        if (deviceSn == null) {
            reject(session, "Missing device-sn parameter");
            return;
        }

        // 校验设备是否存在且在线
        Device device = deviceService.findBySn(deviceSn);
        if (device == null || !"ONLINE".equals(device.getOnlineStatus())) {
            reject(session, "Device not found or offline");
            return;
        }

        CLIENTS.put(deviceSn, session);
        log.info("WebSocket connected: device={}", deviceSn);
        sendJson(session, Map.of("type", "connected", "device", deviceSn));
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        String deviceSn = getDeviceSn(session);
        String payload = message.getPayload();
        log.info("WS msg from {}: {}", deviceSn, payload);

        // 在此处理远程控制指令:
        // - 查询设备状态
        // - 远程重启/关机
        // - 参数修改下发
        // - 日志拉取

        try {
            // 回显确认 (实际应转发到边缘设备MQTT通道)
            sendJson(session, Map.of(
                "type", "ack",
                "device", deviceSn,
                "status", "received"
            ));
        } catch (IOException e) {
            log.error("WS send error: {}", e.getMessage());
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        String deviceSn = getDeviceSn(session);
        if (deviceSn != null) {
            CLIENTS.remove(deviceSn);
            log.info("WebSocket disconnected: device={}, status={}", deviceSn, status);
        }
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable e) {
        log.error("WebSocket transport error: {}", e.getMessage());
        String deviceSn = getDeviceSn(session);
        if (deviceSn != null) CLIENTS.remove(deviceSn);
    }

    /** 向指定设备发送消息 */
    public boolean sendToDevice(String deviceSn, String json) {
        WebSocketSession session = CLIENTS.get(deviceSn);
        if (session == null || !session.isOpen()) return false;
        try {
            session.sendMessage(new TextMessage(json));
            return true;
        } catch (IOException e) {
            log.error("Send to device {} failed: {}", deviceSn, e.getMessage());
            return false;
        }
    }

    /** 获取在线设备数 */
    public int onlineDeviceCount() {
        return CLIENTS.size();
    }

    // --- 私有方法 ---

    private String getDeviceSn(WebSocketSession session) {
        String query = session.getUri() != null ? session.getUri().getQuery() : "";
        if (query == null || query.isEmpty()) return null;
        for (String param : query.split("&")) {
            String[] kv = param.split("=", 2);
            if (kv.length == 2 && "device-sn".equals(kv[0])) {
                return kv[1];
            }
        }
        return null;
    }

    private void reject(WebSocketSession session, String reason) {
        try {
            session.close(new CloseStatus(4000, reason));
        } catch (IOException ignored) {}
    }

    private void sendJson(WebSocketSession session, Map<String, Object> data) throws IOException {
        String json = new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(data);
        session.sendMessage(new TextMessage(json));
    }
}
