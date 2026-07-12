package com.robovla.service;

import com.robovla.entity.Device;
import com.robovla.mapper.DeviceMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;

/**
 * Excel 报表导出服务
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ExcelExportService {

    private final DeviceMapper deviceMapper;

    /**
     * 导出生产日报表
     */
    public byte[] exportDailyReport(Long tenantId, LocalDate date) throws IOException {
        Workbook wb = new XSSFWorkbook();
        createProductionSheet(wb, tenantId, date);
        createFaultSheet(wb, tenantId, date);
        createDeviceSheet(wb, tenantId);

        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        wb.write(bos);
        wb.close();
        return bos.toByteArray();
    }

    /**
     * 导出月报(含稼动率统计)
     */
    public byte[] exportMonthlyReport(Long tenantId, int year, int month) throws IOException {
        Workbook wb = new XSSFWorkbook();

        // 1. 生产数据汇总
        Sheet prodSheet = wb.createSheet("生产汇总");
        CellStyle headerStyle = createHeaderStyle(wb);
        Row header = prodSheet.createRow(0);
        String[] headers = {"日期", "任务名称", "完成数量", "成功数", "失败数", "成功率(%)", "平均周期(ms)"};
        for (int i = 0; i < headers.length; i++) {
            Cell cell = header.createCell(i);
            cell.setCellValue(headers[i]);
            cell.setCellStyle(headerStyle);
        }

        List<Map<String, Object>> logs = deviceMapper.getMonthlyReport(tenantId, year, month);
        int rowIdx = 1;
        int totalSuccess = 0, totalFail = 0;
        for (Map<String, Object> log : logs) {
            Row row = prodSheet.createRow(rowIdx++);
            row.createCell(0).setCellValue(String.valueOf(log.getOrDefault("report_date", "")));
            row.createCell(1).setCellValue(String.valueOf(log.getOrDefault("task_name", "")));
            row.createCell(2).setCellValue(toInt(log.get("cycle_count")));
            row.createCell(3).setCellValue(toInt(log.get("success_count")));
            row.createCell(4).setCellValue(toInt(log.get("fail_count")));
            int s = toInt(log.get("success_count"));
            int f = toInt(log.get("fail_count"));
            totalSuccess += s;
            totalFail += f;
            double rate = (s + f > 0) ? (100.0 * s / (s + f)) : 0;
            row.createCell(5).setCellValue(String.format("%.1f", rate));
            row.createCell(6).setCellValue(toInt(log.get("avg_cycle_ms")));
        }

        // 汇总行
        Row summary = prodSheet.createRow(rowIdx + 1);
        summary.createCell(0).setCellValue("合计");
        summary.createCell(3).setCellValue(totalSuccess);
        summary.createCell(4).setCellValue(totalFail);
        double totalRate = (totalSuccess + totalFail > 0) ? (100.0 * totalSuccess / (totalSuccess + totalFail)) : 0;
        summary.createCell(5).setCellValue(String.format("%.1f%%", totalRate));

        // 2. 稼动率统计
        Sheet oeeSheet = wb.createSheet("稼动率统计");
        Row oeeHeader = oeeSheet.createRow(0);
        String[] oeeHeaders = {"设备名称", "序列号", "在线时长(小时)", "生产时长(小时)", "故障时长(小时)", "稼动率(%)"};
        for (int i = 0; i < oeeHeaders.length; i++) {
            Cell c = oeeHeader.createCell(i);
            c.setCellValue(oeeHeaders[i]);
            c.setCellStyle(headerStyle);
        }
        // OEE data (需结合心率数据计算, 此处留扩展)
        List<Device> devices = deviceMapper.findByTenant(tenantId);
        int oeeRow = 1;
        for (Device d : devices) {
            Row r = oeeSheet.createRow(oeeRow++);
            r.createCell(0).setCellValue(d.getDeviceName());
            r.createCell(1).setCellValue(d.getDeviceSn());
            r.createCell(2).setCellValue(0); // placeholder
            r.createCell(3).setCellValue(0);
            r.createCell(4).setCellValue(0);
            r.createCell(5).setCellValue("N/A");
        }

        for (int i = 0; i < headers.length; i++) prodSheet.autoSizeColumn(i);
        for (int i = 0; i < oeeHeaders.length; i++) oeeSheet.autoSizeColumn(i);

        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        wb.write(bos);
        wb.close();
        return bos.toByteArray();
    }

    // --- 私有 ---

    private void createProductionSheet(Workbook wb, Long tenantId, LocalDate date) {
        Sheet sheet = wb.createSheet(date.toString() + " 生产日报");
        CellStyle hs = createHeaderStyle(wb);
        Row header = sheet.createRow(0);
        String[] h = {"设备", "任务", "完成数", "成功", "失败", "成功率", "平均耗时(ms)"};
        for (int i = 0; i < h.length; i++) {
            Cell c = header.createCell(i);
            c.setCellValue(h[i]);
            c.setCellStyle(hs);
        }
        List<Map<String, Object>> data = deviceMapper.getDailyReport(tenantId, date.toString());
        int r = 1;
        for (Map<String, Object> d : data) {
            Row row = sheet.createRow(r++);
            row.createCell(0).setCellValue(String.valueOf(d.getOrDefault("device_name", "")));
            row.createCell(1).setCellValue(String.valueOf(d.getOrDefault("task_name", "")));
            row.createCell(2).setCellValue(toInt(d.get("cycle_count")));
            row.createCell(3).setCellValue(toInt(d.get("success_count")));
            row.createCell(4).setCellValue(toInt(d.get("fail_count")));
            int sc = toInt(d.get("success_count")), fc = toInt(d.get("fail_count"));
            row.createCell(5).setCellValue((sc + fc > 0) ? String.format("%.1f%%", 100.0 * sc / (sc + fc)) : "0%");
            row.createCell(6).setCellValue(toInt(d.get("avg_cycle_ms")));
        }
        for (int i = 0; i < h.length; i++) sheet.autoSizeColumn(i);
    }

    private void createFaultSheet(Workbook wb, Long tenantId, LocalDate date) {
        Sheet sheet = wb.createSheet("故障记录");
        CellStyle hs = createHeaderStyle(wb);
        Row header = sheet.createRow(0);
        String[] h = {"时间", "设备", "故障码", "级别", "描述", "已解决"};
        for (int i = 0; i < h.length; i++) {
            Cell c = header.createCell(i);
            c.setCellValue(h[i]);
            c.setCellStyle(hs);
        }
        for (int i = 0; i < h.length; i++) sheet.autoSizeColumn(i);
    }

    private void createDeviceSheet(Workbook wb, Long tenantId) {
        Sheet sheet = wb.createSheet("设备清单");
        CellStyle hs = createHeaderStyle(wb);
        Row header = sheet.createRow(0);
        String[] h = {"名称", "序列号", "品牌/型号", "授权类型", "在线状态", "最后心跳"};
        for (int i = 0; i < h.length; i++) {
            Cell c = header.createCell(i);
            c.setCellValue(h[i]);
            c.setCellStyle(hs);
        }
        List<Device> devices = deviceMapper.findByTenant(tenantId);
        int r = 1;
        for (Device d : devices) {
            Row row = sheet.createRow(r++);
            row.createCell(0).setCellValue(d.getDeviceName());
            row.createCell(1).setCellValue(d.getDeviceSn());
            row.createCell(2).setCellValue(d.getRobotBrand() + "/" + d.getRobotModel());
            row.createCell(3).setCellValue(d.getAuthType());
            row.createCell(4).setCellValue(d.getOnlineStatus());
            row.createCell(5).setCellValue(d.getLastHeartbeat() != null ?
                d.getLastHeartbeat().format(DateTimeFormatter.ofPattern("MM-dd HH:mm")) : "N/A");
        }
        for (int i = 0; i < h.length; i++) sheet.autoSizeColumn(i);
    }

    private CellStyle createHeaderStyle(Workbook wb) {
        CellStyle style = wb.createCellStyle();
        Font font = wb.createFont();
        font.setBold(true);
        font.setFontHeightInPoints((short) 11);
        style.setFont(font);
        style.setFillForegroundColor(IndexedColors.GREY_25_PERCENT.getIndex());
        style.setFillPattern(FillPatternType.SOLID_FOREGROUND);
        style.setBorderBottom(BorderStyle.THIN);
        return style;
    }

    private int toInt(Object v) {
        if (v == null) return 0;
        if (v instanceof Number) return ((Number) v).intValue();
        try { return Integer.parseInt(v.toString()); } catch (Exception e) { return 0; }
    }
}
