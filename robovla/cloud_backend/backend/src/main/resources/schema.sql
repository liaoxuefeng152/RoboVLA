-- ============================================================
-- RoboVLA V2.0 云端 SaaS MySQL 数据库初始化脚本
-- 版本: 2.0.0
-- 兼容: MySQL 8.0+
-- ============================================================

CREATE DATABASE IF NOT EXISTS robovla_cloud
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE robovla_cloud;

-- ------------------------------------------------------
-- 1. 客户/租户表
-- ------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_name     VARCHAR(128)  NOT NULL COMMENT '客户企业名称',
    contact_name    VARCHAR(64)   DEFAULT '' COMMENT '联系人',
    contact_phone   VARCHAR(32)   DEFAULT '' COMMENT '联系电话',
    address         VARCHAR(256)  DEFAULT '' COMMENT '工厂地址',
    plan_type       VARCHAR(32)   DEFAULT 'TRIAL' COMMENT '购买方案: TRIAL/BUYOUT/SUBSCRIPTION/RAAS',
    plan_expire_at  DATETIME      NULL COMMENT '方案到期时间',
    status          VARCHAR(16)   DEFAULT 'ACTIVE' COMMENT 'ACTIVE/FROZEN/EXPIRED',
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tenant_status (status)
) ENGINE=InnoDB COMMENT='客户/租户';

-- ------------------------------------------------------
-- 2. 用户账号表（三级权限）
-- ------------------------------------------------------
CREATE TABLE IF NOT EXISTS cloud_user (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id       BIGINT        NOT NULL COMMENT '所属租户',
    username        VARCHAR(64)   NOT NULL UNIQUE,
    password_hash   VARCHAR(256)  NOT NULL COMMENT 'SHA-256哈希',
    role            VARCHAR(16)   DEFAULT 'OPERATOR' COMMENT 'OPERATOR/ADMIN/MAINTENANCE',
    real_name       VARCHAR(64)   DEFAULT '',
    phone           VARCHAR(32)   DEFAULT '',
    status          VARCHAR(16)   DEFAULT 'ACTIVE',
    last_login_at   DATETIME      NULL,
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenant(id),
    INDEX idx_user_tenant (tenant_id),
    INDEX idx_user_role (role)
) ENGINE=InnoDB COMMENT='云端用户账号(三级权限)';

-- ------------------------------------------------------
-- 3. 边缘设备表
-- ------------------------------------------------------
CREATE TABLE IF NOT EXISTS device (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id       BIGINT        NOT NULL,
    device_sn       VARCHAR(128)  NOT NULL UNIQUE COMMENT 'Jetson硬件SN',
    device_name     VARCHAR(128)  DEFAULT 'RoboVLA-Device',
    robot_brand     VARCHAR(32)   DEFAULT '' COMMENT 'aubo/dobot/unitree',
    robot_model     VARCHAR(32)   DEFAULT '',
    software_ver    VARCHAR(32)   DEFAULT '2.0.0',
    auth_code       VARCHAR(256)  NOT NULL COMMENT 'SHA256授权码',
    auth_type       VARCHAR(16)   DEFAULT 'TRIAL' COMMENT 'TRIAL/BUYOUT/SUBSCRIPTION',
    auth_expire_at  DATETIME      NULL,
    online_status   VARCHAR(16)   DEFAULT 'OFFLINE' COMMENT 'ONLINE/OFFLINE/ERROR',
    last_heartbeat  DATETIME      NULL,
    ip_address      VARCHAR(45)   DEFAULT '',
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenant(id),
    INDEX idx_device_tenant (tenant_id),
    INDEX idx_device_sn (device_sn),
    INDEX idx_device_online (online_status)
) ENGINE=InnoDB COMMENT='边缘设备注册';

-- ------------------------------------------------------
-- 4. 生产日志表
-- ------------------------------------------------------
CREATE TABLE IF NOT EXISTS production_log (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id       BIGINT        NOT NULL,
    device_id       BIGINT        NOT NULL,
    task_name       VARCHAR(128)  DEFAULT '' COMMENT '任务/工序名称',
    cycle_count     INT           DEFAULT 0 COMMENT '完成周期数',
    success_count   INT           DEFAULT 0 COMMENT '成功次数',
    fail_count      INT           DEFAULT 0 COMMENT '失败次数',
    avg_cycle_ms    INT           DEFAULT 0 COMMENT '平均周期耗时(ms)',
    status          VARCHAR(16)   DEFAULT 'RUNNING' COMMENT 'RUNNING/PAUSED/STOPPED',
    reported_at     DATETIME      DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenant(id),
    FOREIGN KEY (device_id) REFERENCES device(id),
    INDEX idx_prod_device (device_id),
    INDEX idx_prod_time (reported_at)
) ENGINE=InnoDB COMMENT='生产日志(30s心跳上报)';

