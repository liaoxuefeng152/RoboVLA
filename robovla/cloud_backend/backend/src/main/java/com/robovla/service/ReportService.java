package com.robovla.service;

import com.robovla.entity.ProductionRecord;
import com.robovla.mapper.ProductionRecordMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;

import java.io.FileOutputStream;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

@Slf4j
@Service
@RequiredArgsConstructor
public class ReportService {

    private final ProductionRecordMapper recordMapper;

    /**
     * 日生产报表
     */
    public Map<String, Object> dailyReport(String dateStr) {
        LocalDate date = LocalDate.parse(dateStr);
        LocalDateTime start = date.atStartOfDay();
        LocalDateTime end = date.plusDays(1).atStartOfDay();

        List<ProductionRecord> records = recordMapper.selectByDateRange(start, end);
        int total = records.size();
        int good = records.stream().mapToInt(r -> r.getGoodCount() != null ? r.getGoodCount() : 0).sum();
        int bad = records.stream().mapToInt(r -> r.getBadCount() != null ? r.getBadCount() : 0).sum();
        double totalDuration = records.stream().mapToDouble(r -> r.getDurationS() != null ? r.getDurationS() : 0).sum();

        return Map.of(
            "date", dateStr,
            "totalCycles", total,
            "goodCount", good,
            "badCount", bad,
            "yieldRate", total > 0 ? Math.round(good * 1000.0 / (good + bad)) / 10.0 : 0,
            "durationHours", Math.round(totalDuration / 36.0) / 100.0,
            "errors", records.stream().filter(r -> r.getErrorMsg() != null).count()
        );
    }

    /**
     * 设备稼动率统计
     */
    public Map<String, Object> utilizationRate(String deviceSn, String startDate, String endDate) {
        LocalDateTime start = LocalDate.parse(startDate).atStartOfDay();
        LocalDateTime end = LocalDate.parse(endDate).plusDays(1).atStartOfDay();

        List<ProductionRecord> records = recordMapper.selectByDeviceAndDateRange(deviceSn, start, end);
        double totalWork = records.stream().mapToDouble(r -> r.getDurationS() != null ? r.getDurationS() : 0).sum();
        long totalAvailable = java.time.Duration.between(start, end).toSeconds();

        return Map.of(
            "deviceSn", deviceSn,
            "period", startDate + " ~ " + endDate,
            "totalWorkHours", Math.round(totalWork / 36.0) / 100.0,
            "utilizationRate", totalAvailable > 0 ? Math.round(totalWork * 10000.0 / totalAvailable) / 100.0 : 0
        );
    }

    /**
     * 导出 Excel 报表
     */
    public String exportExcel(String startDate, String endDate) throws Exception {
        LocalDateTime start = LocalDate.parse(startDate).atStartOfDay();
        LocalDateTime end = LocalDate.parse(endDate).plusDays(1).atStartOfDay();

        List<ProductionRecord> records = recordMapper.selectByDateRange(start, end);

        Workbook wb = new XSSFWorkbook();
        Sheet sheet = wb.createSheet("生产报表");

        // 表头
        Row header = sheet.createRow(0);
        String[] headers = {"ID", "设备SN", "任务ID", "循环", "良品", "不良", "耗时(s)", "错误", "时间"};
        for (int i = 0; i < headers.length; i++) {
            Cell cell = header.createCell(i);
            cell.setCellValue(headers[i]);
            CellStyle style = wb.createCellStyle();
            Font font = wb.createFont();
            font.setBold(true);
            style.setFont(font);
            cell.setCellStyle(style);
        }

        // 数据行
        int rowIdx = 1;
        for (ProductionRecord r : records) {
            Row row = sheet.createRow(rowIdx++);
            row.createCell(0).setCellValue(r.getId());
            row.createCell(1).setCellValue(r.getDeviceSn());
            row.createCell(2).setCellValue(r.getTaskId());
            row.createCell(3).setCellValue(r.getCycleNum());
            row.createCell(4).setCellValue(r.getGoodCount());
            row.createCell(5).setCellValue(r.getBadCount());
            row.createCell(6).setCellValue(r.getDurationS());
            row.createCell(7).setCellValue(r.getErrorMsg() != null ? r.getErrorMsg() : "");
            row.createCell(8).setCellValue(r.getCreatedAt() != null ? r.getCreatedAt().toString() : "");
        }

        String filename = "reports/production_" + startDate + "_" + endDate + ".xlsx";
        try (FileOutputStream fos = new FileOutputStream(filename)) {
            wb.write(fos);
        }
        wb.close();
        return filename;
    }
}
