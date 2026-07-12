package com.robovla.controller;

import com.robovla.service.ExcelExportService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.YearMonth;

@Slf4j
@RestController
@RequestMapping("/api/report")
@RequiredArgsConstructor
public class ReportController {

    private final ExcelExportService exportService;

    @GetMapping("/daily")
    public ResponseEntity<byte[]> dailyReport(
            @RequestParam Long tenantId,
            @RequestParam(required = false) String date) {
        LocalDate d = (date != null) ? LocalDate.parse(date) : LocalDate.now();
        try {
            byte[] data = exportService.exportDailyReport(tenantId, d);
            String filename = "RoboVLA_日报_" + d + ".xlsx";
            return excelResponse(data, filename);
        } catch (IOException e) {
            log.error("Daily report export failed", e);
            return ResponseEntity.internalServerError().build();
        }
    }

    @GetMapping("/monthly")
    public ResponseEntity<byte[]> monthlyReport(
            @RequestParam Long tenantId,
            @RequestParam int year,
            @RequestParam int month) {
        try {
            byte[] data = exportService.exportMonthlyReport(tenantId, year, month);
            String filename = String.format("RoboVLA_月报_%d%02d.xlsx", year, month);
            return excelResponse(data, filename);
        } catch (IOException e) {
            log.error("Monthly report export failed", e);
            return ResponseEntity.internalServerError().build();
        }
    }

    private ResponseEntity<byte[]> excelResponse(byte[] data, String filename) {
        return ResponseEntity.ok()
            .header(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename*=UTF-8''" + URLEncoder.encode(filename, StandardCharsets.UTF_8))
            .contentType(MediaType.parseMediaType(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
            .body(data);
    }
}