-- ------------------------------------------------------
-- 5. 故障日志表
-- ------------------------------------------------------
CREATE TABLE IF NOT EXISTS fault_log (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id       BIGINT        NOT NULL,
    device_id       BIGINT        NOT NULL,
    fault_code      VARCHAR(32)   NOT NULL COMMENT '故障码',
    fault_level     VARCHAR(16)   DEFAULT 'WARN' COMMENT 'INFO/WARN/ERROR/FATAL',
    fault_msg       TEXT          COMMENT '故障描述',
    resolved        TINYINT       DEFAULT 0 COMMENT '是否已解决',
    resolved_at     DATETIME      NULL,
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenant(id),
    FOREIGN KEY (device_id) REFERENCES device(id),
    INDEX idx_fault_device (device_id),
    INDEX idx_fault_time (created_at),
    INDEX idx_fault_resolved (resolved)
) ENGINE=InnoDB COMMENT='故障日志';

-- ------------------------------------------------------
-- 6. 授权记录表
-- ------------------------------------------------------
CREATE TABLE IF NOT EXISTS license_record (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id       BIGINT        NOT NULL,
    device_id       BIGINT        NOT NULL,
    auth_type       VARCHAR(16)   NOT NULL COMMENT 'TRIAL/ACTIVATE/RENEW/EXPIRE',
    auth_code       VARCHAR(256)  NOT NULL,
    operator_id     BIGINT        DEFAULT NULL COMMENT '操作人',
    remark          VARCHAR(256)  DEFAULT '',
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenant(id),
    FOREIGN KEY (device_id) REFERENCES device(id),
    INDEX idx_license_device (device_id)
) ENGINE=InnoDB COMMENT='授权操作记录';

-- ------------------------------------------------------
-- 7. OTA版本管理表
-- ------------------------------------------------------
CREATE TABLE IF NOT EXISTS ota_version (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    version_code    VARCHAR(32)   NOT NULL UNIQUE COMMENT '版本号如2.0.1',
    version_name    VARCHAR(64)   DEFAULT '',
    changelog       TEXT          COMMENT '更新日志',
    package_url     VARCHAR(512)  DEFAULT '' COMMENT '更新包下载地址',
    package_hash    VARCHAR(128)  DEFAULT '' COMMENT 'SHA256校验值',
    force_update    TINYINT       DEFAULT 0 COMMENT '是否强制更新',
    status          VARCHAR(16)   DEFAULT 'DRAFT' COMMENT 'DRAFT/PUBLISHED/DEPRECATED',
    published_at    DATETIME      NULL,
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ota_status (status)
) ENGINE=InnoDB COMMENT='OTA版本管理';

-- ------------------------------------------------------
-- 8. 设备OTA更新记录
-- ------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_ota_log (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    device_id       BIGINT        NOT NULL,
    from_version    VARCHAR(32)   DEFAULT '',
    to_version      VARCHAR(32)   DEFAULT '',
    update_status   VARCHAR(16)   DEFAULT 'PENDING' COMMENT 'PENDING/DOWNLOADING/UPDATING/SUCCESS/FAILED',
    error_msg       TEXT,
    started_at      DATETIME      NULL,
    finished_at     DATETIME      NULL,
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES device(id),
    INDEX idx_otalog_device (device_id)
) ENGINE=InnoDB COMMENT='设备OTA更新记录';

-- ------------------------------------------------------
-- 9. 操作日志表（审计留痕180天）
-- ------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id       BIGINT        NOT NULL,
    user_id         BIGINT        DEFAULT NULL,
    action          VARCHAR(64)   NOT NULL COMMENT '操作类型: LOGIN/LOGOUT/CREATE/DELETE/UPDATE/EXPORT',
    target_type     VARCHAR(32)   DEFAULT '' COMMENT '操作对象: DEVICE/TASK/USER/LICENSE',
    target_id       VARCHAR(64)   DEFAULT '',
    detail          TEXT          COMMENT '操作详情JSON',
    ip_address      VARCHAR(45)   DEFAULT '',
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_tenant (tenant_id),
    INDEX idx_audit_time (created_at)
) ENGINE=InnoDB COMMENT='操作审计日志(保留180天)';

-- ------------------------------------------------------
-- 初始管理员账号 (密码: admin123, 上线后必须修改)
-- ------------------------------------------------------
INSERT INTO tenant (id, tenant_name, plan_type, status) VALUES
  (1, '系统管理', 'BUYOUT', 'ACTIVE');

INSERT INTO cloud_user (tenant_id, username, password_hash, role, real_name, status) VALUES
  (1, 'admin', SHA2('admin123', 256), 'ADMIN', '系统管理员', 'ACTIVE'),
  (1, 'maintainer', SHA2('maintain123', 256), 'MAINTENANCE', '运维工程师', 'ACTIVE');
