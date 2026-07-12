package com.robovla.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("device")
public class Device {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long tenantId;
    private String deviceSn;
    private String deviceName;
    private String robotBrand;
    private String robotModel;
    private String softwareVer;
    private String authCode;
    private String authType;
    private LocalDateTime authExpireAt;
    private String onlineStatus;
    private LocalDateTime lastHeartbeat;
    private String ipAddress;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}

@Data
@TableName("license_order")
class LicenseOrder {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String customerName;
    private String contactPhone;
    private String hardwareSn;
    private String authType;
    private Double amount;
    private String status;
    private LocalDateTime startDate;
    private LocalDateTime endDate;
    private LocalDateTime createdAt;
}

@Data
@TableName("cloud_user")
class SysUser {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long tenantId;
    private String username;
    private String passwordHash;
    private String role;
    private String realName;
    private String phone;
    private String status;
    private LocalDateTime lastLoginAt;
    private LocalDateTime createdAt;
}
