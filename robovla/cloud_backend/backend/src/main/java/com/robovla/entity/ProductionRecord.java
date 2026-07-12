package com.robovla.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("production_record")
public class ProductionRecord {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long tenantId;
    private Long deviceId;
    private String deviceSn;
    private String taskName;
    private Integer cycleCount;
    private Integer successCount;
    private Integer failCount;
    private Integer avgCycleMs;
    private LocalDateTime createdAt;
}
