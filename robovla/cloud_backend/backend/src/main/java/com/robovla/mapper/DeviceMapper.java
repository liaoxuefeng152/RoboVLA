package com.robovla.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.robovla.entity.Device;
import com.robovla.entity.ProductionRecord;
import org.apache.ibatis.annotations.*;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Mapper
public interface DeviceMapper extends BaseMapper<Device> {

    @Select("SELECT * FROM device WHERE device_sn = #{sn}")
    Device selectBySn(@Param("sn") String sn);

    @Select("SELECT * FROM device WHERE tenant_id = #{tenantId} ORDER BY updated_at DESC")
    List<Device> selectByTenant(@Param("tenantId") Long tenantId);

    @Select("SELECT * FROM device WHERE online_status = 'ONLINE'")
    List<Device> selectOnline();

    @Select("SELECT * FROM device WHERE auth_expire_at < #{threshold} AND auth_type != 'BUYOUT'")
    List<Device> selectExpiring(@Param("threshold") LocalDateTime threshold);

    /** 用于 DeviceService.findBySn */
    @Select("SELECT * FROM device WHERE device_sn = #{sn} LIMIT 1")
    Device findBySn(@Param("sn") String deviceSn);

    /** 用于 ExcelExportService */
    @Select("SELECT * FROM device WHERE tenant_id = #{tenantId}")
    List<Device> findByTenant(@Param("tenantId") Long tenantId);

    /** 日报查询 */
    @Select("SELECT d.device_name, pl.task_name, " +
            "SUM(pl.cycle_count) as cycle_count, SUM(pl.success_count) as success_count, " +
            "SUM(pl.fail_count) as fail_count, AVG(pl.avg_cycle_ms) as avg_cycle_ms " +
            "FROM production_log pl JOIN device d ON pl.device_id = d.id " +
            "WHERE pl.tenant_id = #{tenantId} AND DATE(pl.reported_at) = #{date} " +
            "GROUP BY d.device_name, pl.task_name")
    List<Map<String, Object>> getDailyReport(@Param("tenantId") Long tenantId, @Param("date") String date);

    /** 月报查询 */
    @Select("SELECT DATE(pl.reported_at) as report_date, pl.task_name, " +
            "SUM(pl.cycle_count) as cycle_count, SUM(pl.success_count) as success_count, " +
            "SUM(pl.fail_count) as fail_count, AVG(pl.avg_cycle_ms) as avg_cycle_ms " +
            "FROM production_log pl " +
            "WHERE pl.tenant_id = #{tenantId} AND YEAR(pl.reported_at) = #{year} AND MONTH(pl.reported_at) = #{month} " +
            "GROUP BY DATE(pl.reported_at), pl.task_name ORDER BY report_date")
    List<Map<String, Object>> getMonthlyReport(@Param("tenantId") Long tenantId,
                                                @Param("year") int year,
                                                @Param("month") int month);
}

@Mapper
interface ProductionRecordMapper extends BaseMapper<ProductionRecord> {
    @Select("SELECT * FROM production_record WHERE created_at BETWEEN #{start} AND #{end} ORDER BY created_at DESC")
    List<ProductionRecord> selectByDateRange(@Param("start") LocalDateTime start,
                                              @Param("end") LocalDateTime end);

    @Select("SELECT * FROM production_record WHERE device_sn = #{sn} AND created_at BETWEEN #{start} AND #{end}")
    List<ProductionRecord> selectByDeviceAndDateRange(@Param("sn") String sn,
                                                       @Param("start") LocalDateTime start,
                                                       @Param("end") LocalDateTime end);
}
